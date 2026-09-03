from sqlalchemy.orm import Session
from . import models


def log_event(db: Session, event_type: str, entity_type: str, entity_id: str, actor: str = "system", payload: dict = None):
    """Every meaningful state change in the app goes through this. No update/
    delete is ever exposed on AuditEvent anywhere in the API — it's append-only
    by construction, not just convention."""
    evt = models.AuditEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        payload=payload or {},
    )
    db.add(evt)
    db.flush()
    return evt
