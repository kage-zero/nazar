import time
from typing import Any

import pytest
from conftest import PASSWORD, SAMPLE1
from fastapi.testclient import TestClient

CHUNK = 1024 * 1024


def create_mission(client: TestClient, name: str = "Colosseum orbit") -> dict[str, Any]:
    response = client.post("/api/missions", json={"name": name})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def register(client: TestClient, mission_id: str, filename: str, size: int) -> dict[str, Any]:
    response = client.post(
        f"/api/missions/{mission_id}/assets",
        json={"kind": "video", "filename": filename, "byte_size": size},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def upload(client: TestClient, asset_id: str, data: bytes) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for offset in range(0, len(data), CHUNK):
        response = client.put(
            f"/api/assets/{asset_id}/content?offset={offset}", content=data[offset : offset + CHUNK]
        )
        assert response.status_code == 200, response.text
        body = response.json()
    return body


def wait_for(client: TestClient, asset_id: str, timeout: float = 60) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        asset: dict[str, Any] = client.get(f"/api/assets/{asset_id}").json()
        if asset["status"] != "validating":
            return asset
        time.sleep(0.2)
    raise AssertionError("validation did not finish")


def test_missions_require_sign_in(client: TestClient) -> None:
    assert client.get("/api/missions").status_code == 401


def test_missions_are_private_to_their_owner(operator: TestClient) -> None:
    mission = create_mission(operator)
    assert [m["id"] for m in operator.get("/api/missions").json()] == [mission["id"]]
    operator.post("/api/auth/logout")
    assert operator.get(f"/api/missions/{mission['id']}").status_code == 401


@pytest.mark.parametrize(
    ("filename", "size", "code"),
    [("notes.txt", 10, 422), ("clip.exe", 10, 422), ("huge.mp4", 10**13, 413)],
)
def test_upload_rejects_wrong_type_and_size(
    operator: TestClient, filename: str, size: int, code: int
) -> None:
    mission = create_mission(operator)
    response = operator.post(
        f"/api/missions/{mission['id']}/assets",
        json={"kind": "video", "filename": filename, "byte_size": size},
    )
    assert response.status_code == code


def test_chunk_offsets_make_retries_safe(operator: TestClient) -> None:
    mission = create_mission(operator)
    asset = register(operator, mission["id"], "a.mp4", 10)
    first = operator.put(f"/api/assets/{asset['id']}/content?offset=0", content=b"01234")
    assert first.json()["received_bytes"] == 5
    stale = operator.put(f"/api/assets/{asset['id']}/content?offset=0", content=b"01234")
    assert stale.status_code == 409
    assert stale.json()["received_bytes"] == 5
    too_much = operator.put(f"/api/assets/{asset['id']}/content?offset=5", content=b"0123456789")
    assert too_much.status_code == 413
    assert operator.get(f"/api/assets/{asset['id']}").json()["received_bytes"] == 5


def test_corrupt_video_is_rejected_with_a_clear_reason(operator: TestClient) -> None:
    mission = create_mission(operator)
    data = b"this is not a video" * 100
    asset = register(operator, mission["id"], "broken.mp4", len(data))
    assert upload(operator, asset["id"], data)["status"] == "validating"
    final = wait_for(operator, asset["id"])
    assert final["status"] == "rejected"
    assert final["error"]
    assert operator.get(f"/api/assets/{asset['id']}/preflight").status_code == 409
    # A rejected video can be removed and replaced.
    assert operator.delete(f"/api/assets/{asset['id']}").status_code == 204
    register(operator, mission["id"], "next.mp4", 10)


@pytest.mark.skipif(not SAMPLE1.is_file(), reason="sample video not present")
def test_sample_video_upload_to_preflight(operator: TestClient) -> None:
    mission = create_mission(operator)
    data = SAMPLE1.read_bytes()
    asset = register(operator, mission["id"], SAMPLE1.name, len(data))
    duplicate = operator.post(
        f"/api/missions/{mission['id']}/assets",
        json={"kind": "video", "filename": "other.mp4", "byte_size": 10},
    )
    assert duplicate.status_code == 409

    upload(operator, asset["id"], data)
    final = wait_for(operator, asset["id"])
    assert final["status"] == "ready", final
    assert len(final["sha256"]) == 64

    report = operator.get(f"/api/assets/{asset['id']}/preflight").json()
    assert report["source_sha256"] == final["sha256"]
    assert report["analysis"]["frames_decoded"] > 500
    assert len(report["keyframes"]) >= 8
    thumb = operator.get(f"/api/assets/{asset['id']}/thumbs/1.jpg")
    assert thumb.status_code == 200
    assert thumb.content[:2] == b"\xff\xd8"
    assert operator.get(f"/api/assets/{asset['id']}/thumbs/9999.jpg").status_code == 404
    assert operator.get(f"/api/assets/{asset['id']}/other/1.jpg").status_code == 404

    mission_view = operator.get(f"/api/missions/{mission['id']}").json()
    assert mission_view["video"]["status"] == "ready"
    assert PASSWORD not in operator.get(f"/api/assets/{asset['id']}/preflight").text


@pytest.mark.skipif(not SAMPLE1.is_file(), reason="sample video not present")
def test_cancel_during_validation_cleans_up(operator: TestClient) -> None:
    mission = create_mission(operator)
    data = SAMPLE1.read_bytes()
    asset = register(operator, mission["id"], SAMPLE1.name, len(data))
    upload(operator, asset["id"], data)
    assert operator.delete(f"/api/assets/{asset['id']}").status_code == 204
    assert operator.get(f"/api/assets/{asset['id']}").status_code == 404
    assert operator.get(f"/api/missions/{mission['id']}").json()["video"] is None
