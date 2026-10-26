from pathlib import Path

import pytest

from nazar_contracts import PIPELINE_STAGES
from nazar_worker.cli import main
from nazar_worker.doctor import collect, parse_nvidia_smi
from nazar_worker.stages import STAGE_PLAN


def test_parse_nvidia_smi_csv() -> None:
    gpus = parse_nvidia_smi("NVIDIA GeForce RTX 4050 Laptop GPU, 6141, 512, 5629, 616.92, 3\n")
    assert len(gpus) == 1
    assert gpus[0].memory_free_mib == 5629
    assert gpus[0].utilization_pct == 3


def test_parse_nvidia_smi_tolerates_unsupported_fields() -> None:
    gpus = parse_nvidia_smi("A100, 40960, 0, 40960, 550.54, [N/A]\ngarbage line\n")
    assert len(gpus) == 1
    assert gpus[0].utilization_pct is None


def test_stage_plan_covers_every_pipeline_stage_in_order() -> None:
    assert tuple(p.stage for p in STAGE_PLAN) == PIPELINE_STAGES


def test_doctor_reports_disk_without_running_gpu_work(tmp_path: Path) -> None:
    report = collect(tmp_path)
    assert isinstance(report["disk_free_gib"], float)
    assert "gpus" in report


def test_run_is_honest_about_missing_job_loop(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run"]) == 2
    assert "not implemented" in capsys.readouterr().err
