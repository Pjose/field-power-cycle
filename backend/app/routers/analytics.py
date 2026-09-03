import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])


@router.get("/summary")
def analytics_summary(db: Session = Depends(get_db)):
    """Real aggregation over whatever is actually in the database right now.
    There's no historical time-series here — this backend doesn't retain
    superseded snapshots, so there's nothing honest to plot as a multi-week
    trend. Everything below is a real, current, all-time total instead."""
    jobs = db.query(models.Job).all()
    techs = db.query(models.Technician).filter(models.Technician.status == "active").all()
    captures = db.query(models.Capture).all()

    jobs_done = [j for j in jobs if j.status == "done" and j.completed_at]
    sla_compliant = [j for j in jobs_done if j.sla_deadline and j.completed_at <= j.sla_deadline]
    sla_compliance_pct = round(len(sla_compliant) / len(jobs_done) * 100) if jobs_done else None

    response_times = [
        (j.arrived_at - j.dispatched_at).total_seconds() / 60
        for j in jobs if j.arrived_at and j.dispatched_at
    ]
    avg_response_min = round(sum(response_times) / len(response_times)) if response_times else None

    verified = [c for c in captures if c.status == "verified"]
    flagged_now = [c for c in captures if c.status == "flagged"]
    resolved = [c for c in captures if c.status in ("resolved_approved", "resolved_rejected")]
    auto_verify_pct = round(len(verified) / len(captures) * 100) if captures else None

    jobs_by_type = {}
    for j in jobs:
        jobs_by_type[j.job_type] = jobs_by_type.get(j.job_type, 0) + 1

    # crude, honestly-labeled industry bucketing from the client's own name —
    # not a stored field, just a readable heuristic for the donut chart
    def industry_for(client):
        c = client.lower()
        if "hospitality" in c or "dining" in c: return "Hospitality"
        if "health" in c or "clinic" in c or "medical" in c: return "Healthcare"
        if "retail" in c or "shop" in c: return "Retail"
        return "Corporate"

    jobs_by_industry = {}
    for j in jobs:
        ind = industry_for(j.site.client)
        jobs_by_industry[ind] = jobs_by_industry.get(ind, 0) + 1

    leaderboard = []
    for t in techs:
        their_jobs = [j for j in jobs if j.assigned_technician_id == t.id]
        their_done = [j for j in their_jobs if j.status == "done" and j.completed_at]
        their_ontime = [j for j in their_done if j.sla_deadline and j.completed_at <= j.sla_deadline]
        ontime_pct = round(len(their_ontime) / len(their_done) * 100) if their_done else None
        durations = [(j.completed_at - j.arrived_at).total_seconds()/60 for j in their_done if j.arrived_at]
        avg_duration = round(sum(durations)/len(durations)) if durations else None
        their_captures = [c for c in captures if c.technician_id == t.id]
        flagged_count = len([c for c in their_captures if c.status in ("flagged","resolved_approved","resolved_rejected")])
        leaderboard.append({
            "id": t.id, "name": t.name, "jobs_done": len(their_done),
            "ontime_pct": ontime_pct, "avg_duration_min": avg_duration, "flagged_count": flagged_count,
        })
    leaderboard.sort(key=lambda x: (x["ontime_pct"] is None, -(x["ontime_pct"] or 0)))

    return {
        "jobs_total": len(jobs),
        "jobs_done": len(jobs_done),
        "sla_compliance_pct": sla_compliance_pct,
        "avg_response_min": avg_response_min,
        "captures_total": len(captures),
        "captures_verified": len(verified),
        "captures_flagged_open": len(flagged_now),
        "captures_resolved": len(resolved),
        "auto_verify_pct": auto_verify_pct,
        "jobs_by_type": jobs_by_type,
        "jobs_by_industry": jobs_by_industry,
        "technician_leaderboard": leaderboard,
    }
