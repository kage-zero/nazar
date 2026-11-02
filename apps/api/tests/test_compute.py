"""Choosing the GPU: each job is aimed at the local or the college worker, and only a worker
at that location leases it. Uses the deterministic test pipeline (SYNTHETIC output)."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from test_bundle import lapse_export_lease
from test_jobs import TOKEN, app_client, ready_mission, worker_client  # noqa: F401

from nazar_contracts import ComputeTarget, GeometryBackend, PipelineMode
from nazar_worker.bundle import export_bundle, import_result, run_bundle
from nazar_worker.runner import run_loop

COLLEGE = ComputeTarget.COLLEGE


def start(client: TestClient, compute: str | None) -> dict[str, Any]:
    body = {"pipeline": "test"} | ({"compute": compute} if compute else {})
    response = client.post(f"/api/missions/{ready_mission(client)}/jobs", json=body)
    assert response.status_code == 201, response.text
    job: dict[str, Any] = response.json()
    return job


def workers(client: TestClient) -> dict[str, dict[str, Any]]:
    return {w["location"]: w for w in client.get("/api/ready").json()["workers"]}


def test_jobs_default_to_the_local_gpu(app_client: TestClient) -> None:  # noqa: F811
    job = start(app_client, None)
    assert job["compute"] == "local"
    assert run_loop(worker_client(app_client, COLLEGE), "vdi", [PipelineMode.TEST], once=True) == 0
    assert run_loop(worker_client(app_client), "laptop", [PipelineMode.TEST], once=True) == 1
    assert app_client.get(f"/api/jobs/{job['id']}").json()["status"] == "completed"


def test_college_job_waits_for_the_college_worker(app_client: TestClient) -> None:  # noqa: F811
    job = start(app_client, "college")
    assert job["compute"] == "college"
    assert run_loop(worker_client(app_client), "laptop", [PipelineMode.TEST], once=True) == 0
    assert app_client.get(f"/api/jobs/{job['id']}").json()["status"] == "queued"

    assert run_loop(worker_client(app_client, COLLEGE), "vdi", [PipelineMode.TEST], once=True) == 1
    final = app_client.get(f"/api/jobs/{job['id']}").json()
    assert final["status"] == "completed" and final["compute"] == "college"

    # Retry keeps the job's location.
    assert app_client.post(f"/api/jobs/{job['id']}/retry").status_code in (200, 409)
    assert app_client.get(f"/api/jobs/{job['id']}").json()["compute"] == "college"


def test_readiness_tracks_each_location(app_client: TestClient) -> None:  # noqa: F811
    assert {w["online"] for w in workers(app_client).values()} == {False}
    college = worker_client(app_client, COLLEGE)
    assert college.lease("vdi", [PipelineMode.STANDARD], GeometryBackend.FAST3R) is None
    seen = workers(app_client)
    assert seen["college"]["online"] is True and seen["college"]["geometry"] == "fast3r"
    assert seen["local"]["online"] is False and seen["local"]["last_seen_s"] is None
    gpu = next(c for c in app_client.get("/api/ready").json()["checks"] if c["name"] == "gpu")
    assert gpu["status"] == "ok" and "college" in gpu["detail"]


def test_unknown_worker_location_is_rejected(app_client: TestClient) -> None:  # noqa: F811
    response = app_client.post(
        "/api/worker/lease",
        json={"worker_id": "w1", "modes": ["test"]},
        headers={"Authorization": f"Bearer {TOKEN}", "X-Nazar-Worker-Location": "moon"},
    )
    assert response.status_code == 400


def test_college_job_through_a_bundle(app_client: TestClient, tmp_path: Path) -> None:  # noqa: F811
    job = start(app_client, "college")
    bundle, result = tmp_path / "mission.zip", tmp_path / "result.zip"
    # The laptop exports on the college's behalf; a local export finds nothing.
    assert export_bundle(worker_client(app_client), "laptop", bundle, [PipelineMode.TEST]) is None
    lease = export_bundle(worker_client(app_client, COLLEGE), "laptop", bundle, [PipelineMode.TEST])
    assert lease is not None and lease.job_id == job["id"]
    lapse_export_lease(app_client, job["id"])
    assert run_bundle(bundle, result, "vdi") == "completed"
    # Import works from a default (local) client: the result says which location it acts for.
    assert import_result(worker_client(app_client), result, "laptop") == "completed"
    assert app_client.get(f"/api/jobs/{job['id']}").json()["status"] == "completed"
