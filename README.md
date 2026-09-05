# Field Power Cycle
A visual-first field service platform — real-time GPS dispatch, and photo/video proof-of-work that replaces paperwork.
Twelve connected pieces covering four people: the dispatcher routing technicians, the technician capturing verified proof in the field, the client watching their job happen live, and the admin running certifications, SLAs, and billing behind it all.

- ***10 App Artifacts***
- ***4 Personas Covered***
  1. Dispatcher & operations
  2. Field technician
  3. Client
  4. Admin / operations lead
- ***0 Paper Forms***

## How a job actually moves through the system
```
┌───────────┐      ┌──────────────┐      ┌────────────┐      ┌─────────────────┐      ┌──────────┐
│  01       │      │  02          │      │  03        │      │  04             │      │  05      │
│  Ticket   │─────►│  Technician  │─────►│  Proof     │─────►│  Auto-verified  │─────►│  Job     │
│  created  │      │  dispatched  │      │  captured  │      │  or flagged     │      │  closes  │
└───────────┘      └──────────────┘      │  on site   │      └─────────────────┘      └──────────┘
                                         └────────────┘
```

---

## Apps Artifacts
### I. Dispatcher & operations
**1. Dispatch Console** - Live map with GPS-tracked technicians, job queue with SLA countdowns, and a review queue for flagged proof-of-work.
**2. Analytics Dashboard** - SLA compliance trend, verification funnel, jobs by type/industry, and a technician leaderboard — 7D/30D/90D toggle.
**3. Assignment Scoring** - Interactive walkthrough of how a new ticket gets ranked across candidate technicians — drag the weights and watch it re-rank.
**4. Notification Center** - Rules engine for every SMS/push/email/console alert in the system, with live channel previews and a delivery feed.

### II. Field technician
**5. Technician Capture App** - Camera capture bound to GPS + timestamp at the moment of the shutter, auto-verifying checklist items, offline queueing.
**6. Workforce & Certifications** - Where the certification data behind assignment eligibility actually lives, plus a step-by-step onboarding tracker for new hires.

### III. Client
**7. Client Portal** - Live technician tracking with ETA, ticket history with verified completion reports, and a locations overview across sites.
**8. Completion Report(Downloadable)** - The static export a client can download — checklist, timestamped proof, and an audit trail with an integrity hash.

### IV. Admin/operations lead
**9. Settings** - SLA tiers, geofence radii and per-site overrides, business hours, client accounts, and connected integrations.
**10. Billing** - Invoices auto-drafted from verified job data — labor hours pulled from arrival/completion timestamps, not self-reported.

---

## a). System Architecture
Check out System Architecture documentation [Field Power Cycle Architecture documentation](frontend/field-powercycle-architecture.md)

## b). API Contract
Check out API Contract documentation [API Contract documentation](frontend/field-powercycle-api-contract.md)
