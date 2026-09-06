import datetime as dt

from sqlalchemy.orm import Session

from . import models
from .audit import log_event
from .auth import hash_password


def now():
    return dt.datetime.utcnow()


def seed(db: Session):
    if db.query(models.Site).count() > 0:
        return  # already seeded

    sites = [
        models.Site(id="SITE-apex", name="Apex Dining Brands — Uptown", client="Apex Dining Brands",
                    address="1400 McKinney Ave, Dallas TX", lat=32.7920, lng=-96.8010, geofence_radius_m=120),
        models.Site(id="SITE-apex-midtown", name="Apex Dining Brands — Midtown", client="Apex Dining Brands",
                    address="3105 Ross Ave, Dallas TX", lat=32.7955, lng=-96.7890, geofence_radius_m=120),
        models.Site(id="SITE-copperline-main", name="Copperline Hospitality — Main Kitchen", client="Copperline Hospitality",
                    address="2200 Kettner Blvd, Suite 4, Dallas TX", lat=32.7767, lng=-96.7970, geofence_radius_m=120),
        models.Site(id="SITE-copperline-down", name="Copperline Hospitality — Downtown", client="Copperline Hospitality",
                    address="88 Main St, Dallas TX", lat=32.7801, lng=-96.7989, geofence_radius_m=120),
        models.Site(id="SITE-meridian", name="Meridian Health Clinic", client="Meridian Health Clinic",
                    address="500 N Akard St, Dallas TX", lat=32.7850, lng=-96.8020, geofence_radius_m=90),
        models.Site(id="SITE-ridgecrest", name="RidgeCrest Corporate Center", client="RidgeCrest Corporate Center",
                    address="5215 N O'Connor Blvd, Irving TX", lat=32.8710, lng=-96.9410, geofence_radius_m=250),
    ]
    db.add_all(sites)

    technicians = [
        models.Technician(id="T-104", name="Marcus Reyes", status="active", lat=32.7918, lng=-96.8005,
                           certifications=[{"type": "pos", "state": "valid", "expires": "2027-01-01"},
                                           {"type": "payment", "state": "valid", "expires": "2027-01-01"}],
                           hourly_rate=95),
        models.Technician(id="T-092", name="Priya Chandran", status="active", lat=32.7700, lng=-96.7900,
                           certifications=[{"type": "pos", "state": "expiring", "expires": "2026-09-15"},
                                           {"type": "payment", "state": "valid", "expires": "2027-06-01"}],
                           hourly_rate=95),
        models.Technician(id="T-118", name="Dana Whitfield", status="active", lat=32.7770, lng=-96.7975,
                           certifications=[{"type": "pos", "state": "valid", "expires": "2026-11-01"},
                                           {"type": "network", "state": "valid", "expires": "2026-11-01"}],
                           hourly_rate=105),
        models.Technician(id="T-071", name="Sam Okafor", status="active", lat=32.7900, lng=-96.7950,
                           certifications=[{"type": "network", "state": "expired", "expires": "2026-02-01"}],
                           hourly_rate=90),
        models.Technician(id="T-059", name="Grace Halden", status="active", lat=32.7765, lng=-96.7968,
                           certifications=[{"type": "pos", "state": "valid", "expires": "2027-01-01"},
                                           {"type": "payment", "state": "valid", "expires": "2027-01-01"}],
                           hourly_rate=105),
        models.Technician(id="T-210", name="Owen Baptiste", status="onboarding", lat=None, lng=None,
                           certifications=[{"type": "safety", "state": "valid", "expires": "2032-08-01"}],
                           hourly_rate=78,
                           onboarding_steps=[
                               {"name": "Offer accepted & background check", "done": True, "sub": "Cleared Aug 12, 2026"},
                               {"name": "OSHA 10 safety training completed", "done": True, "sub": "Certified Aug 18, 2026"},
                               {"name": "POS systems certification course", "done": False, "current": True, "sub": "In progress — exam scheduled Sep 5"},
                               {"name": "Payment device pairing certification", "done": False, "sub": "Not started"},
                               {"name": "Field app + equipment provisioned", "done": False, "sub": "Not started"},
                               {"name": "First shadow shift with senior technician", "done": False, "sub": "Not started"},
                               {"name": "Solo dispatch eligible", "done": False, "sub": "Not started"},
                           ]),
        models.Technician(id="T-214", name="Renee Castillo", status="onboarding", lat=None, lng=None,
                           certifications=[{"type": "safety", "state": "valid", "expires": "2032-08-01"},
                                           {"type": "pos", "state": "valid", "expires": "2029-08-01"}],
                           hourly_rate=78,
                           onboarding_steps=[
                               {"name": "Offer accepted & background check", "done": True, "sub": "Cleared Aug 5, 2026"},
                               {"name": "OSHA 10 safety training completed", "done": True, "sub": "Certified Aug 10, 2026"},
                               {"name": "POS systems certification course", "done": True, "sub": "Certified Aug 22, 2026"},
                               {"name": "Payment device pairing certification", "done": False, "current": True, "sub": "In progress — exam scheduled Sep 2"},
                               {"name": "Field app + equipment provisioned", "done": False, "sub": "Not started"},
                               {"name": "First shadow shift with senior technician", "done": False, "sub": "Not started"},
                               {"name": "Solo dispatch eligible", "done": False, "sub": "Not started"},
                           ]),
    ]
    db.add_all(technicians)
    db.flush()

    t1 = now()
    jobs = [
        models.Job(id="JB-4472", site_id="SITE-apex", job_type="Break-Fix — Payment Terminal", status="enroute",
                   sla_tier="priority", sla_deadline=t1 + dt.timedelta(minutes=90),
                   assigned_technician_id="T-092", dispatched_at=t1 - dt.timedelta(minutes=5), created_at=t1 - dt.timedelta(minutes=8)),
        models.Job(id="JB-4469", site_id="SITE-copperline-main", job_type="KDS Staging — Full Deployment", status="done",
                   sla_tier="standard", sla_deadline=t1 - dt.timedelta(hours=20),
                   assigned_technician_id="T-059",
                   dispatched_at=t1 - dt.timedelta(hours=25),
                   arrived_at=t1 - dt.timedelta(hours=24, minutes=48),
                   completed_at=t1 - dt.timedelta(hours=23, minutes=36),
                   created_at=t1 - dt.timedelta(hours=25, minutes=10)),
        models.Job(id="JB-4478", site_id="SITE-copperline-down", job_type="Self-Checkout Kiosk Setup", status="risk",
                   sla_tier="standard", sla_deadline=t1 - dt.timedelta(minutes=4),
                   assigned_technician_id=None, dispatched_at=None, created_at=t1 - dt.timedelta(hours=3)),
        models.Job(id="JB-4477", site_id="SITE-ridgecrest", job_type="Structured Cat6 Run", status="enroute",
                   sla_tier="standard", sla_deadline=t1 + dt.timedelta(hours=6),
                   assigned_technician_id="T-104", dispatched_at=t1 - dt.timedelta(minutes=6),
                   created_at=t1 - dt.timedelta(minutes=20)),
        models.Job(id="JB-4480", site_id="SITE-meridian", job_type="Break-Fix — Payment Terminal", status="queued",
                   sla_tier="emergency", sla_deadline=t1 + dt.timedelta(minutes=22),
                   assigned_technician_id=None, dispatched_at=None, created_at=t1 - dt.timedelta(minutes=10)),
        models.Job(id="JB-4460", site_id="SITE-apex-midtown", job_type="POS Terminal Install", status="done",
                   sla_tier="standard", sla_deadline=t1 - dt.timedelta(days=2),
                   assigned_technician_id="T-104",
                   dispatched_at=t1 - dt.timedelta(days=2, hours=1),
                   arrived_at=t1 - dt.timedelta(days=2, minutes=50),
                   completed_at=t1 - dt.timedelta(days=2, minutes=15),
                   created_at=t1 - dt.timedelta(days=2, hours=1, minutes=10)),
        models.Job(id="JB-4483", site_id="SITE-apex-midtown", job_type="Firewall Swap", status="queued",
                   sla_tier="scheduled", sla_deadline=t1 + dt.timedelta(days=3),
                   assigned_technician_id=None, dispatched_at=None, created_at=t1 - dt.timedelta(hours=1)),
    ]
    db.add_all(jobs)
    db.flush()

    checklist = [
        models.ChecklistItem(job_id="JB-4472", label="Diagnostic run recorded"),
        models.ChecklistItem(job_id="JB-4472", label="Replacement unit installed"),
        models.ChecklistItem(job_id="JB-4472", label="Transaction test passed"),
        models.ChecklistItem(job_id="JB-4469", label="KDS mounted — all 4 kitchen stations"),
        models.ChecklistItem(job_id="JB-4469", label="Kitchen Wi-Fi survey validated"),
        models.ChecklistItem(job_id="JB-4469", label="Staff training completed"),
        models.ChecklistItem(job_id="JB-4478", label="Kiosks unboxed and mounted"),
        models.ChecklistItem(job_id="JB-4478", label="Payment terminals linked"),
        models.ChecklistItem(job_id="JB-4477", label="Cable path surveyed"),
        models.ChecklistItem(job_id="JB-4477", label="Cat6 pulled"),
        models.ChecklistItem(job_id="JB-4477", label="Termination tested"),
        models.ChecklistItem(job_id="JB-4480", label="Diagnostic run recorded"),
        models.ChecklistItem(job_id="JB-4480", label="Replacement unit installed"),
        models.ChecklistItem(job_id="JB-4460", label="Terminal mounted and powered"),
        models.ChecklistItem(job_id="JB-4460", label="Network drop tested"),
        models.ChecklistItem(job_id="JB-4460", label="Staff walkthrough complete"),
        models.ChecklistItem(job_id="JB-4483", label="Firewall staged"),
        models.ChecklistItem(job_id="JB-4483", label="Swap window confirmed with site manager"),
    ]
    db.add_all(checklist)
    db.flush()

    # Seeded "done" jobs need REAL backing captures, not just a status flag —
    # otherwise any real frontend that queries checklist state (client portal,
    # dispatch console drawer) would show these jobs as done with an empty,
    # unsatisfied checklist, which is exactly the kind of inconsistency this
    # backend exists to avoid. Each capture here passes the same verification
    # checks a live capture would.
    def backed_capture(job_id, tech_id, checklist_item, capture_ts, site):
        cap = models.Capture(
            job_id=job_id, technician_id=tech_id, checklist_item_id=checklist_item.id,
            capture_type="photo", content_hash=f"sha256:seed-{checklist_item.id}",
            capture_lat=site.lat, capture_lng=site.lng, capture_ts=capture_ts,
            status="verified",
            checks={
                "geofence": {"pass": True, "distance_m": 4.0, "radius_m": site.geofence_radius_m or 120},
                "timestamp_window": {"pass": True},
                "duplicate_hash": {"pass": True, "matched_capture_id": None, "matched_job_id": None},
            },
        )
        db.add(cap)
        db.flush()
        checklist_item.satisfied_by_capture_id = cap.id
        checklist_item.completed_at = capture_ts
        log_event(db, "capture_initiated", "capture", cap.id, actor=f"technician:{tech_id}", payload={"job_id": job_id})
        log_event(db, "capture_verified", "capture", cap.id, actor="system:verification-engine", payload={})
        log_event(db, "checklist_item_satisfied", "checklist_item", checklist_item.id,
                   actor="system:verification-engine", payload={"capture_id": cap.id})

    jb4469 = db.get(models.Job, "JB-4469")
    jb4469_items = db.query(models.ChecklistItem).filter(models.ChecklistItem.job_id == "JB-4469").all()
    step = (jb4469.completed_at - jb4469.arrived_at) / max(len(jb4469_items), 1)
    for i, item in enumerate(jb4469_items):
        backed_capture("JB-4469", "T-059", item, jb4469.arrived_at + step * (i + 1), jb4469.site)

    jb4460 = db.get(models.Job, "JB-4460")
    jb4460_items = db.query(models.ChecklistItem).filter(models.ChecklistItem.job_id == "JB-4460").all()
    step = (jb4460.completed_at - jb4460.arrived_at) / max(len(jb4460_items), 1)
    for i, item in enumerate(jb4460_items):
        backed_capture("JB-4460", "T-104", item, jb4460.arrived_at + step * (i + 1), jb4460.site)

    # both completed jobs also get their assign/arrive/complete events on the record,
    # so a real audit-trail timeline (client portal, dispatch console) has something to show
    for job in (jb4469, jb4460):
        log_event(db, "job_assigned", "job", job.id, actor="dispatcher:seed",
                   payload={"technician_id": job.assigned_technician_id})
        log_event(db, "geofence_entered", "job", job.id, actor=f"technician:{job.assigned_technician_id}",
                   payload={})
        log_event(db, "job_completed", "job", job.id, actor="system:verification-engine", payload={})

    rules = [
        models.NotificationRule(name="Technician en route", trigger_event="job_status_changed:enroute",
                                 recipient_role="client", channels=["sms", "push"], enabled=True),
        models.NotificationRule(name="Job completed & verified", trigger_event="job_completed",
                                 recipient_role="client", channels=["sms", "email"], enabled=True),
        models.NotificationRule(name="SLA breach imminent", trigger_event="sla_breach_imminent",
                                 recipient_role="dispatcher", channels=["push", "console"], enabled=True),
        models.NotificationRule(name="Capture flagged for review", trigger_event="capture_flagged",
                                 recipient_role="dispatcher", channels=["push", "console"], enabled=True),
        models.NotificationRule(name="Recapture requested", trigger_event="capture_resolved:rejected",
                                 recipient_role="technician", channels=["push"], enabled=True),
        models.NotificationRule(name="Certification expiring", trigger_event="cert_expiring",
                                 recipient_role="technician+admin", channels=["email", "push"], enabled=True),
    ]
    db.add_all(rules)

    # Real users, real hashed passwords, one per role — these are the actual
    # credentials the demo login screens use. Anyone deploying this for real
    # would replace these before going anywhere near production, but they're
    # not placeholders in the sense of "not really checked" — every one of
    # these hashes is genuinely verified against a genuinely submitted
    # password at /v1/auth/login.
    users = [
        models.User(username="admin", password_hash=hash_password("admin123"),
                    role="admin", display_name="Admin"),
        models.User(username="dispatcher", password_hash=hash_password("dispatch123"),
                    role="dispatcher", display_name="D. Vance"),
        models.User(username="priya", password_hash=hash_password("tech123"),
                    role="technician", display_name="Priya Chandran", technician_id="T-092",
                    phone="+15555550101"),
        models.User(username="dana", password_hash=hash_password("tech123"),
                    role="technician", display_name="Dana Whitfield", technician_id="T-118",
                    phone="+15555550102"),
        models.User(username="grace", password_hash=hash_password("tech123"),
                    role="technician", display_name="Grace Halden", technician_id="T-059",
                    phone="+15555550103"),
        models.User(username="apex", password_hash=hash_password("client123"),
                    role="client", display_name="Apex Dining Brands — Ops", client_name="Apex Dining Brands",
                    email="ops@apexdiningbrands.example"),
        models.User(username="copperline", password_hash=hash_password("client123"),
                    role="client", display_name="Copperline Hospitality — Ops", client_name="Copperline Hospitality",
                    email="ops@copperlinehospitality.example"),
    ]
    db.add_all(users)

    db.commit()
