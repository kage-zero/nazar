"""Set up (or check) the Fast3R GPU runtime used by the standard pipeline.

Usage (repo root):
    uv run python scripts/setup_fast3r.py --check     # read-only: verify an existing install
    uv run python scripts/setup_fast3r.py             # install whatever is missing

Installs, under var/gpu/ (git-ignored):
    fast3r-src/   facebookresearch/fast3r at the pinned commit
    fast3r-env/   Python 3.11 virtualenv from apps/worker/gpu/requirements-fast3r.txt
    weights/Fast3R_ViT_Large_512/   checkpoint at the pinned Hugging Face revision (~2.6 GB)

Fast3R code and weights are under the FAIR Noncommercial Research License: use them only for
non-commercial research (approved for this academic project). Downloads are large; run this
deliberately, not speculatively, and never on shared GPU hosts without permission.
Nothing here needs or prints a secret. A Hugging Face token is not required for these files.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GPU_DIR = REPO_ROOT / "var" / "gpu"
SRC = GPU_DIR / "fast3r-src"
ENV = GPU_DIR / "fast3r-env"
WEIGHTS = GPU_DIR / "weights" / "Fast3R_ViT_Large_512"
REQUIREMENTS = REPO_ROOT / "apps" / "worker" / "gpu" / "requirements-fast3r.txt"

SOURCE_URL = "https://github.com/facebookresearch/fast3r.git"
SOURCE_COMMIT = "33104d4b5b8df43795ecded236194958bbdac572"
WEIGHTS_REPO = "jedyang97/Fast3R_ViT_Large_512"
WEIGHTS_REVISION = "a2c770b768ceb3a53c36c4f7a3619db0413dc3a1"
WEIGHTS_SHA256 = "1357d42e74539ba03510ea1986c7464a7facf17157779e2b7ebd6284e79e0427"
PYTHON = "3.11"


def env_python() -> Path:
    return ENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    # Fixed argv built in this file (git, uv, the GPU interpreter); no user input reaches it.
    subprocess.run(cmd, check=True)  # noqa: S603


def source_commit() -> str | None:
    if not (SRC / ".git").exists():
        return None
    out = subprocess.run(  # noqa: S603 - fixed argv
        ["git", "-C", str(SRC), "rev-parse", "HEAD"],  # noqa: S607 - git from PATH, as documented
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip() or None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


def check(verify_hash: bool) -> list[str]:
    """Problems with the current install (empty when it matches the pins)."""
    problems = []
    commit = source_commit()
    if commit != SOURCE_COMMIT:
        problems.append(f"fast3r source: expected {SOURCE_COMMIT[:7]}, found {commit or 'none'}")
    if not env_python().is_file():
        problems.append(f"GPU environment missing: {env_python()}")
    else:
        probe = (
            "import json, torch, fast3r; print(json.dumps({'torch': torch.__version__, "
            "'cuda': torch.cuda.is_available(), 'device': torch.cuda.get_device_name(0) "
            "if torch.cuda.is_available() else None}))"
        )
        out = subprocess.run(  # noqa: S603 - the GPU interpreter with a fixed probe
            [str(env_python()), "-W", "ignore", "-c", probe],
            capture_output=True,
            text=True,
            check=False,
        )
        lines = [ln for ln in out.stdout.splitlines() if ln.startswith("{")]
        if out.returncode or not lines:
            problems.append("GPU environment cannot import torch + fast3r")
        else:
            info = json.loads(lines[-1])
            print(f"torch {info['torch']}, CUDA available: {info['cuda']}, GPU: {info['device']}")
            if not info["cuda"]:
                problems.append("CUDA is not available to PyTorch in the GPU environment")
    model = WEIGHTS / "model.safetensors"
    if not model.is_file() or not (WEIGHTS / "config.json").is_file():
        problems.append(f"weights missing: {WEIGHTS}")
    elif verify_hash:
        print("hashing model.safetensors (2.6 GB)...")
        if sha256(model) != WEIGHTS_SHA256:
            problems.append("model.safetensors does not match the pinned revision's SHA-256")
    return problems


def install() -> None:
    if shutil.which("git") is None or shutil.which("uv") is None:
        raise SystemExit("git and uv must be on PATH.")
    GPU_DIR.mkdir(parents=True, exist_ok=True)
    if source_commit() != SOURCE_COMMIT:
        if not SRC.exists():
            run(["git", "clone", SOURCE_URL, str(SRC)])
        run(["git", "-C", str(SRC), "fetch", "origin", SOURCE_COMMIT])
        run(["git", "-C", str(SRC), "checkout", "--detach", SOURCE_COMMIT])
    if not env_python().is_file():
        run(["uv", "venv", "--python", PYTHON, str(ENV)])
    pip = ["uv", "pip", "install", "--python", str(env_python())]
    run([*pip, "--index-strategy", "unsafe-best-match", "-r", str(REQUIREMENTS)])
    run([*pip, "--no-deps", "-e", str(SRC)])
    if not (WEIGHTS / "model.safetensors").is_file():
        script = (
            "from huggingface_hub import snapshot_download; "
            f"snapshot_download({WEIGHTS_REPO!r}, revision={WEIGHTS_REVISION!r}, "
            f"local_dir={str(WEIGHTS)!r})"
        )
        run([str(env_python()), "-c", script])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="Verify only; change nothing.")
    parser.add_argument("--hash", action="store_true", help="Also hash the checkpoint (slow).")
    args = parser.parse_args()
    if not args.check:
        install()
    problems = check(verify_hash=args.hash or not args.check)
    for problem in problems:
        print("PROBLEM:", problem)
    if problems:
        return 1
    rel = env_python().relative_to(REPO_ROOT)
    print("Fast3R runtime OK. In .env set:")
    print(f"  NAZAR_FAST3R_PYTHON={rel.as_posix()}")
    print(f"  NAZAR_FAST3R_WEIGHTS={WEIGHTS.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
