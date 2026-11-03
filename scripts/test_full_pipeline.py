"""Run NAZAR's full backend pipeline on one video and report what every model contributed.

Usage (repo root):
    uv run --package nazar-worker python scripts/test_full_pipeline.py \
        --video docs/sample/video/sample1.mp4 --how local
    uv run --package nazar-worker python scripts/test_full_pipeline.py --video clip.mp4 --how clg

--how local  laptop GPU: every model process is capped at the 6 GB budget (slow is fine);
             a step that cannot fit is skipped with a reason.
--how clg    college GPU (30+ GB): larger models and settings; every model must run.

Optional: --telemetry FLIGHT.SRT|.CSV, --out DIR (default var/runs/<video>-<how>).
No API, web app or worker token is needed. Exit codes: 0 every model contributed (and, on
local, stayed within the GPU budget); 3 completed but a model was skipped or over budget;
1 the job failed; 2 bad input.
"""

import sys

from nazar_worker.cli import main

if __name__ == "__main__":
    sys.exit(main(["local", *sys.argv[1:]]))
