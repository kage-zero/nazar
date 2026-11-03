"""Shared helpers for the GPU runners (imported from the runner's own directory).

Runners run inside an isolated GPU environment, never in the worker's own. They speak JSON
lines on stdout (one event per line) and log to stderr. This module gives every runner the
same event format and the same VRAM discipline:

- `budget(mib)` caps this process's PyTorch allocations (`set_per_process_memory_fraction`),
  also bounded by what is actually free right now (the desktop shares the card);
- `peak()` reports what the process really used: the allocator's peak reservation plus the
  CUDA context, measured as the free-memory drop before any allocation.
"""

import contextlib
import json
import sys
import time
from typing import Any

_context_mib = 0.0
_budget_mib = 0.0


def emit(**event: Any) -> None:
    print(json.dumps(event), flush=True)


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def budget(limit_mib: int) -> float:
    """Initialise CUDA and cap this process. Returns the effective cap in MiB (0 = none)."""
    global _context_mib, _budget_mib
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available to PyTorch.")
    free0, total = torch.cuda.mem_get_info()
    torch.zeros(1, device="cuda")  # creates the context
    free1, _ = torch.cuda.mem_get_info()
    _context_mib = max(0.0, (free0 - free1) / 2**20)
    free_mib = free1 / 2**20
    if limit_mib <= 0:
        _budget_mib = 0.0
        return 0.0
    # The cap covers the allocator only; the context already counts against the budget.
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
        return torch.cuda.mem_get_info()[0] / 2**20
    return max(0.0, _budget_mib - torch.cuda.memory_reserved() / 2**20)


def peak() -> dict[str, int]:
    import torch

    reserved = torch.cuda.max_memory_reserved() / 2**20
    return {
        "peak_vram_mib": round(reserved + _context_mib),
        "peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 2**20),
        "cuda_context_mib": round(_context_mib),
        "budget_mib": round(_budget_mib + _context_mib) if _budget_mib else 0,
    }


def is_oom(exc: BaseException) -> bool:
    import torch

    return isinstance(exc, torch.cuda.OutOfMemoryError) or "out of memory" in str(exc).lower()


class Timer:
    def __init__(self) -> None:
        self.t0 = time.monotonic()

    def s(self) -> float:
        return round(time.monotonic() - self.t0, 3)


def run_main(main: Any) -> None:
    """Exit codes: 0 done, 3 out of memory within the budget, 1 any other failure."""
    try:
        sys.exit(main())
    except Exception as exc:
        oom = isinstance(exc, MemoryError)
        with contextlib.suppress(Exception):  # torch itself may be what failed to import
            oom = oom or is_oom(exc)
        emit(
            event="error",
            kind="oom" if oom else "failed",
            message=f"{type(exc).__name__}: {exc}"[:500],
        )
        sys.exit(3 if oom else 1)
