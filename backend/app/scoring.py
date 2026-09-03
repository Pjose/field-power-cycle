"""
Real implementation of the scoring shown in the assignment-scoring walkthrough.
Certification gating happens first (hard exclusion, not a low score), then the
remaining candidates are scored on proximity, current load, and SLA headroom.
"""
import datetime as dt

from sqlalchemy.orm import Session

from . import models
from .verification import haversine_distance_m

DEFAULT_WEIGHTS = {
    "proximity": 0.35,
    "current_load": 0.20,
    "sla_headroom": 0.20,
    "certification_match": 0.25,  # kept in the output even though it's gate-then-1.0, for weight parity with the UI
}

AVG_SPEED_MPS = 11.0  # ~25mph average, used to turn distance into a rough ETA


def job_requires_cert(job: models.Job) -> str | None:
    """Very small mapping of job type -> required cert type, mirroring the
    'req-tags' shown on the scoring tool's ticket card."""
    t = job.job_type.lower()
    if "pos" in t or "kiosk" in t or "checkout" in t:
        return "pos"
    if "payment" in t:
        return "payment"
    if "cat6" in t or "cabling" in t or "rack" in t:
        return "network"
    return None


def technician_has_valid_cert(tech: models.Technician, cert_type: str) -> bool:
    if not cert_type:
        return True
    for c in (tech.certifications or []):
        if c.get("type") == cert_type and c.get("state") == "valid":
            return True
    return False


def score_candidates(db: Session, job: models.Job, weights: dict = None) -> list[dict]:
    weights = weights or DEFAULT_WEIGHTS
    site = job.site
    required_cert = job_requires_cert(job)

    technicians = db.query(models.Technician).filter(models.Technician.status == "active").all()

    # current load: how many active (non-done) jobs each technician already carries
    load_counts = {}
    for t in technicians:
        active_jobs = (
            db.query(models.Job)
            .filter(models.Job.assigned_technician_id == t.id, models.Job.status.in_(["queued", "enroute", "onsite"]))
            .count()
        )
        load_counts[t.id] = active_jobs
    max_load = max(load_counts.values()) if load_counts else 1
    max_load = max(max_load, 1)

    results = []
    for t in technicians:
        eligible = technician_has_valid_cert(t, required_cert)

        distance_m = None
        eta_min = None
        proximity_score = 0.0
        if t.lat is not None and t.lng is not None:
            distance_m = haversine_distance_m(t.lat, t.lng, site.lat, site.lng)
            eta_min = round((distance_m / AVG_SPEED_MPS) / 60, 1)
            # proximity score decays with distance; 0m -> 1.0, ~15km -> ~0
            proximity_score = max(0.0, 1 - (distance_m / 15000))

        load_score = 1 - (load_counts.get(t.id, 0) / max_load)

        sla_headroom_score = 1.0
        active_jobs_q = (
            db.query(models.Job)
            .filter(models.Job.assigned_technician_id == t.id, models.Job.status.in_(["queued", "enroute", "onsite"]))
            .all()
        )
        now = dt.datetime.utcnow()
        for aj in active_jobs_q:
            if aj.sla_deadline:
                minutes_left = (aj.sla_deadline - now).total_seconds() / 60
                if minutes_left < 30:
                    sla_headroom_score -= 0.3
        sla_headroom_score = max(0.0, min(1.0, sla_headroom_score))

        components = {
            "proximity": round(proximity_score, 3),
            "current_load": round(load_score, 3),
            "sla_headroom": round(sla_headroom_score, 3),
            "certification_match": 1.0 if eligible else 0.0,
        }

        if not eligible:
            score = None
        else:
            score = round(
                weights["proximity"] * components["proximity"]
                + weights["current_load"] * components["current_load"]
                + weights["sla_headroom"] * components["sla_headroom"]
                + weights["certification_match"] * components["certification_match"],
                3,
            )

        results.append({
            "technician_id": t.id,
            "name": t.name,
            "eligible": eligible,
            "required_cert": required_cert,
            "distance_m": round(distance_m, 0) if distance_m is not None else None,
            "eta_min": eta_min,
            "components": components,
            "score": score,
        })

    results.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    return results
