"""Locating and running the GPU model runners (ADR-0004).

The worker's own environment never imports torch. Each model runs as a subprocess of a
separate interpreter, reading inputs from and writing outputs to a job work directory, and
streaming JSON events on stdout (see `apps/worker/gpu/_common.py`).

Two GPU interpreters are used:

    NAZAR_GPU_PYTHON    main GPU environment: Fast3R, Open3D, YOLO, SAM 2, Metric3D-v2
    NAZAR_SPLAT_PYTHON  Gaussian-splat environment (gsplat; needs its own torch build)
    NAZAR_GPU_WEIGHTS   directory holding the model weights (default var/gpu/weights)
    NAZAR_GPU_DIR       directory holding model source checkouts (default var/gpu)

When a variable is unset, the standard locations created by `scripts/setup_gpu.py` under
`var/gpu/` are used if they exist. A variable set to an empty value disables that
environment (tests use this to force the CPU-only path).
"""

import json
import logging
import os
import queue
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("nazar_worker")

REPO_ROOT = Path(__file__).resolve().parents[4]
GPU_SCRIPTS = Path(__file__).resolve().parents[2] / "gpu"
DEFAULT_GPU_DIR = REPO_ROOT / "var" / "gpu"


def _venv_python(env_dir: Path) -> Path:
    return env_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


@dataclass(frozen=True)
class GpuRuntime:
    main_python: Path | None
    splat_python: Path | None
    weights: Path
    root: Path = DEFAULT_GPU_DIR

    @staticmethod
    def from_env(env: Mapping[str, str] | None = None) -> "GpuRuntime":
        env = os.environ if env is None else env

        root = Path(env.get("NAZAR_GPU_DIR", "") or DEFAULT_GPU_DIR)

        def pick(var: str, default: Path) -> Path | None:
            if var in env and not env[var]:
                return None  # explicitly disabled
            path = Path(env[var]) if env.get(var) else default
            return path if path.is_file() else None

        return GpuRuntime(
            main_python=pick("NAZAR_GPU_PYTHON", _venv_python(root / "main-env")),
            splat_python=pick("NAZAR_SPLAT_PYTHON", _venv_python(root / "splat-env")),
            weights=Path(env.get("NAZAR_GPU_WEIGHTS", "") or root / "weights"),
            root=root,
        )

    def missing(self, *files: str, splat: bool = False) -> str | None:
        """Why a runner cannot start (shown to users), or None when everything is there."""
        python = self.splat_python if splat else self.main_python
        if python is None:
            var = "NAZAR_SPLAT_PYTHON" if splat else "NAZAR_GPU_PYTHON"
            return (
                f"The GPU environment is not set up on this worker ({var}; scripts/setup_gpu.py)."
            )
        for name in files:
            if not (self.weights / name).exists():
                return f"Model weights {name} are not installed on this worker."
        return None


class RunnerFailed(Exception):
    def __init__(self, message: str, *, oom: bool = False) -> None:
        super().__init__(message)
        self.oom = oom


_ISOLATE = {"VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE"}


def runner_env(base: Mapping[str, str]) -> dict[str, str]:
    """Environment for a GPU interpreter: the worker's own virtualenv must not leak into it
    (its Scripts dir on PATH and VIRTUAL_ENV/PYTHON* variables can make the other interpreter
    load the wrong DLLs or packages)."""
    env = {k: v for k, v in base.items() if k.upper() not in _ISOLATE}
    venv = base.get("VIRTUAL_ENV")
    if venv:
        own = os.path.normcase(os.path.normpath(venv))
        env["PATH"] = os.pathsep.join(
            p
            for p in base.get("PATH", "").split(os.pathsep)
            if p and not os.path.normcase(os.path.normpath(p)).startswith(own)
        )
    env.update(PYTHONWARNINGS="ignore", PYTHONIOENCODING="utf-8")
    if sys.platform != "win32":  # not supported by PyTorch on Windows
        # Fewer, larger segments: less fragmentation under a tight memory cap.
        env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    return env


def run_runner(
    python: Path,
    script: str,
    args: list[str],
    check_cancel: Callable[[], None],
    on_event: Callable[[dict[str, Any]], None] = lambda e: None,
) -> dict[str, Any]:
    """Run `apps/worker/gpu/<script>` and return its `done` event. Raises `RunnerFailed`
    (with `oom` set when the runner ran out of memory within its budget). `check_cancel` may
    raise; the process is killed before the exception propagates."""
    cmd = [str(python), "-X", "faulthandler", str(GPU_SCRIPTS / script), *args]
    try:
        proc = subprocess.Popen(  # noqa: S603 - fixed argv to a configured local interpreter
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=runner_env(os.environ),
            cwd=str(GPU_SCRIPTS),
        )
    except OSError as exc:
        raise RunnerFailed(f"The GPU interpreter could not be started ({exc}).") from exc
    lines: queue.Queue[str | None] = queue.Queue()
    stderr_tail: list[str] = []

    def pump_out() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    def pump_err() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_tail.append(line.rstrip())
            del stderr_tail[:-60]

    threading.Thread(target=pump_out, daemon=True).start()
    threading.Thread(target=pump_err, daemon=True).start()
    done: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    try:
        while True:
            check_cancel()
            try:
                line = lines.get(timeout=0.5)
            except queue.Empty:
                continue
            if line is None:
                break
            try:
                event = json.loads(line)
            except ValueError:
                continue  # library chatter on stdout
            if not isinstance(event, dict):
                continue
            if event.get("event") == "done":
                done = event
            elif event.get("event") == "error":
                error = event
            else:
                on_event(event)
        proc.wait(timeout=60)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
    if done is not None and proc.returncode == 0:
        return done
    log.warning("%s failed (exit %s):\n%s", script, proc.returncode, "\n".join(stderr_tail))
    if error is not None:
        raise RunnerFailed(str(error.get("message", "failed")), oom=error.get("kind") == "oom")
    useful = [ln for ln in stderr_tail if ln.strip() and "Warning" not in ln]
    raise RunnerFailed(
        f"{script} exited with code {proc.returncode}. {' | '.join(useful[-3:])[:400]}".strip()
    )
