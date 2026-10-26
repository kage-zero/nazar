"""Bring the database schema to the latest Alembic revision (run on API startup)."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from nazar_api.settings import Settings

API_DIR = Path(__file__).resolve().parents[2]


def upgrade_to_head(settings: Settings) -> None:
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "migrations"))
    config.attributes["settings"] = settings
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
