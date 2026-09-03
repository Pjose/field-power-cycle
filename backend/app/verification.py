"""
The verification engine. This is the part every frontend prototype narrated
("Verifying... GPS matched geofence") but never actually computed. Here it's
real: an actual haversine distance calculation against the job's site radius,
a real timestamp window check against when the job was dispatched, and a real
duplicate-hash lookup across every prior capture in the database.
"""
import math
import datetime as dt

from sqlalchemy.orm import Session

from . import models


EARTH_RADIUS_M = 6371000


def haversine_distance_m(lat1, lng1, lat2, lng2):
    """Great-circle distance between two lat/lng points, in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_M * c


def check_geofence(capture_lat, capture_lng, site, radius_override=None):
    radius = radius_override or site.geofence_radius_m or 120
    distance = haversine_distance_m(capture_lat, capture_lng, site.lat, site.lng)
    return {
        "pass": distance <= radius,
        "distance_m": round(distance, 1),
        "radius_m": radius,
    }


def check_timestamp_window(capture_ts: dt.datetime, job: models.Job):
    """Capture must fall between dispatch and now (jobs aren't retroactively
    proven with photos taken before the technician was even sent)."""
    window_start = job.dispatched_at or job.created_at
    now = dt.datetime.utcnow()
    ok = window_start is not None and window_start <= capture_ts <= now
    return {
        "pass": ok,
        "window_start": window_start.isoformat() if window_start else None,
        "capture_ts": capture_ts.isoformat(),
    }


def check_duplicate_hash(db: Session, content_hash: str, exclude_capture_id: str = None):
    q = db.query(models.Capture).filter(models.Capture.content_hash == content_hash)
    if exclude_capture_id:
        q = q.filter(models.Capture.id != exclude_capture_id)
    prior = q.first()
    return {
        "pass": prior is None,
        "matched_capture_id": prior.id if prior else None,
        "matched_job_id": prior.job_id if prior else None,
    }


def run_verification(db: Session, capture: models.Capture) -> dict:
    """Runs all checks and returns the combined result. Does not commit —
    caller decides how to persist it."""
    job = capture.job
    site = job.site

    geofence = check_geofence(capture.capture_lat, capture.capture_lng, site)
    timestamp_window = check_timestamp_window(capture.capture_ts, job)
    duplicate_hash = check_duplicate_hash(db, capture.content_hash, exclude_capture_id=capture.id)

    checks = {
        "geofence": geofence,
        "timestamp_window": timestamp_window,
        "duplicate_hash": duplicate_hash,
    }

    all_pass = geofence["pass"] and timestamp_window["pass"] and duplicate_hash["pass"]

    if all_pass:
        return {"status": "verified", "checks": checks, "reason": None}

    reasons = []
    if not geofence["pass"]:
        reasons.append(
            f"Capture is {geofence['distance_m']:.0f}m from the job site — outside the "
            f"{geofence['radius_m']}m geofence."
        )
    if not timestamp_window["pass"]:
        reasons.append("Capture timestamp falls outside the job's active work window.")
    if not duplicate_hash["pass"]:
        reasons.append(
            f"This exact file was already submitted on job {duplicate_hash['matched_job_id']}."
        )

    return {"status": "flagged", "checks": checks, "reason": " ".join(reasons)}
