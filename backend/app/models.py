import datetime as dt
import uuid

from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship

from .database import Base


def now():
    return dt.datetime.utcnow()


def gen_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class Site(Base):
    __tablename__ = "sites"
    id = Column(String, primary_key=True, default=lambda: gen_id("SITE"))
    name = Column(String, nullable=False)
    client = Column(String, nullable=False)
    address = Column(String)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    geofence_radius_m = Column(Integer, default=120)  # overridable per-site (Settings > Geofencing)

    jobs = relationship("Job", back_populates="site")


class Technician(Base):
    __tablename__ = "technicians"
    id = Column(String, primary_key=True, default=lambda: gen_id("T"))
    name = Column(String, nullable=False)
    role = Column(String, default="Field Technician")
    status = Column(String, default="active")  # active | onboarding | inactive
    certifications = Column(JSON, default=list)  # [{"type": "pos", "state": "valid", "expires": "..."}]
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    last_ping_at = Column(DateTime, nullable=True)
    active_job_id = Column(String, ForeignKey("jobs.id"), nullable=True)
    hourly_rate = Column(Float, default=95.0)
    onboarding_steps = Column(JSON, nullable=True)  # null for fully active techs; list of steps while onboarding

    location_pings = relationship("LocationPing", back_populates="technician")


class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True, default=lambda: gen_id("JB"))
    site_id = Column(String, ForeignKey("sites.id"), nullable=False)
    job_type = Column(String, nullable=False)
    status = Column(String, default="queued")  # queued|enroute|onsite|done|risk
    sla_tier = Column(String, default="standard")
    sla_deadline = Column(DateTime, nullable=True)
    assigned_technician_id = Column(String, ForeignKey("technicians.id"), nullable=True)
    dispatched_at = Column(DateTime, nullable=True)
    arrived_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now)

    site = relationship("Site", back_populates="jobs")
    checklist_items = relationship("ChecklistItem", back_populates="job", cascade="all, delete-orphan")
    captures = relationship("Capture", back_populates="job", cascade="all, delete-orphan")


class ChecklistItem(Base):
    __tablename__ = "checklist_items"
    id = Column(String, primary_key=True, default=lambda: gen_id("CHK"))
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    label = Column(String, nullable=False)
    satisfied_by_capture_id = Column(String, ForeignKey("captures.id"), nullable=True)
    completed_at = Column(DateTime, nullable=True)

    job = relationship("Job", back_populates="checklist_items")


class LocationPing(Base):
    __tablename__ = "location_pings"
    id = Column(String, primary_key=True, default=lambda: gen_id("PING"))
    technician_id = Column(String, ForeignKey("technicians.id"), nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    accuracy_m = Column(Float, default=10.0)
    device_ts = Column(DateTime, default=now)
    received_ts = Column(DateTime, default=now)

    technician = relationship("Technician", back_populates="location_pings")


class Capture(Base):
    __tablename__ = "captures"
    id = Column(String, primary_key=True, default=lambda: gen_id("CAP"))
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    technician_id = Column(String, ForeignKey("technicians.id"), nullable=False)
    checklist_item_id = Column(String, ForeignKey("checklist_items.id"), nullable=True)
    capture_type = Column(String, default="photo")  # photo | video
    content_hash = Column(String, nullable=False)
    capture_lat = Column(Float, nullable=False)
    capture_lng = Column(Float, nullable=False)
    capture_ts = Column(DateTime, default=now)
    status = Column(String, default="pending")  # pending | verified | flagged | resolved_approved | resolved_rejected
    checks = Column(JSON, default=dict)  # {geofence: {...}, timestamp_window: {...}, duplicate_hash: {...}}
    flag_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now)

    job = relationship("Job", back_populates="captures")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(String, primary_key=True, default=lambda: gen_id("EVT"))
    event_type = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    actor = Column(String, default="system")
    payload = Column(JSON, default=dict)
    ts = Column(DateTime, default=now)
    # append-only by convention: no update/delete exposed anywhere in the API


class NotificationRule(Base):
    __tablename__ = "notification_rules"
    id = Column(String, primary_key=True, default=lambda: gen_id("RULE"))
    name = Column(String, nullable=False)
    trigger_event = Column(String, nullable=False)
    recipient_role = Column(String, nullable=False)
    channels = Column(JSON, default=list)
    enabled = Column(Boolean, default=True)


class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(String, primary_key=True, default=lambda: gen_id("INV"))
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    client = Column(String, nullable=False)
    line_items = Column(JSON, default=list)
    subtotal = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    status = Column(String, default="draft")  # draft | sent | paid | overdue
    issued_at = Column(DateTime, default=now)
    due_at = Column(DateTime, nullable=True)


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: gen_id("USR"))
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # admin | dispatcher | technician | client
    display_name = Column(String, nullable=False)
    technician_id = Column(String, ForeignKey("technicians.id"), nullable=True)  # set when role == technician
    client_name = Column(String, nullable=True)  # set when role == client — scopes visibility to this client's jobs
    active = Column(Boolean, default=True)
    email = Column(String, nullable=True)  # real delivery target for send_email()
    phone = Column(String, nullable=True)  # real delivery target for send_sms()


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    id = Column(String, primary_key=True, default=lambda: gen_id("SNAP"))
    taken_at = Column(DateTime, default=now)
    # a persisted copy of what GET /v1/analytics/summary computes live —
    # this is what makes a real trend line possible instead of narrating
    # that one isn't available. See app/analytics_snapshot.py.
    jobs_total = Column(Integer)
    jobs_done = Column(Integer)
    sla_compliance_pct = Column(Float, nullable=True)
    avg_response_min = Column(Float, nullable=True)
    captures_total = Column(Integer)
    captures_verified = Column(Integer)
    captures_flagged_open = Column(Integer)
    captures_resolved = Column(Integer)
    auto_verify_pct = Column(Float, nullable=True)
    jobs_by_type = Column(JSON, default=dict)
    jobs_by_industry = Column(JSON, default=dict)
    technician_leaderboard = Column(JSON, default=list)
