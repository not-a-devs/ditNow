---
name: fullstack-implementation
description: Implement an approved, bounded DIT NOW frontend/backend/database feature with API contract, authorization, tests, and navigation updates; use for coding tasks only.
---

# fullstack-implementation

## Workflow
1. Follow `AGENTS.md`, find actual code through `NAV.md`, and identify task IDs, relevant FR/NFR/RBAC/TC.
2. Confirm where the real server persists data: `mvp/src/shared/data/api` is currently a browser mock. Avoid treating it as a secure production API.
3. For cross-stack changes, implement/check contract and server permission first, then client, then tests and seed data. Keep protected records scoped to identity server-side.
4. Do not silently invent required institutional policies; mark undecidable high-risk behavior BLOCKED.
5. Run existing relevant commands (`cd mvp && npm run typecheck`, `npm run build`) and any real tests added; report exact results.
6. Update `NAV.md` for path/entrypoint changes and impacted FR/TC documents only when appropriate. Report unverified production claims explicitly.
