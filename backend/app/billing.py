"""
Turns a completed job into real invoice line items. Labor hours are computed
from arrived_at -> completed_at on the job record (which itself is only ever
set by real status-change events), not typed in by anyone.
"""
import datetime as dt

RATE_CARDS = {
    "standard":  {"hourly": 95.0,  "dispatch_fee": 45.0, "materials_markup": 0.12, "after_hours_mult": 1.5},
    "priority":  {"hourly": 115.0, "dispatch_fee": 65.0, "materials_markup": 0.12, "after_hours_mult": 1.5},
    "emergency": {"hourly": 150.0, "dispatch_fee": 95.0, "materials_markup": 0.15, "after_hours_mult": 2.0},
    "scheduled": {"hourly": 85.0,  "dispatch_fee": 0.0,  "materials_markup": 0.10, "after_hours_mult": 1.5},
}

TAX_RATE = 0.0825


def build_invoice(job, materials=None):
    materials = materials or []
    tier = (job.sla_tier or "standard").lower()
    card = RATE_CARDS.get(tier, RATE_CARDS["standard"])

    if not job.arrived_at or not job.completed_at:
        raise ValueError("Job must have both arrived_at and completed_at to invoice")

    hours = round((job.completed_at - job.arrived_at).total_seconds() / 3600, 2)
    labor = round(hours * card["hourly"], 2)
    dispatch_fee = card["dispatch_fee"]

    materials_subtotal = round(sum(m["qty"] * m["unit_price"] for m in materials), 2)
    materials_markup = round(materials_subtotal * card["materials_markup"], 2)

    line_items = [
        {"description": "Dispatch fee", "source": f"flat · {tier} tier", "qty": 1, "rate": dispatch_fee, "amount": dispatch_fee},
        {"description": "Field labor", "source": "audit trail: arrival → completion timestamps", "qty": hours, "rate": card["hourly"], "amount": labor},
    ]
    for m in materials:
        line_items.append({
            "description": m["name"], "source": "materials — logged on job",
            "qty": m["qty"], "rate": m["unit_price"], "amount": round(m["qty"] * m["unit_price"], 2),
        })
    if materials_subtotal:
        line_items.append({
            "description": "Materials markup", "source": f"{int(card['materials_markup']*100)}% per rate card",
            "qty": None, "rate": None, "amount": materials_markup,
        })

    subtotal = round(dispatch_fee + labor + materials_subtotal + materials_markup, 2)
    tax = round(subtotal * TAX_RATE, 2)
    total = round(subtotal + tax, 2)

    return {
        "hours": hours,
        "tier": tier,
        "line_items": line_items,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
    }
