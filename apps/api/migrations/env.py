from logging.config import fileConfig

from alembic import context

import nazar_api.models  # noqa: F401 - registers tables on Base.metadata
from nazar_api.db import Base, get_engine
from nazar_api.settings import Settings, get_settings

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# The API passes its own Settings when it migrates on startup; the CLI uses the environment.
settings: Settings = config.attributes.get("settings") or get_settings()
settings.storage_path.mkdir(parents=True, exist_ok=True)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=settings.sqlalchemy_url, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with get_engine(settings.sqlalchemy_url).connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
