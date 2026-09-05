import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..verification import haversine_distance_m
from ..audit import log_event
from ..auth import get_current_user, check_technician_self, actor_label

router = APIRouter(prefix="/v1/locations", tags=["locations"])


@router.post("/ping", response_model=schemas.LocationPingOut)
def post_ping(body: schemas.LocationPingIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_technician_self(user, body.technician_id)
    tech = db.get(models.Technician, body.technician_id)
    if not tech:
        raise HTTPException(404, "technician not found")

    device_ts = body.device_ts or dt.datetime.utcnow()
    received_ts = dt.datetime.utcnow()

    ping = models.LocationPing(
        technician_id=tech.id, lat=body.lat, lng=body.lng,
        accuracy_m=body.accuracy_m, device_ts=device_ts, received_ts=received_ts,
    )
    db.add(ping)

    # was the technician inside their active job's geofence before this ping?
    was_inside = None
    is_inside = None
    geofence_event = None

    if tech.active_job_id:
        job = db.get(models.Job, tech.active_job_id)
        if job:
            site = job.site
            if tech.lat is not None and tech.lng is not None:
                prev_dist = haversine_distance_m(tech.lat, tech.lng, site.lat, site.lng)
                was_inside = prev_dist <= (site.geofence_radius_m or 120)
            new_dist = haversine_distance_m(body.lat, body.lng, site.lat, site.lng)
            is_inside = new_dist <= (site.geofence_radius_m or 120)

            if was_inside is False and is_inside is True:
                geofence_event = {"type": "entered", "job_id": job.id, "distance_m": round(new_dist, 1)}
                log_event(db, "geofence_entered", "job", job.id, actor=actor_label(user),
                          payload={"distance_m": round(new_dist, 1)})
                if job.status == "enroute":
                    job.status = "onsite"
                    job.arrived_at = received_ts
            elif was_inside is True and is_inside is False:
                geofence_event = {"type": "exited", "job_id": job.id, "distance_m": round(new_dist, 1)}
                log_event(db, "geofence_exited", "job", job.id, actor=actor_label(user),
                          payload={"distance_m": round(new_dist, 1)})

    tech.lat = body.lat
    tech.lng = body.lng
    tech.last_ping_at = received_ts

    log_event(db, "location_ping_received", "technician", tech.id,
              actor=actor_label(user), payload={"lat": body.lat, "lng": body.lng})

    db.commit()
    return schemas.LocationPingOut(received_ts=received_ts, geofence_event=geofence_event)
