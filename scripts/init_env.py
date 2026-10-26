"""Create `.env` from `.env.example` and fill blank machine-generated secrets.

Usage (repo root): uv run python scripts/init_env.py

Only values that software generates for itself are filled (random tokens). Anything a
human must choose (accounts, third-party keys) is left untouched. Existing non-blank
values are never changed, and secret values are never printed.
"""

import os
import re
import secrets
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATED = ("NAZAR_SECRET_KEY", "NAZAR_WORKER_TOKEN")


def main() -> int:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        shutil.copyfile(REPO_ROOT / ".env.example", env_path)
        print("Created .env from .env.example")

    text = env_path.read_text(encoding="utf-8")
    for name in GENERATED:
        pattern = re.compile(rf"^{name}=[ \t]*$", re.MULTILINE)
        if pattern.search(text):
            text = pattern.sub(f"{name}={secrets.token_urlsafe(48)}", text, count=1)
            print(f"{name}: generated")
        elif re.search(rf"^{name}=\S", text, re.MULTILINE):
            print(f"{name}: already set (unchanged)")
        else:
            text = text.rstrip("\n") + f"\n{name}={secrets.token_urlsafe(48)}\n"
            print(f"{name}: added and generated")

    tmp = env_path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, env_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
