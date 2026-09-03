# Field PowerCycle — API Contract
### Technician app ⇄ backend ⇄ dispatch console

Companion to the architecture doc. This defines the actual request/response shapes for the flows shown in both prototypes. REST for CRUD-style calls, WebSocket for anything that needs to be live (location, verification results, review queue updates). All REST bodies are JSON; all timestamps are ISO 8601 UTC.

Auth isn't detailed here — assume a bearer token per technician/dispatcher session, scoped so a technician can only write to jobs assigned to them.

---

## 1. Location ingestion

### `POST /v1/locations/ping`
Sent every 10–15s by the technician app while a shift is active.

**Request**
```json
{
  "technician_id": "T-104",
  "device_ts": "2026-08-31T15:24:01.402Z",
  "lat": 32.77681,
  "lng": -96.79701,
  "accuracy_m": 8.2,
  "heading_deg": 134.0,
  "speed_mps": 0.0,
  "active_job_id": "JB-4471",
  "battery_pct": 62
}
```
**Response `202 Accepted`**
```json
{ "received_ts": "2026-08-31T15:24:01.900Z", "geofence_event": null }
```
`geofence_event` is populated (`"entered"` / `"exited"`, plus `job_id`) when this ping crosses a job's geofence boundary — the server does this check, not the client, so it can't be spoofed by a manipulated app state.

Pings are sent in small batches (up to 20) when the app is recovering from an offline gap:

### `POST /v1/locations/batch`
```json
{ "technician_id": "T-104", "pings": [ /* array of ping objects above, each with its own device_ts */ ] }
```

### `WS /v1/stream/locations?watch=T-104,T-092,...`
Dispatch console subscribes to a set of technician IDs (or `watch=all`). Server pushes:
```json
{ "type": "location_update", "technician_id": "T-104", "lat": 32.7769, "lng": -96.7968, "heading_deg": 140, "ts": "2026-08-31T15:24:02Z" }
```

---

## 2. Job & dispatch

### `GET /v1/jobs?status=queued,enroute,onsite`
Returns the dispatcher's job queue. Each job includes `sla_deadline`, `assigned_technician_id` (nullable), and `checklist` with per-item `satisfied_by_capture_id`.

### `POST /v1/jobs/{job_id}/assign`
```json
{ "technician_id": "T-133", "assigned_by": "dispatcher:D-Vance", "override_score": false }
```
`override_score` is `true` when a dispatcher manually assigns against the recommendation from `/v1/jobs/{job_id}/candidates` (§5) — kept in the audit trail so scoring quality can be reviewed later against what dispatchers actually chose.

### `WS /v1/stream/jobs`
Pushes job state changes to the console (status transitions, SLA countdown crossing a threshold, new tickets created) so the queue updates without polling.

---

## 3. Media capture & verification

### `POST /v1/captures/init`
Called the instant the shutter fires, before the file finishes uploading — this is what lets the "Verifying…" state appear immediately in the technician app.

**Request**
```json
{
  "job_id": "JB-4472",
  "technician_id": "T-092",
  "checklist_item_id": "t1",
  "capture_type": "photo",
  "content_hash": "sha256:9f86d0...",
  "device_signature": "ed25519:3045022100...",
  "capture_lat": 32.77670,
  "capture_lng": -96.79683,
  "capture_ts": "2026-08-31T15:26:44.100Z"
}
```
`device_signature` signs `{content_hash, capture_lat, capture_lng, capture_ts, job_id, technician_id}` with a key generated on-device at app install — this is the binding described in the architecture doc that keeps the GPS/timestamp trustworthy independent of file metadata.

**Response `201 Created`**
```json
{ "capture_id": "CAP-88213", "upload_url": "https://storage.../presigned...", "expires_in": 300 }
```

### `PUT {upload_url}`
Direct-to-storage upload of the media file (client uploads straight to S3/GCS with the pre-signed URL — never routes through the app server).

### `POST /v1/captures/{capture_id}/complete`
Client confirms upload finished; triggers verification.
```json
{ "storage_etag": "\"a1b2c3...\"" }
```

**Response `202 Accepted`** — verification runs async, result delivered via WebSocket (below) or polled:

### `GET /v1/captures/{capture_id}`
```json
{
  "capture_id": "CAP-88213",
  "status": "verified",
  "checks": {
    "geofence": { "pass": true, "distance_m": 18 },
    "timestamp_window": { "pass": true },
    "duplicate_hash": { "pass": true },
    "location_continuity": { "pass": true }
  },
  "checklist_item_satisfied": "t1",
  "verified_ts": "2026-08-31T15:26:46.700Z"
}
```
If any check fails, `status` is `"flagged"` and `checks` shows which one, with a human-readable `reason` string — this is exactly what populates the review queue cards in the console.

### `WS /v1/stream/captures?job_id=JB-4472`
Pushes `capture_status_changed` events so the console's job drawer and the technician's own progress bar update the instant verification finishes, matching the ~1s "Verifying → Verified" delay in both prototypes.

---

## 4. Review queue (dispatcher resolving flagged captures)

### `GET /v1/review-queue?status=open`
Returns flagged captures with their `checks` object, needed for the review card's reason line.

### `POST /v1/captures/{capture_id}/resolve`
```json
{ "resolution": "approved", "resolved_by": "dispatcher:D-Vance", "note": "GPS drift near parking structure, confirmed via call with technician." }
```
`resolution` is `"approved"` or `"rejected"`. Approving satisfies the checklist item exactly as an auto-verified capture would; rejecting pushes a `recapture_requested` push notification to the technician's device with the same `checklist_item_id`, and writes both the original flag and the resolution to the audit ledger — nothing is ever deleted, only appended to.

---

## 5. Assignment scoring

### `GET /v1/jobs/{job_id}/candidates`
Returns ranked technicians for an unassigned job, used by the dispatcher before confirming an assignment.
```json
{
  "job_id": "JB-4478",
  "candidates": [
    {
      "technician_id": "T-201",
      "score": 0.86,
      "components": {
        "proximity": 0.91,
        "certification_match": 1.0,
        "current_load": 0.68,
        "sla_headroom": 0.78
      },
      "eta_min": 14
    }
  ]
}
```
See the scoring walkthrough for how `components` are weighted into `score`.

---

## 6. Event catalog (for the audit ledger)

Every write above also emits one row here — nothing is inferred after the fact.

| `event_type` | Fired on |
|---|---|
| `location_ping_received` | every accepted ping |
| `geofence_entered` / `geofence_exited` | boundary crossing |
| `job_assigned` | dispatcher or auto-assignment |
| `job_status_changed` | queued → en route → on site → done |
| `capture_initiated` | `POST /captures/init` |
| `capture_verified` / `capture_flagged` | verification engine result |
| `capture_resolved` | dispatcher approves/rejects a flagged capture |
| `checklist_item_satisfied` | any path that closes out a checklist item |
| `job_completed` | all checklist items satisfied |

```json
{
  "event_id": "EVT-994213",
  "event_type": "capture_flagged",
  "entity_type": "capture",
  "entity_id": "CAP-88240",
  "actor": "system:verification-engine",
  "ts": "2026-08-31T15:31:02Z",
  "payload": { "reason": "geofence", "distance_m": 340 }
}
```

---

## 7. Notifications

The notification service doesn't originate anything — it subscribes to the same audit events in §6 and matches them against the active rule set, so there's exactly one source of truth for "what happened" and a separate, swappable layer for "who gets told." This is also why rules can be toggled on/off (as in the Notification Center) without touching the services that actually run dispatch or verification.

### `GET /v1/notification-rules`
Returns the active rule set: trigger event, recipient role, channels, template, enabled state. This is what powers the Notification Center's rule list.

```json
{
  "rule_id": "r1",
  "name": "Technician en route",
  "trigger_event": "job_status_changed",
  "trigger_condition": { "to_status": "enroute", "requires_gps_lock": true },
  "recipient_role": "client_contact",
  "channels": ["sms", "push"],
  "enabled": true,
  "templates": {
    "sms": "Field PowerCycle: {technician_name} is on the way — ETA {eta_min} min for {job_id} at {site_name}. Track live: {tracking_url}",
    "push": { "title": "Technician en route", "body": "{technician_name} is {eta_min} minutes away for {job_id} at {site_name}." }
  }
}
```

### `PATCH /v1/notification-rules/{rule_id}`
```json
{ "enabled": false }
```
Toggling a rule off is itself an audited action — it writes a `notification_rule_toggled` event, since a dispatcher quietly muting SLA-breach alerts is exactly the kind of thing that should be visible later.

### `POST /v1/notifications/dispatch` *(internal — called by the rule engine, not by clients)*
Fired when an audit event matches an enabled rule's trigger condition.
```json
{
  "rule_id": "r3",
  "trigger_event_id": "EVT-994288",
  "recipient": { "role": "dispatcher", "id": "dispatcher:D-Vance" },
  "channel": "push",
  "rendered": { "title": "⚠ SLA at risk — JB-4478", "body": "Union Square Retail #7 breaches SLA in 12 minutes and is still unassigned." }
}
```

### `GET /v1/notifications/feed?since=...`
Returns delivery history — timestamp, event, recipient, channel, status (`delivered` / `opened` / `failed`) — exactly what backs the Notification Center's live activity feed. `failed` deliveries (bad phone number, bounced email) get retried once on a fallback channel before being surfaced to an admin, rather than silently dropped — an SLA-breach alert that fails to send is worse than one that arrives late.

### `WS /v1/stream/notifications?recipient=dispatcher:D-Vance`
Push channel itself, for in-app/console delivery — the same mechanism the dispatch console uses for its badge/toast alerts.

### Rule catalog (initial set)

| Rule | Trigger | Recipient | Channels |
|---|---|---|---|
| Technician en route | `job_status_changed` → `enroute` | Client | SMS, push |
| Job completed & verified | `job_completed` | Client | SMS, email |
| SLA breach imminent | SLA countdown < 15 min, unassigned | Dispatcher | Push, console |
| Job unassigned too long | Queued > 20 min | Dispatcher | Console |
| Capture flagged for review | `capture_flagged` | Dispatcher | Push, console |
| Recapture requested | `capture_resolved` → rejected | Technician | Push |
| Certification expiring | 30 / 14 / 3 days before expiry | Technician + Admin | Email, push |
| New job assigned | `job_assigned` | Technician | Push |

Two design choices worth calling out: **client-facing rules stay narrow on purpose** — a client gets told when a technician is en route and when a job closes, not every intermediate status change, because a chatty notification stream trains people to ignore all of it, including the one message that matters. And **failed sends are a first-class status**, not an error to swallow, because a silently-failed SLA alert defeats the entire point of automating the alert in the first place.

---

*Companion docs: `field-powercycle-architecture.md` (system design), assignment-scoring walkthrough and notification center (interactive).*
