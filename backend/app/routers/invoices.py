import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..audit import log_event
from ..billing import build_invoice
from ..auth import require_roles, actor_label

router = APIRouter(prefix="/v1/invoices", tags=["invoices"])


@router.get("/queue")
def invoice_queue(user: models.User = Depends(require_roles("admin", "dispatcher")), db: Session = Depends(get_db)):
    """Jobs that are done, have real arrival/completion timestamps, and don't
    already have an invoice — exactly the set the Billing tool's queue shows."""
    invoiced_job_ids = {i.job_id for i in db.query(models.Invoice).all()}
    jobs = (
        db.query(models.Job)
        .filter(models.Job.status == "done", models.Job.arrived_at.isnot(None), models.Job.completed_at.isnot(None))
        .all()
    )
    out = []
    for j in jobs:
        if j.id in invoiced_job_ids:
            continue
        hours = round((j.completed_at - j.arrived_at).total_seconds() / 3600, 2)
        out.append({
            "job_id": j.id, "job_type": j.job_type, "client": j.site.client,
            "site": j.site.name, "hours": hours, "sla_tier": j.sla_tier,
            "completed_at": j.completed_at.isoformat(),
        })
    return out


@router.post("/generate/{job_id}")
def generate_invoice(job_id: str, body: schemas.InvoiceGenerateIn,
                      user: models.User = Depends(require_roles("admin", "dispatcher")),
                      db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if db.query(models.Invoice).filter(models.Invoice.job_id == job_id).first():
        raise HTTPException(400, "job is already invoiced")

    try:
        result = build_invoice(job, materials=[m.model_dump() for m in body.materials])
    except ValueError as e:
        raise HTTPException(400, str(e))

    invoice = models.Invoice(
        job_id=job.id, client=job.site.client,
        line_items=result["line_items"], subtotal=result["subtotal"],
        tax=result["tax"], total=result["total"],
        status="draft", due_at=dt.datetime.utcnow() + dt.timedelta(days=30),
    )
    db.add(invoice)
    db.flush()  # assigns invoice.id via its default before we reference it below
    log_event(db, "invoice_generated", "invoice", invoice.id, actor=actor_label(user),
              payload={"job_id": job.id, "total": result["total"]})
    db.commit()
    db.refresh(invoice)

    return {
        "invoice_id": invoice.id, "job_id": job.id, "client": invoice.client,
        "hours": result["hours"], "tier": result["tier"],
        "line_items": invoice.line_items, "subtotal": invoice.subtotal,
        "tax": invoice.tax, "total": invoice.total, "status": invoice.status,
    }


@router.get("")
def list_invoices(user: models.User = Depends(require_roles("admin", "dispatcher")), db: Session = Depends(get_db)):
    invoices = db.query(models.Invoice).all()
    return [
        {"invoice_id": i.id, "job_id": i.job_id, "client": i.client,
         "total": i.total, "status": i.status,
         "issued_at": i.issued_at.isoformat(), "due_at": i.due_at.isoformat() if i.due_at else None}
        for i in invoices
    ]


@router.post("/{invoice_id}/send")
def send_invoice(invoice_id: str, user: models.User = Depends(require_roles("admin", "dispatcher")),
                  db: Session = Depends(get_db)):
    invoice = db.get(models.Invoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "invoice not found")
    invoice.status = "sent"
    log_event(db, "invoice_sent", "invoice", invoice.id, actor=actor_label(user), payload={})
    db.commit()
    return {"invoice_id": invoice.id, "status": invoice.status}
