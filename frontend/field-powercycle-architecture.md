# Field PowerCycle — System Architecture
### Real-time dispatch + tamper-resistant proof-of-work, for PowerCycle360

This describes what sits behind the two prototypes: the dispatch console and the technician capture app. It's organized around the two jobs the system has to do — track and route people, and turn a photo or video into evidence that will hold up.

---

## 1. High-level shape

```
┌────────────────┐      ┌──────────────────┐      ┌───────────────────┐
│  Technician app │◄────►│   API / Realtime  │◄────►│  Dispatch console  │
│  (iOS/Android)  │      │      layer        │      │   (web)            │
└───────┬─────────┘      └─────────┬─────────┘      └────────────────────┘
        │ GPS pings, media              │
        │ capture, offline queue        │
        ▼                              ▼
┌────────────────┐            ┌──────────────────┐
│  Location       │            │  Job / dispatch   │
│  ingestion      │            │  service           │
└───────┬─────────┘            └─────────┬──────────┘
        │                                │
        ▼                                ▼
┌────────────────┐            ┌──────────────────┐
│  Media          │            │  Verification      │
│  ingestion +    │───────────►│  engine             │
│  object storage │            └─────────┬──────────┘
└────────────────┘                       ▼
                                ┌──────────────────┐
                                │  Audit / evidence  │
                                │  ledger             │
                                └──────────────────┘
```

Five services do the real work: **location ingestion**, **job/dispatch**, **media ingestion**, **verification engine**, and an **audit ledger** that's append-only by design, because proof-of-work is only worth something if it can't quietly be edited later.

---

## 2. Real-time GPS tracking & dispatch

**Ingestion.** The technician app pings location every 10–15 seconds while a job is active, less frequently when idle, batched and sent over MQTT or a lightweight WebSocket — not a REST call per ping, that doesn't scale past a few dozen techs. Each ping carries lat/lng, accuracy radius, heading, speed, and device timestamp. Pings land in a time-series store (TimescaleDB or a managed equivalent) keyed by technician ID.

**Fan-out.** A pub/sub layer (Redis Streams or SNS/SQS) pushes each accepted ping to any dispatch console currently watching that technician, so the map updates live without polling. This is also what drives ETA recalculation — a routing service (Mapbox/Google Directions, or OSRM self-hosted if this needs to stay off third-party APIs) recomputes ETA whenever a technician's position drifts meaningfully from the last route, not on every single ping.

**Dispatch/assignment logic.** Not just "closest tech" — the assignment service weighs:
- proximity and current ETA
- certification match (payment terminal work vs. structured cabling vs. HIPAA-cleared healthcare sites need different techs)
- current job load and estimated completion time
- SLA remaining on the new ticket vs. what the technician is already carrying

This can start as a scoring function a dispatcher reviews before confirming, and evolve into auto-assignment once there's enough historical data to trust it unattended for routine ticket types — keep emergency break-fix tickets human-confirmed longer than routine installs.

**Geofencing.** Each job has a geofence (radius around the site's lat/lng, or a polygon for large campuses). Arrival/departure events fire when a technician's *filtered* position — not a single raw ping — crosses the boundary, to avoid false triggers from GPS jitter. This same geofence is what the verification engine checks media against.

---

## 3. Photo/video proof-of-work

This is the part that actually replaces paperwork, so it has to be resistant to the two obvious ways people fake it: submitting an old photo, or submitting a photo taken somewhere else.

**Capture-time binding.** The technician app captures location and timestamp from the device GPS/clock *at the moment of capture*, not read out of file metadata after the fact — EXIF can be stripped or edited, so the app independently records and cryptographically signs the capture event (device ID, GPS fix, timestamp, job ID) alongside the media file. That signed record is what gets checked, not the file's own metadata.

**Upload pipeline.**
1. App captures media → generates a content hash (SHA-256) and the signed capture record.
2. Both are queued locally (see offline handling below) and uploaded to object storage (S3/GCS) via a pre-signed URL — media never routes through the app server itself.
3. On successful upload, the capture record and storage reference are written to the job's proof-of-work log.

**Verification engine** runs automatically on every capture:
- **Geofence check** — capture GPS within the job's defined radius/polygon
- **Timestamp check** — capture time falls within the job's active window (after dispatch, before close)
- **Continuity check** — capture sequence is consistent with the technician's location trail from step 2 (flags an outlier if the photo's GPS doesn't match where the tech's tracked route says they were)
- **Duplicate/reuse check** — content hash isn't already attached to a prior job (catches resubmitted old photos)
- **Optional: computer vision** — a lightweight model classifies the image against what the checklist item expects (e.g. "mounted terminal" vs. "blank wall") to flag obviously mismatched submissions for human review, not to auto-reject — false positives here should never block a technician from finishing a job.

Captures that pass all checks auto-verify and auto-check off the matching checklist item, same as in the prototype. Anything that fails a check doesn't get silently rejected — it routes to a dispatcher review queue with the reason flagged, since GPS drift near buildings and dead zones is common and shouldn't block legitimate work.

**Audit ledger.** Every capture, verification result, and checklist state change is written once, never mutated, to an append-only log (a dedicated table with no UPDATE/DELETE grants, or a proper event-sourced store if the org wants stronger guarantees). This is what makes the completion report defensible if a client disputes a job later — there's a full, ordered record of what was captured, when, where, and how it was verified.

**Offline handling.** Field sites often have dead zones. The app queues signed captures locally (encrypted at rest on-device) and syncs when connectivity returns; the signed capture record already has its authoritative timestamp/GPS, so late upload doesn't affect verification — this is why signing at capture time matters more than relying on upload time.

---

## 4. Data model (core entities)

| Entity | Key fields |
|---|---|
| `technician` | id, name, certifications[], status, current_location, active_job_id |
| `job` | id, site_id, type, status, sla_deadline, assigned_technician_id, checklist[] |
| `site` | id, client, address, lat/lng, geofence (radius or polygon) |
| `location_ping` | technician_id, lat, lng, accuracy, heading, device_ts, received_ts |
| `capture` | id, job_id, technician_id, media_url, content_hash, capture_lat/lng, capture_ts, device_signature, verification_status, verification_reasons[] |
| `checklist_item` | job_id, label, required_capture_type, satisfied_by_capture_id, completed_at |
| `audit_event` | entity_type, entity_id, event_type, payload, actor, timestamp (append-only) |

---

## 5. Stack suggestion (pragmatic, not prescriptive)

- **Mobile app:** React Native or Flutter for one codebase across iOS/Android, native modules for background GPS and camera access
- **Realtime layer:** WebSocket gateway (or managed service like Ably/Pusher) for map updates; MQTT if battery/bandwidth efficiency on spotty field connections matters more than simplicity
- **API:** REST or GraphQL for CRUD, gRPC/WebSocket for the location and verification streams
- **Location store:** TimescaleDB or PostGIS for geospatial queries (geofence checks are just spatial queries)
- **Object storage:** S3-compatible, with a CDN in front for dispatcher-side playback
- **Verification workers:** queue-driven (SQS/Kafka) so verification doesn't block the upload response — technician gets "uploaded" immediately, "verified" a second or two later, exactly like the prototype simulates
- **Audit store:** append-only table or event store; this is the one place to resist the temptation to make things editable

---

## 6. What I'd build first

1. Location ingestion + live map (the highest-visibility, lowest-risk piece)
2. Job/checklist data model + dispatcher assignment UI
3. Capture pipeline with client-side signing, before worrying about CV-based classification
4. Verification engine with geofence + timestamp checks only — add duplicate detection and CV matching once the basics are proven in the field
5. Audit ledger from day one, even in its simplest form — retrofitting "we now keep a real record" after clients have been trusting the reports is a much harder conversation than building it in from the start

---

*Companion prototypes: `fieldglass-dispatch-console.html` (dispatcher-facing) and the technician capture app (field-facing).*
