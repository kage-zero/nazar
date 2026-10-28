"""Telemetry upload through the real chunked-upload API. SYNTHETIC FIXTURES: no real flight log
was supplied, so these files are hand-written in the documented DJI SRT / CSV layouts."""

from typing import Any

from fastapi.testclient import TestClient
from test_missions import create_mission, upload

SRT = "".join(
    f"{i + 1}\n00:00:{i:02d},000 --> 00:00:{i:02d},033\n"
    f"[latitude: {41.89021 + i * 0.00009:.6f}] [longitude: 12.492231] "
    f"[rel_alt: {50 + i:.3f} abs_alt: 98.512]\n\n"
    for i in range(10)
)


def register(client: TestClient, mission_id: str, name: str, size: int) -> Any:
    return client.post(
        f"/api/missions/{mission_id}/assets",
        json={"kind": "telemetry", "filename": name, "byte_size": size},
    )


def test_srt_is_accepted_and_summarised(operator: TestClient) -> None:
    mission = create_mission(operator)
    data = SRT.encode()
    asset = register(operator, mission["id"], "DJI_0001.SRT", len(data)).json()
    done = upload(operator, asset["id"], data)
    assert done["status"] == "ready" and done["kind"] == "telemetry"
    summary = operator.get(f"/api/assets/{asset['id']}/telemetry").json()
    assert summary["format"] == "dji_srt"
    assert summary["samples"] == 10
    assert summary["altitude_kind"] == "relative_to_takeoff"
    assert summary["video_coverage"] is None  # no validated video yet
    assert 85 < summary["horizontal_extent_m"] < 95  # 9 steps of ~10 m north
    mission_now = operator.get(f"/api/missions/{mission['id']}").json()
    assert mission_now["telemetry"]["id"] == asset["id"]
    # One telemetry file per mission.
    assert register(operator, mission["id"], "again.srt", 10).status_code == 409


def test_unusable_telemetry_is_rejected_with_a_reason(operator: TestClient) -> None:
    mission = create_mission(operator)
    data = b"time_s,latitude,longitude\n0,41.89,12.49\n"
    asset = register(operator, mission["id"], "log.csv", len(data)).json()
    done = upload(operator, asset["id"], data)
    assert done["status"] == "rejected"
    assert "Fewer than two" in done["error"]
    assert operator.get(f"/api/assets/{asset['id']}/telemetry").status_code == 409
    # A rejected file can be removed and replaced.
    assert operator.delete(f"/api/assets/{asset['id']}").status_code == 204
    assert register(operator, mission["id"], "log.csv", len(data)).status_code == 201


def test_wrong_types_and_sizes_are_refused_before_upload(operator: TestClient) -> None:
    mission = create_mission(operator)
    assert register(operator, mission["id"], "flight.kml", 100).status_code == 422
    assert register(operator, mission["id"], "flight.srt", 30 * 2**20).status_code == 413
