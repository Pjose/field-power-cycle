"""
Turns a live analytics summary into a persisted row, and runs that on a
schedule so a trend chart has real history to plot instead of narrating
that it doesn't exist.

In a real deployment this fires once a day via cron, Celery beat, or a
cloud scheduler — the interval below is compressed for demo purposes
(SNAPSHOT_INTERVAL_MINUTES) so a trend actually accumulates during a
normal development session instead of requiring literal days of uptime.
That compression is stated here, not hidden — nothing about the snapshot
data itself is fabricated; only the frequency is sped up.
"""
import logging
import threading
import time

from sqlalchemy.orm import Session

from . import models
from .analytics_core import compute_summary
from .database import SessionLocal

logger = logging.getLogger("fpc.analytics_snapshot")

SNAPSHOT_INTERVAL_MINUTES = 5  # compressed for demo; a real deployment sets this to 1440 (daily)


def take_snapshot(db: Session) -> models.AnalyticsSnapshot:
    s = compute_summary(db)
    snap = models.AnalyticsSnapshot(
        jobs_total=s["jobs_total"], jobs_done=s["jobs_done"],
        sla_compliance_pct=s["sla_compliance_pct"], avg_response_min=s["avg_response_min"],
        captures_total=s["captures_total"], captures_verified=s["captures_verified"],
        captures_flagged_open=s["captures_flagged_open"], captures_resolved=s["captures_resolved"],
        auto_verify_pct=s["auto_verify_pct"],
        jobs_by_type=s["jobs_by_type"], jobs_by_industry=s["jobs_by_industry"],
        technician_leaderboard=s["technician_leaderboard"],
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    logger.info("analytics snapshot taken: %s jobs_done=%s sla=%s%%",
                snap.id, snap.jobs_done, snap.sla_compliance_pct)
    return snap


def _scheduler_loop(stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            db = SessionLocal()
            try:
                take_snapshot(db)
            finally:
                db.close()
        except Exception:
            logger.exception("scheduled analytics snapshot failed")
        stop_event.wait(SNAPSHOT_INTERVAL_MINUTES * 60)


_stop_event = None
_thread = None


def start_background_scheduler():
    """Called once from main.py's startup event. Runs in a plain daemon
    thread rather than pulling in APScheduler/Celery — appropriate for a
    single-process reference deployment; a real multi-worker production
    deployment should run this as a separate scheduled job/worker instead
    of in-process, to avoid every worker process taking its own snapshot."""
    global _stop_event, _thread
    if _thread is not None:
        return
    _stop_event = threading.Event()
    _thread = threading.Thread(target=_scheduler_loop, args=(_stop_event,), daemon=True)
    _thread.start()
    logger.info("analytics snapshot scheduler started (every %s min)", SNAPSHOT_INTERVAL_MINUTES)
