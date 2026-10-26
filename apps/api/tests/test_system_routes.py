from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nazar_api.main import create_app
from nazar_api.settings import Settings

SECRET = "s3cr3t-value-that-must-never-leak"


def make_client(tmp_path: Path, **overrides: Any) -> TestClient:
    settings = Settings(_env_file=None, env="test", storage_dir=tmp_path, **overrides)
    return TestClient(create_app(settings))


def test_health_is_ok(tmp_path: Path) -> None:
    body = make_client(tmp_path).get("/api/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "nazar-api"
    assert body["environment"] == "test"


def test_ready_reports_blank_secrets_as_not_configured(tmp_path: Path) -> None:
    body = make_client(tmp_path, secret_key="").get("/api/ready").json()
    checks = {c["name"]: c for c in body["checks"]}
    assert body["ready"] is False
    assert checks["database"]["status"] == "ok"
    assert checks["storage"]["status"] == "ok"
    assert checks["config:NAZAR_SECRET_KEY"]["status"] == "not_configured"
    assert checks["worker"]["status"] == "not_implemented"


def test_ready_when_configured_never_echoes_secret_values(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        secret_key=SECRET,
        worker_token=SECRET,
        bootstrap_admin_email="ops@example.org",
        bootstrap_admin_password=SECRET,
    )
    response = client.get("/api/ready")
    assert response.json()["ready"] is True
    assert SECRET not in response.text


@pytest.mark.parametrize("raw", ["", "   "])
def test_blank_env_values_are_unset(raw: str, tmp_path: Path) -> None:
    settings = Settings(_env_file=None, storage_dir=tmp_path, worker_token=raw)
    assert settings.worker_token is None
    assert SECRET not in repr(Settings(_env_file=None, worker_token=SECRET))


def test_cors_allows_configured_web_origin(tmp_path: Path) -> None:
    client = make_client(tmp_path, web_origins="http://localhost:5173")
    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
