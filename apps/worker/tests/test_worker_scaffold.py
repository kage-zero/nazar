import os
from pathlib import Path

import pytest

from nazar_contracts import PIPELINE_STAGES
from nazar_worker.cli import FAST3R_VARS, _load_fast3r_settings, main
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


def test_run_refuses_without_a_worker_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NAZAR_WORKER_TOKEN", raising=False)
    assert main(["run", "--env-file", str(tmp_path / "missing.env")]) == 2
    assert "NAZAR_WORKER_TOKEN is not set" in capsys.readouterr().err


def test_fast3r_settings_come_from_the_env_file_relative_to_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in FAST3R_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NAZAR_FAST3R_MAX_VIEWS", "6")  # the environment wins over the file
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# NAZAR_FAST3R_PYTHON=commented/out\n"
        "NAZAR_FAST3R_PYTHON=var/gpu/python.exe\n"
        "NAZAR_FAST3R_WEIGHTS=\n"
        "NAZAR_FAST3R_MAX_VIEWS=12\n",
        encoding="utf-8",
    )
    _load_fast3r_settings(env_file)
    assert Path(os.environ["NAZAR_FAST3R_PYTHON"]) == (tmp_path / "var/gpu/python.exe").resolve()
    assert "NAZAR_FAST3R_WEIGHTS" not in os.environ  # blank stays unset: CPU baseline
    assert os.environ["NAZAR_FAST3R_MAX_VIEWS"] == "6"
