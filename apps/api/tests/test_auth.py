from pathlib import Path

from conftest import EMAIL, HEADERS, PASSWORD, make_settings
from fastapi.testclient import TestClient

from nazar_api.main import create_app
from nazar_api.security import hash_password, verify_password


def test_password_hash_round_trip_and_is_salted() -> None:
    encoded = hash_password(PASSWORD)
    assert verify_password(PASSWORD, encoded)
    assert not verify_password("wrong password", encoded)
    assert hash_password(PASSWORD) != encoded
    assert PASSWORD not in encoded
    assert not verify_password(PASSWORD, "garbage")


def test_first_run_setup_signs_in_and_then_closes(client: TestClient) -> None:
    assert client.get("/api/auth/state").json() == {"setup_required": True, "user": None}
    response = client.post(
        "/api/auth/setup", json={"email": "Ops@Example.org", "password": PASSWORD}
    )
    assert response.status_code == 201
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    state = client.get("/api/auth/state").json()
    assert state["setup_required"] is False
    assert state["user"]["email"] == EMAIL
    again = client.post("/api/auth/setup", json={"email": "x@example.org", "password": PASSWORD})
    assert again.status_code == 409


def test_setup_is_refused_in_production(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, env="production"))
    with TestClient(app, headers=HEADERS) as c:
        response = c.post("/api/auth/setup", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 403


def test_bootstrap_admin_from_env_can_sign_in(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path, bootstrap_admin_email=EMAIL, bootstrap_admin_password=PASSWORD
    )
    with TestClient(create_app(settings), headers=HEADERS) as c:
        assert c.get("/api/auth/state").json()["setup_required"] is False
        assert c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).is_success


def test_login_logout_and_wrong_password(operator: TestClient) -> None:
    operator.post("/api/auth/logout")
    assert operator.get("/api/missions").status_code == 401
    bad = operator.post("/api/auth/login", json={"email": EMAIL, "password": "not the password"})
    assert bad.status_code == 401
    assert operator.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).is_success
    assert operator.get("/api/missions").status_code == 200


def test_login_is_throttled_after_repeated_failures(operator: TestClient) -> None:
    operator.post("/api/auth/logout")
    for _ in range(8):
        operator.post("/api/auth/login", json={"email": EMAIL, "password": "wrong-password"})
    blocked = operator.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert blocked.status_code == 429


def test_mutations_without_request_header_are_rejected(operator: TestClient) -> None:
    response = operator.post("/api/missions", json={"name": "x"}, headers={"X-Nazar-Request": ""})
    assert response.status_code == 403


def test_short_passwords_are_rejected(client: TestClient) -> None:
    response = client.post("/api/auth/setup", json={"email": EMAIL, "password": "short"})
    assert response.status_code == 422
