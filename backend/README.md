# Field PowerCycle — Reference Backend

This is a real, runnable implementation of the logic described in
`field-powercycle-architecture.md` and `field-powercycle-api-contract.md`.
Every other artifact in the prototype suite (dispatch console, technician app,
client portal, etc.) uses hardcoded JavaScript arrays for its data — this is
the piece that replaces "pretend this is real" with an actual database and
actual computation.

## What's real here

- **A real database.** SQLite via SQLAlchemy, with the same entities described
  in the architecture doc: sites, technicians, jobs, checklist items, location
  pings, captures, audit events, notification rules, invoices.
- **Real geofence math.** `app/verification.py` computes actual haversine
  great-circle distance between a capture's GPS coordinates and the job
  site's coordinates, compared against the site's real radius — not a
  hardcoded "verified" flag.
- **A real verification engine.** Every capture is checked against geofence,
  timestamp window, and duplicate content-hash — all three run for real, and
  a capture that fails any of them is flagged with the actual reason and
  actual numbers (e.g. `"Capture is 775m from the job site — outside the
  120m geofence."`), not a canned string.
- **Real geofence-crossing detection.** `POST /v1/locations/ping` compares a
  technician's previous and new position against their active job's site and
  fires a real `entered`/`exited` event — and a real `entered` event flips
  the job to `onsite`, exactly as narrated in the console prototype.
- **Real assignment scoring.** `app/scoring.py` hard-excludes technicians
  without a valid certification for the job type (not just a low score), then
  scores the rest on real distance-derived proximity, real current job load
  from the database, and real SLA headroom on their existing assignments.
- **Real billing math.** `app/billing.py` computes labor hours as the actual
  difference between a job's `arrived_at` and `completed_at` timestamps —
  numbers that are only ever set by real status-change logic, never typed in
  — then applies the rate card, materials, markup, and tax.
- **A real append-only audit log.** Every meaningful action writes to
  `AuditEvent` via `app/audit.py`. No route anywhere updates or deletes an
  audit event.
- **A real, auto-generated API contract.** Run the server and visit `/docs`
  for live OpenAPI/Swagger docs generated from the actual code — the
  `field-powercycle-api-contract.md` doc describes the target shape; this is
  the executable version of it.

## What's still a stand-in

This is a backend for a prototype suite, not a production deployment. Notably
not implemented:

- **Object storage.** `/v1/captures/init` returns a mock `upload_url`
  instead of a real S3/GCS pre-signed URL, and `/complete` doesn't expect an
  actual file — there's no media storage layer here.
- **Auth.** Every endpoint is open. The API contract describes bearer-token
  scoping per technician/dispatcher; none of that is enforced yet.
- **Real SMS/email/push delivery.** The notification *rules* are modeled and
  toggleable, and every trigger condition writes a real audit event, but
  nothing calls out to Twilio/SendGrid/APNs. `GET /v1/notifications/feed`
  surfaces the audit events that *would* have fired a notification.
- **Frontend wiring — all eleven done.** Every HTML prototype in the suite
  now attempts to load real data from `http://127.0.0.1:8000` on open, and
  falls back to embedded demo data if the backend isn't reachable — a
  connection badge somewhere in each UI shows which mode it's in.

  **The core operational loop** (dispatcher → technician → client → billing → scoring):
  - **Dispatch console** — live map, job drawer with real captures and a
    real audit-event timeline, review queue Approve/Reject calling real
    endpoints.
  - **Technician app** — loads JB-4472's real checklist, tries
    `navigator.geolocation` for an actual device fix, runs real captures
    through the real verification engine.
  - **Client portal** — resolves its own client identity from real job
    data, polls the assigned technician's real GPS for a real ETA. Proven
    end-to-end: a capture made through the technician app's real flow
    caused the portal's next poll to show the job as completed.
  - **Billing** — real invoice queue, real invoice generation from actual
    job timestamps, client-side rate math confirmed to match the server to
    the cent.
  - **Assignment Scoring** — real candidates for an actual unassigned
    ticket, real certification gating, client-side re-ranking against real
    component values, real assignment persisted on click.

  **The administrative layer** (workforce → notifications → settings → analytics):
  - **Workforce admin** — real certifications, a real `onboarding_steps`
    field added to the Technician model with two genuinely-seeded
    onboarding technicians, "jobs completed" and "on-time rate" computed
    client-side from real job history rather than fabricated.
  - **Notifications** — real rule enabled/disabled state (6 of 8 rules
    matched to real backend rows by name; 2 without a backend equivalent
    stay local-only, clearly), a real feed built from actual audit events
    with real recipients resolved via job/technician lookups. Live feed
    rows are marked `"logged"`, not `"delivered"` — this backend doesn't
    track real SMS/push receipts, and the UI doesn't pretend otherwise.
  - **Settings** — added `GET /v1/sites` and `PATCH /v1/sites/{id}` so the
    geofencing panel is genuinely live and editable: change a radius in
    the UI and it persists immediately, with a real audit event
    (`site_geofence_updated`) logged. Every other panel (business hours,
    SLA tier targets, client portal-access toggles, integrations) has no
    real backing store in this prototype and is left as static reference
    — stated plainly rather than half-wired.
  - **Analytics** — added `GET /v1/analytics/summary`, a real server-side
    aggregation (SLA compliance, avg response time, verification funnel,
    jobs by type, a heuristic jobs-by-industry bucketing from client name,
    and a technician leaderboard) computed fresh from whatever's actually
    in the database. The one thing intentionally *not* faked: the SLA
    trend chart and 7D/30D/90D range toggle. This backend keeps live
    state, not historical snapshots, so there's no honest multi-week trend
    to plot — live mode shows the current compliance number plainly and
    disables the range toggle rather than fabricating a line chart.

  Two real bugs surfaced and fixed during this process: `job_to_dict()`
  never exposed a job's own `completed_at`/`arrived_at` at the top level
  (only nested inside checklist items), and the originally-seeded "done"
  jobs had a status flag but no real `Capture` rows backing their
  checklists — both fixed rather than worked around.
- **Device signing.** The API contract describes a `device_signature` binding
  GPS/timestamp to a capture at the moment of shutter-press. This backend
  accepts a `content_hash` but doesn't verify a real cryptographic signature.

## Running it

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Then visit `http://localhost:8000/docs` for interactive API docs, or
`http://localhost:8000/` for a health check. The database (`fieldpowercycle.db`)
is created and seeded automatically on first startup with the same sites,
technicians, and jobs used across the other prototypes (Apex Dining Brands,
Copperline Hospitality, Marcus Reyes, Priya Chandran, etc.) so IDs and names
line up if you cross-reference against the frontend mockups.

Delete `fieldpowercycle.db` to reset to a clean seeded state.

## A worked example

This is the actual sequence exercised while building this backend, runnable
against a fresh database:

```bash
# 1. Score candidates for an unassigned ticket — certification-gated, real distance
curl http://localhost:8000/v1/jobs/JB-4478/candidates

# 2. Assign it to the top candidate
curl -X POST http://localhost:8000/v1/jobs/JB-4478/assign \
  -H "Content-Type: application/json" \
  -d '{"technician_id":"T-118","assigned_by":"dispatcher:D-Vance"}'

# 3. Technician's GPS crosses into the site geofence — job auto-flips to onsite
curl -X POST http://localhost:8000/v1/locations/ping \
  -H "Content-Type: application/json" \
  -d '{"technician_id":"T-118","lat":32.7900,"lng":-96.7900}'
curl -X POST http://localhost:8000/v1/locations/ping \
  -H "Content-Type: application/json" \
  -d '{"technician_id":"T-118","lat":32.7801,"lng":-96.7989}'

# 4. Capture proof inside the geofence — auto-verifies, satisfies the checklist item
curl -X POST http://localhost:8000/v1/captures/init \
  -H "Content-Type: application/json" \
  -d '{"job_id":"JB-4478","technician_id":"T-118","capture_type":"photo",
       "content_hash":"sha256:aaa111","capture_lat":32.7801,"capture_lng":-96.7989}'
curl -X POST http://localhost:8000/v1/captures/<capture_id>/complete

# 5. Once a job has real arrived_at/completed_at timestamps, generate an invoice
curl -X POST http://localhost:8000/v1/invoices/generate/JB-4469 \
  -H "Content-Type: application/json" \
  -d '{"materials":[{"name":"KDS mounting hardware kit","qty":4,"unit_price":38}]}'
```

## Project layout

```
backend/
  requirements.txt
  app/
    main.py           FastAPI app, route registration, startup/seed, /v1/technicians, /v1/sites, /v1/audit-events
    database.py        SQLAlchemy engine/session
    models.py           ORM models — the real data model from the architecture doc
    schemas.py           Pydantic request/response shapes
    verification.py       Geofence + timestamp + duplicate-hash checks (haversine math)
    scoring.py              Assignment candidate scoring
    billing.py                Invoice line-item calculation
    audit.py                   Append-only event logging helper
    seed.py                     Seed data matching the frontend prototypes
    routers/
      locations.py               GPS ping ingestion + geofence crossing
      jobs.py                     Job queue, assignment, candidate scoring
      captures.py                 Capture init/complete — runs the verification engine
      review.py                    Dispatcher review queue for flagged captures
      notifications.py             Rule toggling + audit-backed activity feed
      invoices.py                   Billing queue, invoice generation, invoice list
      analytics.py                  Real aggregation: KPIs, funnel, jobs by type/industry, leaderboard
```
