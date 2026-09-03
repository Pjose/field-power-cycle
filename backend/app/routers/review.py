import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..audit import log_event

router = APIRouter(tags=["review"])


@router.get("/v1/review-queue")
def review_queue(status: str = "open", db: Session = Depends(get_db)):
    q = db.query(models.Capture)
    if status == "open":
        q = q.filter(models.Capture.status == "flagged")
    else:
        q = q.filter(models.Capture.status.in_(["resolved_approved", "resolved_rejected"]))
    captures = q.all()
    return [
        {
            "capture_id": c.id, "job_id": c.job_id, "technician_id": c.technician_id,
            "capture_ts": c.capture_ts.isoformat(), "status": c.status,
            "checks": c.checks, "reason": c.flag_reason,
        }
        for c in captures
    ]


@router.post("/v1/captures/{capture_id}/resolve")
def resolve_capture(capture_id: str, body: schemas.ReviewResolveIn, db: Session = Depends(get_db)):
    capture = db.get(models.Capture, capture_id)
    if not capture:
        raise HTTPException(404, "capture not found")
    if capture.status != "flagged":
        raise HTTPException(400, "capture is not currently flagged")
    if body.resolution not in ("approved", "rejected"):
        raise HTTPException(400, "resolution must be 'approved' or 'rejected'")

    capture.status = f"resolved_{body.resolution}"
    log_event(db, "capture_resolved", "capture", capture.id, actor=body.resolved_by,
              payload={"resolution": body.resolution, "note": body.note})

    if body.resolution == "approved" and capture.checklist_item_id:
        item = db.get(models.ChecklistItem, capture.checklist_item_id)
        if item and not item.satisfied_by_capture_id:
            item.satisfied_by_capture_id = capture.id
            item.completed_at = dt.datetime.utcnow()
            log_event(db, "checklist_item_satisfied", "checklist_item", item.id,
                       actor=body.resolved_by, payload={"capture_id": capture.id, "via": "dispatcher_approval"})
            job = capture.job
            remaining = [c for c in job.checklist_items if not c.satisfied_by_capture_id]
            if not remaining and job.status != "done":
                job.status = "done"
                job.completed_at = dt.datetime.utcnow()
                log_event(db, "job_completed", "job", job.id, actor=body.resolved_by, payload={})
    elif body.resolution == "rejected":
        log_event(db, "notification_dispatched", "capture", capture.id, actor="system:notification-engine",
                   payload={"rule": "Recapture requested", "recipient": capture.technician_id})

    db.commit()
    return {"capture_id": capture.id, "status": capture.status}
