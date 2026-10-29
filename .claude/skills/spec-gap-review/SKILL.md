---
name: spec-gap-review
description: Compare DIT NOW PRD, FRD, NFR, RBAC, data model, architecture, and current repo behavior; use to find missing requirements and conflicting decisions before implementation.
---

# spec-gap-review

## Workflow
1. Read `NAV.md` and the applicable `docs/` files, especially `11_DECISION_LOG.md`.
2. Map each candidate requirement to feature ID, roles, screens, API/data, happy path, error path, security, test cases, and state transitions.
3. Compare approved vs proposed vs unknown. Never invent school operating rules such as grading, loan limits, or attendance judgments.
4. Produce a traceability table: `[ID | evidence | existing spec | gap | proposal | decision needed | priority]`.
5. Update only research/proposal reports unless explicit approval is present for changing normative spec files.
6. Flag root README vs docs contradictions, and v0.2 pre-MVP mock claims.
