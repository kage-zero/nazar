import argparse
import json
import sys
from pathlib import Path

from nazar_worker import __version__
from nazar_worker.doctor import collect
from nazar_worker.stages import ADAPTERS, STAGE_PLAN


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nazar-worker")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="Read-only host diagnostics (GPU, disk, toolchain).")
    doctor.add_argument("--workdir", type=Path, default=Path.cwd())
    sub.add_parser("stages", help="Show the stage plan and which adapters are implemented.")
    sub.add_parser("run", help="Lease and process jobs from the API (Milestone 4).")
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
    print(
        "The job loop is not implemented yet (Milestone 4). Nothing was processed.", file=sys.stderr
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
