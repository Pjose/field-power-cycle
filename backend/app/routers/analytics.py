from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..auth import require_roles
from ..analytics_core import compute_summary

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])


@router.get("/summary")
def analytics_summary(user: models.User = Depends(require_roles("admin", "dispatcher")),
                       db: Session = Depends(get_db)):
    """Real aggregation over whatever is actually in the database right now.
    For real historical trends over time, see GET /v1/analytics/history —
    this endpoint is always the current, live total."""
    return compute_summary(db)


@router.get("/history")
def analytics_history(limit: int = 30,
                       user: models.User = Depends(require_roles("admin", "dispatcher")),
                       db: Session = Depends(get_db)):
    """Real persisted snapshots, oldest first — this is what makes an
    honest trend line possible. See app/analytics_snapshot.py for how
    snapshots get taken."""
    snaps = (
        db.query(models.AnalyticsSnapshot)
        .order_by(models.AnalyticsSnapshot.taken_at.desc())
        .limit(limit)
        .all()
    )
    snaps = list(reversed(snaps))
    return [
        {
            "id": s.id, "taken_at": s.taken_at.isoformat(),
            "jobs_total": s.jobs_total, "jobs_done": s.jobs_done,
            "sla_compliance_pct": s.sla_compliance_pct, "avg_response_min": s.avg_response_min,
            "captures_total": s.captures_total, "captures_verified": s.captures_verified,
            "captures_flagged_open": s.captures_flagged_open, "captures_resolved": s.captures_resolved,
            "auto_verify_pct": s.auto_verify_pct,
            "jobs_by_type": s.jobs_by_type, "jobs_by_industry": s.jobs_by_industry,
            "technician_leaderboard": s.technician_leaderboard,
        }
        for s in snaps
    ]


@router.post("/snapshot")
def take_snapshot_now(user: models.User = Depends(require_roles("admin", "dispatcher")),
                       db: Session = Depends(get_db)):
    """Manually trigger a snapshot — in a real deployment this same logic
    runs on a schedule (see app/analytics_snapshot.py's background job),
    but exposing it as an endpoint too makes it demonstrable and testable
    on demand rather than only ever firing invisibly on a timer."""
    from ..analytics_snapshot import take_snapshot
    snap = take_snapshot(db)
    return {"id": snap.id, "taken_at": snap.taken_at.isoformat()}
