import argparse
import json
import logging
import os
import re
import socket
import sys
from pathlib import Path

from nazar_contracts import PipelineMode
from nazar_worker import __version__
from nazar_worker.client import WorkerClient
from nazar_worker.doctor import collect
from nazar_worker.runner import run_loop
from nazar_worker.stages import ADAPTERS, STAGE_PLAN

TOKEN_VAR = "NAZAR_WORKER_TOKEN"  # noqa: S105 - the variable name, not a value


def _token(env_file: Path | None) -> str | None:
    """Read the worker token from the environment, else from a dotenv file. Never printed."""
    value = os.environ.get(TOKEN_VAR, "").strip()
    if value or env_file is None or not env_file.is_file():
        return value or None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, sep, raw = line.partition("=")
        if sep and name.strip() == TOKEN_VAR:
            return raw.strip().strip("'\"") or None
    return None


def _default_worker_id() -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", f"{socket.gethostname()}-{os.getpid()}")[:64]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nazar-worker")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="Read-only host diagnostics (GPU, disk, toolchain).")
    doctor.add_argument("--workdir", type=Path, default=Path.cwd())
    sub.add_parser("stages", help="Show the stage plan and which adapters are implemented.")
    run = sub.add_parser("run", help="Lease and process jobs from the API (outbound HTTP only).")
    run.add_argument("--api", default=os.environ.get("NAZAR_API_BASE_URL", "http://127.0.0.1:8000"))
    run.add_argument(
        "--modes",
        default="test",
        help="Comma-separated pipelines to accept: test (deterministic fixtures), standard.",
    )
    run.add_argument("--worker-id", default=_default_worker_id())
    run.add_argument("--env-file", type=Path, default=Path(".env"))
    run.add_argument("--step-delay", type=float, default=0.0, help="Test pipeline pacing (s).")
    run.add_argument("--poll", type=float, default=2.0, help="Seconds between empty polls.")
    run.add_argument("--heartbeat", type=float, default=10.0, help="Lease renewal interval (s).")
    run.add_argument("--once", action="store_true", help="Handle at most one job, then exit.")
    args = parser.parse_args(argv)

    if args.command == "doctor":
        print(json.dumps(collect(args.workdir), indent=2))
        return 0
    if args.command == "stages":
        for plan in STAGE_PLAN:
            state = "implemented" if plan.stage in ADAPTERS else "not implemented"
            kind = "optional" if plan.optional else "required"
            print(
                f"{plan.stage.value:22} {kind:9} M{plan.milestone:<3} {state:16} {plan.component}"
            )
        return 0

    try:
        modes = [PipelineMode(m.strip()) for m in args.modes.split(",") if m.strip()]
    except ValueError:
        print("--modes accepts: test, standard", file=sys.stderr)
        return 2
    token = _token(args.env_file)
    if token is None:
        print(
            f"{TOKEN_VAR} is not set (environment or --env-file). Nothing was run.", file=sys.stderr
        )
        return 2
    if PipelineMode.STANDARD in modes and not ADAPTERS:
        print(
            "Note: no real reconstruction stages are implemented yet; standard jobs will fail "
            "with an explanation at the geometry stage.",
            file=sys.stderr,
        )
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = WorkerClient(args.api, token)
    try:
        run_loop(
            client,
            args.worker_id,
            modes,
            step_s=args.step_delay,
            poll_s=args.poll,
            heartbeat_s=args.heartbeat,
            once=args.once,
        )
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
