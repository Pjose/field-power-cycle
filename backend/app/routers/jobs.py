import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..audit import log_event
from ..scoring import score_candidates
from ..auth import get_current_user, require_roles, client_scope_or_none, actor_label

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


def job_to_dict(job: models.Job):
    return {
        "id": job.id,
        "site": {"id": job.site.id, "name": job.site.name, "client": job.site.client, "lat": job.site.lat, "lng": job.site.lng},
        "job_type": job.job_type,
        "status": job.status,
        "sla_tier": job.sla_tier,
        "sla_deadline": job.sla_deadline.isoformat() if job.sla_deadline else None,
        "sla_minutes_remaining": (
            round((job.sla_deadline - dt.datetime.utcnow()).total_seconds() / 60, 1) if job.sla_deadline else None
        ),
        "assigned_technician_id": job.assigned_technician_id,
        "dispatched_at": job.dispatched_at.isoformat() if job.dispatched_at else None,
        "arrived_at": job.arrived_at.isoformat() if job.arrived_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "checklist": [
            {"id": c.id, "label": c.label, "satisfied_by_capture_id": c.satisfied_by_capture_id,
             "completed_at": c.completed_at.isoformat() if c.completed_at else None}
            for c in job.checklist_items
        ],
    }


def check_job_visible(user: models.User, job: models.Job):
    """Client-role users can only see jobs belonging to their own client —
    enforced here, not just left to the frontend to behave itself."""
    scope = client_scope_or_none(user)
    if scope and job.site.client != scope:
        raise HTTPException(403, "not authorized to view this job")


@router.get("")
def list_jobs(status: str = None, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(models.Job)
    if status:
        statuses = status.split(",")
        q = q.filter(models.Job.status.in_(statuses))
    jobs = q.all()
    scope = client_scope_or_none(user)
    if scope:
        jobs = [j for j in jobs if j.site.client == scope]
    return [job_to_dict(j) for j in jobs]


@router.get("/{job_id}")
def get_job(job_id: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    check_job_visible(user, job)
    return job_to_dict(job)


@router.get("/{job_id}/candidates")
def get_candidates(job_id: str, user: models.User = Depends(require_roles("admin", "dispatcher")),
                    db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return {"job_id": job_id, "candidates": score_candidates(db, job)}


@router.get("/{job_id}/captures")
def list_job_captures(job_id: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    check_job_visible(user, job)
    return [
        {
            "capture_id": c.id, "checklist_item_id": c.checklist_item_id,
            "capture_type": c.capture_type, "capture_ts": c.capture_ts.isoformat(),
            "status": c.status, "checks": c.checks, "flag_reason": c.flag_reason,
        }
        for c in job.captures
    ]


@router.post("/{job_id}/assign")
def assign_job(job_id: str, body: schemas.JobAssignIn,
                user: models.User = Depends(require_roles("admin", "dispatcher")),
                db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    tech = db.get(models.Technician, body.technician_id)
    if not tech:
        raise HTTPException(404, "technician not found")

    job.assigned_technician_id = tech.id
    job.status = "enroute"
    job.dispatched_at = dt.datetime.utcnow()
    tech.active_job_id = job.id

    # actor is the real authenticated identity, not whatever the client claimed in the body
    log_event(db, "job_assigned", "job", job.id, actor=actor_label(user),
              payload={"technician_id": tech.id, "override_score": body.override_score})
    log_event(db, "job_status_changed", "job", job.id, actor=actor_label(user),
              payload={"to_status": "enroute"})

    db.commit()
    return job_to_dict(job)
