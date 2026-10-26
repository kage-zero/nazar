"""Missions and their input assets: resumable chunked upload, validation, preflight."""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from nazar_api.deps import DbDep, SettingsDep, UserDep
from nazar_api.models import AssetRecord, MissionRecord, User
from nazar_api.storage import (
    PREFLIGHT_DIR,
    UPLOAD_PART,
    asset_dir,
    remove_tree,
    sha256_file,
    video_extension,
)
from nazar_contracts import (
    Asset,
    AssetCreate,
    AssetKind,
    AssetStatus,
    Mission,
    MissionCreate,
    PreflightReport,
    ProcessingProgress,
)

router = APIRouter(prefix="/api", tags=["missions"])

ACTIVE_VIDEO = (AssetStatus.UPLOADING, AssetStatus.VALIDATING, AssetStatus.READY)


def to_asset(row: AssetRecord) -> Asset:
    return Asset(
        id=row.id,
        mission_id=row.mission_id,
        kind=AssetKind(row.kind),
        filename=row.filename,
        byte_size=row.byte_size,
        received_bytes=row.received_bytes,
        status=AssetStatus(row.status),
        error=row.error,
        progress=ProcessingProgress.model_validate(row.progress) if row.progress else None,
        sha256=row.sha256,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _current_video(db: Session, mission_id: str) -> AssetRecord | None:
    return db.scalars(
        select(AssetRecord)
        .where(
            AssetRecord.mission_id == mission_id,
            AssetRecord.kind == AssetKind.VIDEO,
            AssetRecord.status != AssetStatus.CANCELLED,
        )
        .order_by(AssetRecord.created_at.desc())
        .limit(1)
    ).first()


def to_mission(db: Session, row: MissionRecord) -> Mission:
    video = _current_video(db, row.id)
    return Mission(
        id=row.id,
        name=row.name,
        created_at=row.created_at,
        video=to_asset(video) if video else None,
    )


def _owned_mission(db: Session, user: User, mission_id: str) -> MissionRecord:
    mission = db.get(MissionRecord, mission_id)
    # Same 404 for "missing" and "someone else's" so ids cannot be probed.
    if mission is None or mission.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mission not found.")
    return mission


def _owned_asset(db: Session, user: User, asset_id: str) -> AssetRecord:
    row = db.execute(
        select(AssetRecord)
        .join(MissionRecord, MissionRecord.id == AssetRecord.mission_id)
        .where(AssetRecord.id == asset_id, MissionRecord.owner_id == user.id)
    ).scalar_one_or_none()
    if row is None or row.status == AssetStatus.CANCELLED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    return row


@router.get("/missions", response_model=list[Mission])
def list_missions(user: UserDep, db: DbDep) -> list[Mission]:
    rows = db.scalars(
        select(MissionRecord)
        .where(MissionRecord.owner_id == user.id)
        .order_by(MissionRecord.created_at.desc())
    ).all()
    return [to_mission(db, r) for r in rows]


@router.post("/missions", response_model=Mission, status_code=status.HTTP_201_CREATED)
def create_mission(body: MissionCreate, user: UserDep, db: DbDep) -> Mission:
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the mission a name.")
    row = MissionRecord(owner_id=user.id, name=name)
    db.add(row)
    db.commit()
    return to_mission(db, row)


@router.get("/missions/{mission_id}", response_model=Mission)
def get_mission(mission_id: str, user: UserDep, db: DbDep) -> Mission:
    return to_mission(db, _owned_mission(db, user, mission_id))


@router.post(
    "/missions/{mission_id}/assets", response_model=Asset, status_code=status.HTTP_201_CREATED
)
def create_asset(
    mission_id: str, body: AssetCreate, user: UserDep, db: DbDep, settings: SettingsDep
) -> Asset:
    """Register an upload. The client then sends the bytes in chunks to `/content`."""
    mission = _owned_mission(db, user, mission_id)
    if body.kind is not AssetKind.VIDEO:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Telemetry import is not supported yet."
        )
    ext = video_extension(body.filename)
    if ext is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Unsupported file type. Upload an MP4, MOV, MKV, AVI or M4V video.",
        )
    limit = settings.max_upload_mb * 1024 * 1024
    if body.byte_size > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"The file is larger than the {settings.max_upload_mb} MB limit.",
        )
    existing = _current_video(db, mission.id)
    if existing is not None and existing.status in ACTIVE_VIDEO:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This mission already has a video. Remove it first."
        )
    row = AssetRecord(
        mission_id=mission.id,
        kind=AssetKind.VIDEO,
        filename=Path(body.filename).name[:255],
        stored_name=f"source{ext}",
        byte_size=body.byte_size,
        received_bytes=0,
        status=AssetStatus.UPLOADING,
    )
    db.add(row)
    db.commit()
    asset_dir(settings, mission.id, row.id).mkdir(parents=True, exist_ok=True)
    return to_asset(row)


@router.get("/assets/{asset_id}", response_model=Asset)
def get_asset(asset_id: str, user: UserDep, db: DbDep) -> Asset:
    return to_asset(_owned_asset(db, user, asset_id))


@router.put("/assets/{asset_id}/content", response_model=Asset)
async def upload_chunk(
    asset_id: str,
    request: Request,
    user: UserDep,
    db: DbDep,
    settings: SettingsDep,
    offset: int = Query(ge=0),
) -> Asset | Response:
    """Append one chunk at `offset`. Offsets must match the bytes already received, which
    makes retries safe: a 409 response carries the offset to resume from."""
    row = _owned_asset(db, user, asset_id)
    if row.status != AssetStatus.UPLOADING:
        raise HTTPException(status.HTTP_409_CONFLICT, "This upload is already complete.")
    if offset != row.received_bytes:
        return Response(
            content=to_asset(row).model_dump_json(),
            status_code=status.HTTP_409_CONFLICT,
            media_type="application/json",
        )

    max_chunk = settings.upload_chunk_max_mb * 1024 * 1024
    folder = asset_dir(settings, row.mission_id, row.id)
    folder.mkdir(parents=True, exist_ok=True)
    part = folder / UPLOAD_PART
    written = 0
    with part.open("ab") as fh:
        fh.truncate(row.received_bytes)  # drop bytes of an interrupted earlier attempt
        async for piece in request.stream():
            written += len(piece)
            if written > max_chunk or row.received_bytes + written > row.byte_size:
                fh.truncate(row.received_bytes)
                raise HTTPException(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "Chunk exceeds the declared file size or the chunk limit.",
                )
            fh.write(piece)
    row.received_bytes += written
    if row.received_bytes == row.byte_size:
        source = folder / row.stored_name
        os.replace(part, source)
        row.sha256 = sha256_file(source)
        row.status = AssetStatus.VALIDATING
        row.progress = {"phase": "queued", "completed": None, "total": None}
    db.commit()
    if row.status == AssetStatus.VALIDATING:
        request.app.state.processor.submit(row.id)
    return to_asset(row)


@router.post("/assets/{asset_id}/retry", response_model=Asset)
def retry_validation(asset_id: str, request: Request, user: UserDep, db: DbDep) -> Asset:
    row = _owned_asset(db, user, asset_id)
    if row.status != AssetStatus.FAILED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a failed validation can be retried.")
    row.status, row.error = AssetStatus.VALIDATING, None
    row.progress = {"phase": "queued", "completed": None, "total": None}
    db.commit()
    request.app.state.processor.submit(row.id)
    return to_asset(row)


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_asset(asset_id: str, user: UserDep, db: DbDep, settings: SettingsDep) -> None:
    """Cancel an upload/validation or remove a file. A running validation stops at its next
    checkpoint and cleans up its own files."""
    row = _owned_asset(db, user, asset_id)
    folder = asset_dir(settings, row.mission_id, row.id)
    if row.status == AssetStatus.VALIDATING:
        row.status, row.progress = AssetStatus.CANCELLED, None
        db.commit()
        return
    db.delete(row)
    db.commit()
    remove_tree(folder)


def _ready_dir(db: Session, user: User, asset_id: str, settings: SettingsDep) -> Path:
    row = _owned_asset(db, user, asset_id)
    if row.status != AssetStatus.READY:
        raise HTTPException(status.HTTP_409_CONFLICT, "Preflight is not available yet.")
    return asset_dir(settings, row.mission_id, row.id) / PREFLIGHT_DIR


@router.get("/assets/{asset_id}/preflight", response_model=PreflightReport)
def get_preflight(asset_id: str, user: UserDep, db: DbDep, settings: SettingsDep) -> Response:
    path = _ready_dir(db, user, asset_id, settings) / "preflight.json"
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preflight report not found.")
    return FileResponse(path, media_type="application/json")


@router.get("/assets/{asset_id}/{kind}/{number}.jpg")
def get_keyframe_image(
    asset_id: str, kind: str, number: int, user: UserDep, db: DbDep, settings: SettingsDep
) -> FileResponse:
    if kind not in ("thumbs", "keyframes") or not 1 <= number <= 9999:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found.")
    path = _ready_dir(db, user, asset_id, settings) / kind / f"{number:04d}.jpg"
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found.")
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )
