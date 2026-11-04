"""Shared helpers for the GPU runners (imported from the runner's own directory).

Runners run inside an isolated GPU environment, never in the worker's own. They speak JSON
lines on stdout (one event per line) and log to stderr. This module gives every runner the
same event format and the same VRAM discipline:

- `budget(mib)` caps this process's PyTorch allocations (`set_per_process_memory_fraction`)
  so that allocator + CUDA context stay within `mib`, also bounded by what is actually free
  (the desktop shares the card);
- `peak()` reports what the process really used. The device's used memory is read with
  `nvidia-smi` before CUDA starts (baseline: other programs) and sampled 10x per second while
  the runner works; the process peak is the largest rise over the baseline. That covers the
  CUDA context and cuDNN/cuBLAS workspaces that PyTorch's own counters do not see.
"""

import contextlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

_context_mib = 0.0
_budget_mib = 0.0
_baseline_mib: float | None = None
_device_peak_mib = 0.0
_stop = threading.Event()
_ASSUMED_CONTEXT_MIB = 400.0
"""Used only when nvidia-smi is unavailable to measure the CUDA context."""


def emit(**event: Any) -> None:
    print(json.dumps(event), flush=True)


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _nvidia_smi_used_mib() -> float | None:
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return None
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv
            [exe, "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-i", "0"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return float(out.stdout.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def _sample(torch: Any) -> None:
    global _device_peak_mib
    while not _stop.wait(0.1):
        with contextlib.suppress(Exception):
            free, total = torch.cuda.mem_get_info()
            _device_peak_mib = max(_device_peak_mib, (total - free) / 2**20)


def budget(limit_mib: int) -> float:
    """Initialise CUDA, start the memory sampler and cap this process. Returns the allocator
    cap in MiB (0 = none)."""
    global _context_mib, _budget_mib, _baseline_mib, _device_peak_mib
    _baseline_mib = _nvidia_smi_used_mib()
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available to PyTorch.")
    torch.zeros(1, device="cuda")  # creates the context
    free, total = torch.cuda.mem_get_info()
    used = (total - free) / 2**20
    _device_peak_mib = used
    _context_mib = used - _baseline_mib if _baseline_mib is not None else _ASSUMED_CONTEXT_MIB
    _context_mib = max(_context_mib, 0.0)
    threading.Thread(target=_sample, args=(torch,), daemon=True).start()
    free_mib = free / 2**20
    if limit_mib <= 0:
        _budget_mib = 0.0
        return 0.0
    cap = min(limit_mib - _context_mib, free_mib - 256)
    if cap <= 256:
        raise MemoryError(
            f"Only {free_mib:.0f} MiB of GPU memory is free; close other GPU programs."
        )
    torch.cuda.set_per_process_memory_fraction(min(1.0, cap * 2**20 / total))
    _budget_mib = cap
    return cap


def allocator_cap_mib() -> float:
    """What the allocator may still use, for runners that size their batches to it."""
    import torch

    if _budget_mib <= 0:
        return float(torch.cuda.mem_get_info()[0] / 2**20)
    return max(0.0, _budget_mib - torch.cuda.memory_reserved() / 2**20)


def peak() -> dict[str, Any]:
    import torch

    reserved = torch.cuda.max_memory_reserved() / 2**20
    measured = _device_peak_mib - _baseline_mib if _baseline_mib is not None else None
    process = max(reserved + _context_mib, measured or 0.0)
    return {
        "peak_vram_mib": round(process),
        "peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 2**20),
        "peak_reserved_mib": round(reserved),
        "cuda_context_mib": round(_context_mib),
        "other_programs_mib": round(_baseline_mib) if _baseline_mib is not None else None,
        "budget_mib": round(_budget_mib + _context_mib) if _budget_mib else 0,
        "measurement": "device-sampled rise over other programs (nvidia-smi baseline)"
        if measured is not None
        else "allocator peak + assumed CUDA context (nvidia-smi unavailable)",
    }


def is_oom(exc: BaseException) -> bool:
    import torch

    return isinstance(exc, torch.cuda.OutOfMemoryError) or "out of memory" in str(exc).lower()


class Timer:
    def __init__(self) -> None:
        self.t0 = time.monotonic()

    def s(self) -> float:
        return round(time.monotonic() - self.t0, 3)


def _exit(code: int) -> None:
    """Leave without the interpreter's CUDA teardown, which was seen to hang for minutes on
    Windows after a runner had already written its results (the driver frees everything)."""
    _stop.set()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def run_main(main: Any) -> None:
    """Exit codes: 0 done, 3 out of memory within the budget, 1 any other failure."""
    try:
        code = int(main() or 0)
    except Exception as exc:
        oom = isinstance(exc, MemoryError)
        with contextlib.suppress(Exception):  # torch itself may be what failed to import
            oom = oom or is_oom(exc)
        emit(
            event="error",
            kind="oom" if oom else "failed",
            message=f"{type(exc).__name__}: {exc}"[:500],
        )
        import traceback

        traceback.print_exc()
        code = 3 if oom else 1
    _exit(code)
