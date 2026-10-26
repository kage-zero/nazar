from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nazar_api.main import create_app
from nazar_api.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE1 = REPO_ROOT / "docs/sample/video/sample1.mp4"
HEADERS = {"X-Nazar-Request": "1"}
EMAIL = "ops@example.org"
PASSWORD = "correct horse battery"


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    overrides.setdefault("env", "test")
    return Settings(_env_file=None, storage_dir=tmp_path, **overrides)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(tmp_path)), headers=HEADERS) as c:
        yield c


@pytest.fixture
def operator(client: TestClient) -> TestClient:
    """The client, signed in as a freshly created first operator."""
    response = client.post("/api/auth/setup", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return client
