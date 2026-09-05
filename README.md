# Field Power Cycle
A visual-first field service platform — real-time GPS dispatch, and photo/video proof-of-work that replaces paperwork.
Twelve connected pieces covering four people: the dispatcher routing technicians, the technician capturing verified proof in the field, the client watching their job happen live, and the admin running certifications, SLAs, and billing behind it all.

### 12 Artifacts
### 4 Personas Covered
### 0 Paper Forms

## How a job actually moves through the system
```
┌───────────┐      ┌──────────────┐      ┌────────────┐      ┌─────────────────┐      ┌──────────┐
│  01       │      │  02          │      │  03        │      │  04             │      │  05      │
│  Ticket   │─────►│  Technician  │─────►│  Proof     │─────►│  Auto-verified  │─────►│  Job     │
│  created  │      │  dispatched  │      │  captured  │      │  or flagged     │      │  closes  │
└───────────┘      └──────────────┘      │  on site   │      └─────────────────┘      └──────────┘
                                         └────────────┘
```

## Field Power Cycle - App Suite For PowerCycle360
### i. Field Ops Suite
- Dispatch Console
- Workforce
- Notifications
- Settings
- Billing
- Analytics
- Assignment Scoring

### ii. Client-facing
- Client Portal
- Technician App

> Technician app ⇄ backend ⇄ dispatch console

---

## A) System Architecture
Check out the System Architecture document [Field Power Cycle Architecture documentation](frontend/field-powercycle-architecture.md)

## B) API Contract
Check out the API Contract documentation [API Contract documentation](frontend/field-powercycle-api-contract.md)
