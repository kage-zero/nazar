import argparse

import uvicorn

from nazar_api.settings import get_settings


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="nazar-api")
    parser.add_argument("--reload", action="store_true", help="Reload on code changes (dev).")
    args = parser.parse_args()
    uvicorn.run(
        "nazar_api.main:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        reload=args.reload,
        log_config=None,
    )


if __name__ == "__main__":
    main()
