"""
The missing link between "a rule fired" (already real — the audit event
exists) and "something actually got sent" (now also real, for email and
SMS). This is deliberately a thin layer: look up the rule by name, look up
a real recipient address on the User table, call the real provider, and
log exactly what happened — delivered or not, and why.
"""
from sqlalchemy.orm import Session

from . import models
from .audit import log_event
from .notification_providers import send_email, send_sms


def _find_rule(db: Session, name: str) -> models.NotificationRule | None:
    return db.query(models.NotificationRule).filter(models.NotificationRule.name == name).first()


def notify_client_job_completed(db: Session, job: models.Job):
    rule = _find_rule(db, "Job completed & verified")
    if not rule or not rule.enabled:
        return
    contact = (
        db.query(models.User)
        .filter(models.User.role == "client", models.User.client_name == job.site.client)
        .first()
    )
    to = contact.email if contact else None
    subject = f"Completion report ready — {job.id}"
    body = (
        f"Your {job.job_type} job at {job.site.name} is complete and fully verified. "
        f"No signature or paperwork is needed on your end — every checklist item was "
        f"satisfied by field-verified photo/video proof, timestamped and geofenced to "
        f"the job site. View the full report in your Field PowerCycle portal."
    )
    result = send_email(to, subject, body)
    log_event(
        db, "notification_dispatched", "job", job.id, actor="system:notification-engine",
        payload={"rule": "Job completed & verified", "channel": "email", **result},
    )


def notify_technician_recapture(db: Session, capture: models.Capture, reason: str):
    rule = _find_rule(db, "Recapture requested")
    if not rule or not rule.enabled:
        return
    tech = db.get(models.Technician, capture.technician_id)
    tech_user = (
        db.query(models.User)
        .filter(models.User.role == "technician", models.User.technician_id == capture.technician_id)
        .first()
    )
    to = tech_user.phone if tech_user else None
    body = f"Field PowerCycle: a capture on {capture.job_id} was rejected — {reason or 'please recapture.'}"
    result = send_sms(to, body)
    log_event(
        db, "notification_dispatched", "capture", capture.id, actor="system:notification-engine",
        payload={"rule": "Recapture requested", "channel": "sms", **result},
    )
