"""Background validation + preflight for uploaded videos.

Runs CPU-only work (FFmpeg decode, NumPy metrics) on one background thread so request
handlers stay fast. Progress and outcome are written to the asset row, which clients poll.
Assets left in `validating` by a restart are picked up again on startup.

This in-process executor covers Milestone 2. GPU stages go to the pull-based worker
(ADR-0003) once the job infrastructure lands in Milestone 4.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from nazar_api.models import AssetRecord
from nazar_api.settings import Settings
from nazar_api.storage import PREFLIGHT_DIR, asset_dir, remove_tree
from nazar_contracts import AssetStatus
from nazar_media import Cancelled, MediaError, run_preflight

log = logging.getLogger(__name__)


class AssetProcessor:
    def __init__(self, settings: Settings, engine: Engine) -> None:
        self._settings = settings
        self._engine = engine
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="preflight")

    def submit(self, asset_id: str) -> None:
        self._pool.submit(self._run_safely, asset_id)

    def resume_pending(self) -> int:
        with Session(self._engine) as db:
            ids = db.scalars(
                select(AssetRecord.id).where(AssetRecord.status == AssetStatus.VALIDATING)
            ).all()
        for asset_id in ids:
            self.submit(asset_id)
        return len(ids)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _update(self, asset_id: str, **fields: Any) -> None:
        with Session(self._engine) as db:
            asset = db.get(AssetRecord, asset_id)
            if asset is None:
                return
            for key, value in fields.items():
                setattr(asset, key, value)
            db.commit()

    def _status(self, asset_id: str) -> str | None:
        with Session(self._engine) as db:
            return db.scalar(select(AssetRecord.status).where(AssetRecord.id == asset_id))

    def _run_safely(self, asset_id: str) -> None:
        try:
            self._run(asset_id)
        except Exception:
            log.exception("preflight crashed", extra={"asset_id": asset_id})
            self._update(
                asset_id,
                status=AssetStatus.FAILED,
                progress=None,
                error="Validation stopped because of an internal error. You can retry it.",
            )

    def _run(self, asset_id: str) -> None:
        with Session(self._engine) as db:
            asset = db.get(AssetRecord, asset_id)
            if asset is None or asset.status != AssetStatus.VALIDATING:
                return
            mission_id, stored_name, sha256 = asset.mission_id, asset.stored_name, asset.sha256
        folder = asset_dir(self._settings, mission_id, asset_id)

        last_write = 0.0
        last_check = 0.0
        cancelled = False

        def on_phase(phase: str, done: int | None, total: int | None) -> None:
            nonlocal last_write
            now = time.monotonic()
            if done not in (None, 0) and now - last_write < 0.25:
                return
            last_write = now
            self._update(asset_id, progress={"phase": phase, "completed": done, "total": total})

        def should_cancel() -> bool:
            nonlocal last_check, cancelled
            now = time.monotonic()
            if now - last_check >= 0.5:
                last_check = now
                cancelled = self._status(asset_id) != AssetStatus.VALIDATING
            return cancelled

        started = time.monotonic()
        try:
            report = run_preflight(
                folder / stored_name,
                folder / PREFLIGHT_DIR,
                asset_id=asset_id,
                source_sha256=sha256 or "",
                max_duration_s=self._settings.max_video_seconds,
                on_phase=on_phase,
                should_cancel=should_cancel,
            )
        except Cancelled:
            log.info("preflight cancelled", extra={"asset_id": asset_id})
            remove_tree(folder)
            return
        except MediaError as exc:
            log.info("video rejected", extra={"asset_id": asset_id, "code": exc.code})
            remove_tree(folder / PREFLIGHT_DIR)
            self._update(asset_id, status=AssetStatus.REJECTED, progress=None, error=exc.message)
            return
        if self._status(asset_id) != AssetStatus.VALIDATING:  # cancelled at the last moment
            remove_tree(folder)
            return
        self._update(asset_id, status=AssetStatus.READY, progress=None, error=None)
        log.info(
            "preflight complete",
            extra={
                "asset_id": asset_id,
                "frames": report.analysis.frames_decoded,
                "keyframes": len(report.keyframes),
                "seconds": round(time.monotonic() - started, 2),
            },
        )
