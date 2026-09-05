from fastapi import APIRouter, Depends, HTTPException, Request, Response

from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..audit import log_event
from ..auth import get_current_user, client_scope_or_none
from ..storage import verify_upload_token, save_file, read_file, file_exists

router = APIRouter(prefix="/v1/media", tags=["media"])


@router.put("/upload/{capture_id}")
async def upload_media(capture_id: str, request: Request, token: str, db: Session = Depends(get_db)):
    """No Bearer auth on this route by design — the signed, time-limited
    `token` query param IS the authorization, the same way a real S3
    pre-signed URL works. Anyone without this exact URL (capture ID + valid
    signature + not yet expired) gets rejected before any bytes are read."""
    if not verify_upload_token(capture_id, token):
        raise HTTPException(403, "upload link is invalid or has expired — request a new one via /v1/captures/init")

    capture = db.get(models.Capture, capture_id)
    if not capture:
        raise HTTPException(404, "capture not found")

    content = await request.body()
    if not content:
        raise HTTPException(400, "empty upload body")

    real_hash = save_file(capture_id, content)

    if real_hash != capture.content_hash:
        # the claimed hash from /captures/init doesn't match what was
        # actually uploaded — reject rather than silently trusting the claim
        log_event(db, "media_hash_mismatch", "capture", capture.id, actor="system:storage",
                   payload={"claimed_hash": capture.content_hash, "actual_hash": real_hash})
        db.commit()
        raise HTTPException(
            400,
            f"content hash mismatch: claimed {capture.content_hash}, actual upload hashes to {real_hash} — "
            "this capture cannot be verified until the uploaded bytes match what was declared",
        )

    log_event(db, "media_uploaded", "capture", capture.id, actor="system:storage",
              payload={"bytes": len(content), "hash": real_hash})
    db.commit()
    return {"capture_id": capture.id, "bytes_received": len(content), "hash_verified": True}


def _check_media_visible(user: models.User, capture: models.Capture, db: Session):
    if user.role in ("admin", "dispatcher"):
        return
    if user.role == "technician" and user.technician_id == capture.technician_id:
        return
    scope = client_scope_or_none(user)
    if scope:
        job = db.get(models.Job, capture.job_id)
        if job and job.site.client == scope:
            return
    raise HTTPException(403, "not authorized to view this media")


@router.get("/{capture_id}")
def get_media(capture_id: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    capture = db.get(models.Capture, capture_id)
    if not capture:
        raise HTTPException(404, "capture not found")
    _check_media_visible(user, capture, db)

    content = read_file(capture_id)
    if content is None:
        raise HTTPException(404, "no media uploaded for this capture yet")

    media_type = "image/png" if capture.capture_type == "photo" else "video/webm"
    return Response(content=content, media_type=media_type)


@router.get("/{capture_id}/status")
def media_status(capture_id: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lightweight existence check without transferring the file — used by
    /captures/{id}/complete's error message and by frontends that want to
    know upload status without downloading the whole payload."""
    capture = db.get(models.Capture, capture_id)
    if not capture:
        raise HTTPException(404, "capture not found")
    _check_media_visible(user, capture, db)
    return {"capture_id": capture_id, "uploaded": file_exists(capture_id)}
