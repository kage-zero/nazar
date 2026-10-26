"""Locating and invoking FFmpeg/ffprobe. Arguments are always argv lists, never a shell."""

import shutil
import subprocess
from pathlib import Path


class MediaError(Exception):
    """The input cannot be used. `message` is safe to show to the user."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Cancelled(Exception):
    """Processing was cancelled by the caller."""


def tool(name: str) -> str:
    exe = shutil.which(name)
    if exe is None:
        raise RuntimeError(f"{name} was not found on PATH. Install FFmpeg (see ENVIRONMENT_SETUP).")
    return exe


def run_ffprobe(args: list[str], path: Path, timeout: float = 120) -> str:
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv, resolved executable
            [tool("ffprobe"), "-v", "error", *args, str(path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError("probe_timeout", "Reading the video's metadata timed out.") from exc
    if out.returncode != 0:
        raise MediaError(
            "unreadable", "The file could not be read as media. It may be corrupt or not a video."
        )
    return out.stdout
