"""Typed settings loaded from the environment and the repo-root `.env` file.

Secrets are `SecretStr` so they never appear in reprs or logs. Blank values in `.env`
are treated as "not configured", never as an empty secret.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NAZAR_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    web_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    storage_dir: Path = Path("var/storage")
    max_upload_mb: int = Field(default=2048, gt=0)
    max_video_seconds: int = Field(default=900, gt=0)
    gpu_max_concurrent_jobs: int = Field(default=1, ge=1)

    secret_key: SecretStr | None = None
    worker_token: SecretStr | None = None
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: SecretStr | None = None

    database_url: SecretStr | None = None
    redis_url: SecretStr | None = None
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("web_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @property
    def storage_path(self) -> Path:
        path = self.storage_dir
        return path if path.is_absolute() else REPO_ROOT / path

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url is not None:
            return self.database_url.get_secret_value()
        return f"sqlite:///{(self.storage_path / 'nazar.db').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
