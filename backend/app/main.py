from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models
from .database import engine, get_db, Base
from .seed import seed
from .auth import get_current_user, require_roles, actor_label
from .routers import locations, jobs, captures, review, notifications, invoices, analytics, media, auth as auth_router

app = FastAPI(
    title="Field PowerCycle API",
    description="Reference implementation of the architecture and API contract docs: "
                 "real geofence math, real timestamp-based verification, real billing "
                 "calculations — running against a real (SQLite) database instead of "
                 "hardcoded frontend mock data.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local prototype only — tighten before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(locations.router)
app.include_router(jobs.router)
app.include_router(captures.router)
app.include_router(review.router)
app.include_router(notifications.router)
app.include_router(notifications.feed_router)
app.include_router(invoices.router)
app.include_router(analytics.router)
app.include_router(media.router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    seed(db)
    from .analytics_snapshot import start_background_scheduler
    start_background_scheduler()


@app.get("/")
def root():
    return {
        "service": "field-powercycle-api",
        "status": "ok",
        "docs": "/docs",
        "note": "This is the reference backend for the Field PowerCycle prototype suite. "
                "See field-powercycle-architecture.md and field-powercycle-api-contract.md.",
    }


@app.get("/v1/sites")
def list_sites(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    sites = db.query(models.Site).all()
    return [
        {"id": s.id, "name": s.name, "client": s.client, "address": s.address,
         "lat": s.lat, "lng": s.lng, "geofence_radius_m": s.geofence_radius_m}
        for s in sites
    ]


@app.patch("/v1/sites/{site_id}")
def update_site(site_id: str, body: dict,
                 user: models.User = Depends(require_roles("admin", "dispatcher")),
                 db: Session = Depends(get_db)):
    site = db.get(models.Site, site_id)
    if not site:
        raise HTTPException(404, "site not found")
    if "geofence_radius_m" in body:
        old = site.geofence_radius_m
        site.geofence_radius_m = body["geofence_radius_m"]
        from .audit import log_event
        log_event(db, "site_geofence_updated", "site", site.id, actor=actor_label(user),
                   payload={"old_radius_m": old, "new_radius_m": body["geofence_radius_m"]})
        db.commit()
    return {"id": site.id, "geofence_radius_m": site.geofence_radius_m}


@app.get("/v1/technicians")
def list_technicians(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    techs = db.query(models.Technician).all()
    # client-role users can see technician names/positions (needed for live tracking)
    # but not certifications or pay rate — that's internal workforce data
    is_client = user.role == "client"
    return [
        {
            "id": t.id, "name": t.name, "status": t.status,
            "lat": t.lat, "lng": t.lng, "active_job_id": t.active_job_id,
            "certifications": None if is_client else t.certifications,
            "hourly_rate": None if is_client else t.hourly_rate,
            "onboarding_steps": None if is_client else t.onboarding_steps,
        }
        for t in techs
    ]


@app.get("/v1/audit-events")
def list_audit_events(entity_id: str = None, limit: int = 100,
                       user: models.User = Depends(require_roles("admin", "dispatcher")),
                       db: Session = Depends(get_db)):
    q = db.query(models.AuditEvent)
    if entity_id:
        q = q.filter(models.AuditEvent.entity_id == entity_id)
    events = q.order_by(models.AuditEvent.ts.desc()).limit(limit).all()
    return [
        {"id": e.id, "event_type": e.event_type, "entity_type": e.entity_type,
         "entity_id": e.entity_id, "actor": e.actor, "ts": e.ts.isoformat(), "payload": e.payload}
        for e in events
    ]
