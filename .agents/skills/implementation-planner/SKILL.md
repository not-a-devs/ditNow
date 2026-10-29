---
name: implementation-planner
description: Break approved DIT NOW requirements into small dependency-aware frontend/backend/database tasks with explicit acceptance tests; use for plans, not implementation.
---

# implementation-planner

## Workflow
1. Read `NAV.md`, `docs/02_FRD.md`, `docs/03_NFR.md`, `docs/04_POLICY_RBAC.md`, `docs/05_DATA_MODEL.md`, `docs/09_RELEASE_SCOPE.md`, `docs/10_AI_RUNBOOK.md`. Read relevant sections only.
2. Create small tasks with ID, scope, owner boundary, affected files, prerequisites, schema/API contract, acceptance, tests, risk, reviewer, and rollback where applicable.
3. Split infrastructure/auth/schema migrations first, then independent UI and API units. Coordinate shared files to one owner.
4. Mark not-yet-approved architectural changes BLOCKED with explicit proposal; continue unrelated ready tasks.
5. Don't generate code or claim tasks complete. Output ready tasks, critical path, dependencies, and owner handoff.
