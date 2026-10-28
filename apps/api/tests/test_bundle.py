"""Offline bundle mode (ADR-0003): export a job's inputs, run it with no API, import the result.
Uses the deterministic test pipeline (SYNTHETIC output) so the round trip is fast; the replay
path is the same for standard jobs."""

import json
import zipfile
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_jobs import app_client, events, ready_mission, start_job, worker_client  # noqa: F401
from test_standard_pipeline import sample_mission

from nazar_api.jobs import expire_leases
from nazar_api.models import JobRecord, utcnow
from nazar_contracts import PipelineMode
from nazar_worker.bundle import BundleError, export_bundle, import_result, run_bundle
from nazar_worker.cli import main as cli_main
from nazar_worker.runner import run_loop


def lapse_export_lease(client: TestClient, job_id: str) -> None:
    """Fast-forward the export lease's expiry (60 s in real use)."""
    with Session(client.app.state.engine) as db:  # type: ignore[attr-defined]
        row = db.get(JobRecord, job_id)
        assert row is not None
        row.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        expire_leases(db)


def exported(client: TestClient, tmp_path: Path) -> tuple[str, Path]:
    job = start_job(client, ready_mission(client))
    bundle = tmp_path / "mission.zip"
    lease = export_bundle(worker_client(client), "laptop", bundle, [PipelineMode.TEST])
    assert lease is not None and lease.job_id == job["id"]
    return str(job["id"]), bundle


def test_bundle_round_trip_completes_the_job(app_client: TestClient, tmp_path: Path) -> None:  # noqa: F811
    job_id, bundle = exported(app_client, tmp_path)
    with zipfile.ZipFile(bundle) as zf:
        names = set(zf.namelist())
        meta = json.loads(zf.read("bundle.json"))
    assert {"bundle.json", "preflight.json", "keyframes/0001.jpg"} <= names
    assert meta["lease"]["lease_id"] == "offline-bundle"  # no live lease id leaves the API

    snap = app_client.get(f"/api/jobs/{job_id}").json()
    assert snap["status"] == "queued" and snap["attempt"] == 1
    lapse_export_lease(app_client, job_id)
    assert app_client.get(f"/api/jobs/{job_id}").json()["attempt"] == 1  # no attempt used

    result = tmp_path / "result.zip"
    assert run_bundle(bundle, result, "vdi-gpu") == "completed"
    assert import_result(worker_client(app_client), result, "laptop") == "completed"

    final = app_client.get(f"/api/jobs/{job_id}").json()
    assert final["status"] == "completed", final["error"]
    assert final["attempt"] == 1
    assert {a["kind"] for a in final["artifacts"]} == {
        "point_cloud_preview",
        "point_cloud",
        "camera_trajectory",
        "report",
    }
    codes = [w["code"] for w in final["warnings"]]
    assert "offline_bundle" in codes and "test_pipeline" in codes
    log = events(app_client, job_id)
    assert [e["seq"] for e in log] == list(range(1, len(log) + 1))
    done = [e for e in log if e["type"] == "stage.completed"]
    assert done and all("duration_s" in e["data"] for e in done)

    # Importing again is refused: the job is finished.
    with pytest.raises(BundleError, match="cannot be leased"):
        import_result(worker_client(app_client), result, "laptop")


def test_import_waits_for_the_export_lease_and_checks_the_video(
    app_client: TestClient,  # noqa: F811
    tmp_path: Path,
) -> None:
    job_id, bundle = exported(app_client, tmp_path)
    result = tmp_path / "result.zip"
    run_bundle(bundle, result, "vdi-gpu")
    with pytest.raises(BundleError, match="export lease"):
        import_result(worker_client(app_client), result, "laptop")

    lapse_export_lease(app_client, job_id)
    forged = tmp_path / "forged.zip"
    with zipfile.ZipFile(result) as src, zipfile.ZipFile(forged, "w") as dst:
        for item in src.infolist():
            data = src.read(item)
            if item.filename == "result.json":
                meta = json.loads(data)
                meta["video_sha256"] = "f" * 64
                data = json.dumps(meta).encode()
            dst.writestr(item, data)
    with pytest.raises(BundleError, match="different video"):
        import_result(worker_client(app_client), forged, "laptop")


def test_corrupted_artifact_is_refused_before_anything_is_sent(
    app_client: TestClient,  # noqa: F811
    tmp_path: Path,
) -> None:
    job_id, bundle = exported(app_client, tmp_path)
    lapse_export_lease(app_client, job_id)
    result = tmp_path / "result.zip"
    run_bundle(bundle, result, "vdi-gpu")
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(result) as src, zipfile.ZipFile(broken, "w") as dst:
        for item in src.infolist():
            data = src.read(item)
            if item.filename == "artifacts/001.bin":
                data = bytes([data[0] ^ 0xFF]) + data[1:]
            dst.writestr(item, data)
    before = len(events(app_client, job_id))
    with pytest.raises(BundleError, match="corrupted"):
        import_result(worker_client(app_client), broken, "laptop")
    assert len(events(app_client, job_id)) == before
    snap = app_client.get(f"/api/jobs/{job_id}").json()
    assert snap["status"] == "queued"
    # The untouched result still imports, and an online worker would also have found the job.
    assert import_result(worker_client(app_client), result, "laptop") == "completed"
    assert run_loop(worker_client(app_client), "w1", [PipelineMode.TEST], once=True) == 0


def test_standard_job_through_the_cli_bundle_run(
    app_client: TestClient,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REAL DATA: sample1 keyframes, offline `nazar-worker bundle run` (CPU baseline unless
    Fast3R is configured), then import. This is the command sequence for the college VDI."""
    for name in ("NAZAR_FAST3R_PYTHON", "NAZAR_FAST3R_WEIGHTS"):
        monkeypatch.delenv(name, raising=False)  # deterministic: CPU baseline
    job = start_job(app_client, sample_mission(app_client), pipeline="standard")
    bundle, result = tmp_path / "mission.zip", tmp_path / "result.zip"
    lease = export_bundle(worker_client(app_client), "laptop", bundle, [PipelineMode.STANDARD])
    assert lease is not None
    lapse_export_lease(app_client, job["id"])

    code = cli_main(
        ["bundle", "run", str(bundle), "--out", str(result), "--env-file", str(tmp_path / "none")]
    )
    assert code == 0
    with zipfile.ZipFile(result) as zf:
        assert json.loads(zf.read("result.json"))["geometry"] == "cpu-baseline"
    assert import_result(worker_client(app_client), result, "laptop") == "completed"

    final = app_client.get(f"/api/jobs/{job['id']}").json()
    assert final["status"] == "completed", final["error"]
    media = {a["media_type"] for a in final["artifacts"] if a["kind"] == "export"}
    assert {"application/vnd.las", "model/gltf-binary"} <= media
