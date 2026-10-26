"""Read-only environment diagnostics for a worker host (laptop or college VDI session).

Runs no GPU workload, installs nothing, and reads no credentials. Safe to run on a shared
machine to answer: which GPU, how much free VRAM/disk, which toolchain is present.
"""

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

NVIDIA_QUERY = "name,memory.total,memory.used,memory.free,driver_version,utilization.gpu"


@dataclass(frozen=True)
class GpuInfo:
    name: str
    memory_total_mib: int
    memory_used_mib: int
    memory_free_mib: int
    driver_version: str
    utilization_pct: int | None


def parse_nvidia_smi(csv_text: str) -> list[GpuInfo]:
    gpus = []
    for line in csv_text.strip().splitlines():
        fields = [f.strip() for f in line.split(",")]
        if len(fields) != 6:
            continue
        name, total, used, free, driver, util = fields
        gpus.append(
            GpuInfo(
                name=name,
                memory_total_mib=int(total),
                memory_used_mib=int(used),
                memory_free_mib=int(free),
                driver_version=driver,
                utilization_pct=int(util) if util.isdigit() else None,
            )
        )
    return gpus


def _version(cmd: list[str]) -> str | None:
    exe = shutil.which(cmd[0])
    if exe is None:
        return None
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv, resolved executable
            [exe, *cmd[1:]], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    first = (out.stdout or out.stderr).strip().splitlines()
    return first[0] if first else None


def _gpus() -> list[GpuInfo] | None:
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return None
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv, resolved executable
            [exe, f"--query-gpu={NVIDIA_QUERY}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_nvidia_smi(out.stdout) if out.returncode == 0 else None


def collect(workdir: Path) -> dict[str, object]:
    disk = shutil.disk_usage(workdir)
    gpus = _gpus()
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "workdir": str(workdir.resolve()),
        "disk_free_gib": round(disk.free / 2**30, 1),
        "disk_total_gib": round(disk.total / 2**30, 1),
        "ffmpeg": _version(["ffmpeg", "-version"]),
        "ffprobe": _version(["ffprobe", "-version"]),
        "nvcc": _version(["nvcc", "--version"]),
        "gpus": [asdict(g) for g in gpus] if gpus is not None else None,
        "notes": [] if gpus else ["nvidia-smi not found or failed: no usable NVIDIA GPU detected."],
    }
