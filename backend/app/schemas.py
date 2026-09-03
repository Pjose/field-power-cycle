import datetime as dt
from typing import Optional, List, Dict, Any

from pydantic import BaseModel


class LocationPingIn(BaseModel):
    technician_id: str
    lat: float
    lng: float
    accuracy_m: float = 10.0
    device_ts: Optional[dt.datetime] = None


class LocationPingOut(BaseModel):
    received_ts: dt.datetime
    geofence_event: Optional[Dict[str, Any]] = None


class JobAssignIn(BaseModel):
    technician_id: str
    assigned_by: str = "dispatcher"
    override_score: bool = False


class CaptureInitIn(BaseModel):
    job_id: str
    technician_id: str
    checklist_item_id: Optional[str] = None
    capture_type: str = "photo"
    content_hash: str
    capture_lat: float
    capture_lng: float
    capture_ts: Optional[dt.datetime] = None


class CaptureCompleteIn(BaseModel):
    pass


class ReviewResolveIn(BaseModel):
    resolution: str  # approved | rejected
    resolved_by: str
    note: Optional[str] = None


class NotificationRuleToggleIn(BaseModel):
    enabled: bool


class MaterialLine(BaseModel):
    name: str
    qty: float
    unit_price: float


class InvoiceGenerateIn(BaseModel):
    materials: List[MaterialLine] = []
