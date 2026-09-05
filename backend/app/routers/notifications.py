from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..audit import log_event
from ..auth import require_roles, actor_label

router = APIRouter(prefix="/v1/notification-rules", tags=["notifications"])


@router.get("")
def list_rules(user: models.User = Depends(require_roles("admin", "dispatcher")), db: Session = Depends(get_db)):
    return [
        {"id": r.id, "name": r.name, "trigger_event": r.trigger_event,
         "recipient_role": r.recipient_role, "channels": r.channels, "enabled": r.enabled}
        for r in db.query(models.NotificationRule).all()
    ]


@router.patch("/{rule_id}")
def toggle_rule(rule_id: str, body: schemas.NotificationRuleToggleIn,
                 user: models.User = Depends(require_roles("admin", "dispatcher")),
                 db: Session = Depends(get_db)):
    rule = db.get(models.NotificationRule, rule_id)
    if not rule:
        raise HTTPException(404, "rule not found")
    rule.enabled = body.enabled
    log_event(db, "notification_rule_toggled", "notification_rule", rule.id,
              actor=actor_label(user), payload={"enabled": body.enabled})
    db.commit()
    return {"id": rule.id, "enabled": rule.enabled}


feed_router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


@feed_router.get("/feed")
def notification_feed(limit: int = 50, user: models.User = Depends(require_roles("admin", "dispatcher")),
                       db: Session = Depends(get_db)):
    """Surfaces every audit event that corresponds to a notification-worthy
    moment, newest first — this is what the Notification Center's live feed
    would poll or subscribe to."""
    events = (
        db.query(models.AuditEvent)
        .filter(models.AuditEvent.event_type.in_([
            "job_assigned", "job_status_changed", "job_completed",
            "capture_flagged", "capture_resolved", "notification_dispatched",
        ]))
        .order_by(models.AuditEvent.ts.desc())
        .limit(limit)
        .all()
    )
    return [
        {"id": e.id, "event_type": e.event_type, "entity_type": e.entity_type,
         "entity_id": e.entity_id, "actor": e.actor, "ts": e.ts.isoformat(), "payload": e.payload}
        for e in events
    ]
