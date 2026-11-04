import argparse
import json
import logging
import os
import re
import socket
import sys
from pathlib import Path

from nazar_contracts import ComputeTarget, PipelineMode
from nazar_worker import __version__, local_run
from nazar_worker.bundle import BundleError, export_bundle, import_result, run_bundle
from nazar_worker.client import ApiCallFailed, WorkerClient
from nazar_worker.doctor import collect
from nazar_worker.fast3r import Fast3rRuntime
from nazar_worker.runner import run_loop
from nazar_worker.stages import STAGE_PLAN
from nazar_worker.standard import Skip, build_standard_pipeline

TOKEN_VAR = "NAZAR_WORKER_TOKEN"  # noqa: S105 - the variable name, not a value


FAST3R_VARS = ("NAZAR_FAST3R_PYTHON", "NAZAR_FAST3R_WEIGHTS", "NAZAR_FAST3R_MAX_VIEWS")
FAST3R_PATHS = {"NAZAR_FAST3R_PYTHON", "NAZAR_FAST3R_WEIGHTS"}


def _dotenv(env_file: Path | None) -> dict[str, str]:
    if env_file is None or not env_file.is_file():
        return {}
    values = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, sep, raw = line.partition("=")
        if sep and not name.lstrip().startswith("#"):
            values[name.strip()] = raw.strip().strip("'\"")
    return values


def _token(env_file: Path | None) -> str | None:
    """Read the worker token from the environment, else from a dotenv file. Never printed."""
    value = os.environ.get(TOKEN_VAR, "").strip()
    return value or _dotenv(env_file).get(TOKEN_VAR) or None


def _load_fast3r_settings(env_file: Path | None) -> None:
    """Fill the Fast3R settings (paths, not secrets) from the dotenv file when the environment
    does not set them; relative paths are relative to the dotenv file's folder (repo root)."""
    values = _dotenv(env_file)
    for name in FAST3R_VARS:
        value = values.get(name, "")
        if name in os.environ or not value:
            continue
        if name in FAST3R_PATHS and env_file is not None and not Path(value).is_absolute():
            value = str((env_file.resolve().parent / value).resolve())
        os.environ[name] = value


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
        default="test,standard",
        help="Comma-separated pipelines to accept: test (deterministic fixtures), standard.",
    )
    run.add_argument("--worker-id", default=_default_worker_id())
    run.add_argument("--env-file", type=Path, default=Path(".env"))
    run.add_argument("--step-delay", type=float, default=0.0, help="Test pipeline pacing (s).")
    run.add_argument("--poll", type=float, default=2.0, help="Seconds between empty polls.")
    run.add_argument("--heartbeat", type=float, default=10.0, help="Lease renewal interval (s).")
    run.add_argument("--once", action="store_true", help="Handle at most one job, then exit.")
    run.add_argument(
        "--location",
        choices=[c.value for c in ComputeTarget],
        default=os.environ.get("NAZAR_WORKER_LOCATION", ComputeTarget.LOCAL.value),
        help="Where this worker runs; it only takes jobs started for this GPU (default: local, "
        "or NAZAR_WORKER_LOCATION).",
    )
    _bundle_parser(sub)
    local_run.add_parser(sub)
    args = parser.parse_args(argv)

    if args.command == "doctor":
        print(json.dumps(collect(args.workdir), indent=2))
        return 0
    if args.command == "stages":
        standard = {
            stage
            for stage, adapter in build_standard_pipeline().items()
            if not isinstance(adapter, Skip)
        }
        for plan in STAGE_PLAN:
            state = "implemented" if plan.stage in standard else "not implemented"
            kind = "optional" if plan.optional else "required"
            print(
                f"{plan.stage.value:22} {kind:9} M{plan.milestone:<3} {state:16} {plan.component}"
            )
        return 0
    if args.command == "bundle":
        return _bundle(args)
    if args.command == "local":
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
        return local_run.main(args)

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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if PipelineMode.STANDARD in modes:
        _load_fast3r_settings(args.env_file)
        runtime = Fast3rRuntime.from_env()
        logging.getLogger("nazar_worker").info(
            "standard geometry: %s",
            "Fast3R on the GPU (CPU baseline as fallback)"
            if isinstance(runtime, Fast3rRuntime)
            else f"CPU baseline. {runtime}",
        )
    client = WorkerClient(args.api, token, location=ComputeTarget(args.location))
    logging.getLogger("nazar_worker").info("worker location: %s GPU", args.location)
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


def _bundle_parser(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    bundle = sub.add_parser(
        "bundle", help="Offline mode for a GPU machine that cannot reach the API (ADR-0003)."
    )
    steps = bundle.add_subparsers(dest="step", required=True)
    exp = steps.add_parser("export", help="(online) Lease a queued job; save its inputs to a zip.")
    exp.add_argument("--out", type=Path, required=True, help="Mission bundle to write (.zip).")
    exp.add_argument("--job", default=None, help="Job id (default: the oldest queued job).")
    exp.add_argument("--modes", default="standard", help="Pipelines to accept: test, standard.")
    exp.add_argument(
        "--location",
        choices=[c.value for c in ComputeTarget],
        default=ComputeTarget.COLLEGE.value,
        help="Export a job started for this GPU (default: college).",
    )
    run = steps.add_parser("run", help="(offline) Process a mission bundle; no network or token.")
    run.add_argument("bundle", type=Path, help="Mission bundle from `bundle export`.")
    run.add_argument("--out", type=Path, required=True, help="Result bundle to write (.zip).")
    run.add_argument("--step-delay", type=float, default=0.0, help="Test pipeline pacing (s).")
    imp = steps.add_parser("import", help="(online) Send a result bundle to the API.")
    imp.add_argument("result", type=Path, help="Result bundle from `bundle run`.")
    for step in (exp, run, imp):
        step.add_argument("--env-file", type=Path, default=Path(".env"))
        step.add_argument("--worker-id", default=_default_worker_id())
    for step in (exp, imp):
        step.add_argument(
            "--api", default=os.environ.get("NAZAR_API_BASE_URL", "http://127.0.0.1:8000")
        )


def _bundle(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.step == "run":
        _load_fast3r_settings(args.env_file)
        try:
            outcome = run_bundle(args.bundle, args.out, args.worker_id, args.step_delay)
        except BundleError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"Job {outcome}. Result bundle: {args.out}")
        return 0 if outcome == "completed" else 1
    token = _token(args.env_file)
    if token is None:
        print(
            f"{TOKEN_VAR} is not set (environment or --env-file). Nothing was sent.",
            file=sys.stderr,
        )
        return 2
    location = ComputeTarget(getattr(args, "location", ComputeTarget.LOCAL.value))
    client = WorkerClient(args.api, token, location=location)
    try:
        if args.step == "export":
            modes = [PipelineMode(m.strip()) for m in args.modes.split(",") if m.strip()]
            lease = export_bundle(client, args.worker_id, args.out, modes, args.job)
            if lease is None:
                print(f"No queued job for the {location.value} GPU to export.", file=sys.stderr)
                return 1
            print(
                f"Exported job {lease.job_id} ({lease.keyframe_count} keyframes) to {args.out}. "
                "It stays queued: do not run an online worker until you import the result."
            )
            return 0
        outcome = import_result(client, args.result, args.worker_id)
    except (BundleError, ApiCallFailed, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Imported: job {outcome}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
