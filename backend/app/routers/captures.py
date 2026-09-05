import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..audit import log_event
from ..verification import run_verification
from ..auth import get_current_user, check_technician_self, actor_label

router = APIRouter(prefix="/v1/captures", tags=["captures"])


def capture_to_dict(cap: models.Capture):
    return {
        "capture_id": cap.id,
        "job_id": cap.job_id,
        "technician_id": cap.technician_id,
        "checklist_item_id": cap.checklist_item_id,
        "capture_type": cap.capture_type,
        "capture_ts": cap.capture_ts.isoformat(),
        "status": cap.status,
        "checks": cap.checks,
        "checklist_item_satisfied": cap.checklist_item_id if cap.status == "verified" else None,
        "flag_reason": cap.flag_reason,
    }


@router.post("/init")
def init_capture(body: schemas.CaptureInitIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_technician_self(user, body.technician_id)
    job = db.get(models.Job, body.job_id)
    if not job:
        raise HTTPException(404, "job not found")
    tech = db.get(models.Technician, body.technician_id)
    if not tech:
        raise HTTPException(404, "technician not found")

    capture = models.Capture(
        job_id=job.id,
        technician_id=tech.id,
        checklist_item_id=body.checklist_item_id,
        capture_type=body.capture_type,
        content_hash=body.content_hash,
        capture_lat=body.capture_lat,
        capture_lng=body.capture_lng,
        capture_ts=body.capture_ts or dt.datetime.utcnow(),
        status="pending",
    )
    db.add(capture)
    db.flush()  # assigns capture.id via its default before we reference it below
    log_event(db, "capture_initiated", "capture", capture.id, actor=actor_label(user),
              payload={"job_id": job.id, "checklist_item_id": body.checklist_item_id})
    db.commit()
    db.refresh(capture)

    # in production this would return a pre-signed upload URL; the sandboxed
    # demo has no object storage, so /complete is called directly with no body.
    return {"capture_id": capture.id, "upload_url": f"mock://upload/{capture.id}", "expires_in": 300}


@router.post("/{capture_id}/complete")
def complete_capture(capture_id: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    capture = db.get(models.Capture, capture_id)
    if not capture:
        raise HTTPException(404, "capture not found")
    check_technician_self(user, capture.technician_id)

    result = run_verification(db, capture)
    capture.status = result["status"]
    capture.checks = result["checks"]
    capture.flag_reason = result["reason"]

    if result["status"] == "verified":
        log_event(db, "capture_verified", "capture", capture.id, actor="system:verification-engine",
                   payload={"checks": result["checks"]})
        if capture.checklist_item_id:
            item = db.get(models.ChecklistItem, capture.checklist_item_id)
            if item:
                item.satisfied_by_capture_id = capture.id
                item.completed_at = dt.datetime.utcnow()
                log_event(db, "checklist_item_satisfied", "checklist_item", item.id,
                          actor="system:verification-engine", payload={"capture_id": capture.id})

        job = capture.job
        remaining = [c for c in job.checklist_items if not c.satisfied_by_capture_id]
        if not remaining and job.status != "done":
            job.status = "done"
            job.completed_at = dt.datetime.utcnow()
            log_event(db, "job_completed", "job", job.id, actor="system:verification-engine", payload={})
    else:
        log_event(db, "capture_flagged", "capture", capture.id, actor="system:verification-engine",
                   payload={"reason": result["reason"], "checks": result["checks"]})

    db.commit()
    db.refresh(capture)
    return capture_to_dict(capture)


@router.get("/{capture_id}")
def get_capture(capture_id: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    capture = db.get(models.Capture, capture_id)
    if not capture:
        raise HTTPException(404, "capture not found")
    return capture_to_dict(capture)
