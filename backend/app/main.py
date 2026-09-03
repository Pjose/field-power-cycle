from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models
from .database import engine, get_db, Base
from .seed import seed
from .routers import locations, jobs, captures, review, notifications, invoices, analytics

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

app.include_router(locations.router)
app.include_router(jobs.router)
app.include_router(captures.router)
app.include_router(review.router)
app.include_router(notifications.router)
app.include_router(notifications.feed_router)
app.include_router(invoices.router)
app.include_router(analytics.router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    seed(db)


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
def list_sites(db: Session = Depends(get_db)):
    sites = db.query(models.Site).all()
    return [
        {"id": s.id, "name": s.name, "client": s.client, "address": s.address,
         "lat": s.lat, "lng": s.lng, "geofence_radius_m": s.geofence_radius_m}
        for s in sites
    ]


@app.patch("/v1/sites/{site_id}")
def update_site(site_id: str, body: dict, db: Session = Depends(get_db)):
    site = db.get(models.Site, site_id)
    if not site:
        return {"error": "site not found"}
    if "geofence_radius_m" in body:
        old = site.geofence_radius_m
        site.geofence_radius_m = body["geofence_radius_m"]
        from .audit import log_event
        log_event(db, "site_geofence_updated", "site", site.id, actor="dispatcher:settings",
                   payload={"old_radius_m": old, "new_radius_m": body["geofence_radius_m"]})
        db.commit()
    return {"id": site.id, "geofence_radius_m": site.geofence_radius_m}


@app.get("/v1/technicians")
def list_technicians(db: Session = Depends(get_db)):
    techs = db.query(models.Technician).all()
    return [
        {
            "id": t.id, "name": t.name, "status": t.status,
            "lat": t.lat, "lng": t.lng, "active_job_id": t.active_job_id,
            "certifications": t.certifications, "hourly_rate": t.hourly_rate,
            "onboarding_steps": t.onboarding_steps,
        }
        for t in techs
    ]


@app.get("/v1/audit-events")
def list_audit_events(entity_id: str = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(models.AuditEvent)
    if entity_id:
        q = q.filter(models.AuditEvent.entity_id == entity_id)
    events = q.order_by(models.AuditEvent.ts.desc()).limit(limit).all()
    return [
        {"id": e.id, "event_type": e.event_type, "entity_type": e.entity_type,
         "entity_id": e.entity_id, "actor": e.actor, "ts": e.ts.isoformat(), "payload": e.payload}
        for e in events
    ]
