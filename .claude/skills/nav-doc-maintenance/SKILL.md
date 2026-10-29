---
name: nav-doc-maintenance
description: Keep DIT NOW NAV.md, repository instructions, documentation references, and task records aligned after folder or API boundary changes.
---

# nav-doc-maintenance

## Workflow
1. Inspect git diff and actual repository tree. Read `NAV.md`, `docs/00_START_HERE.md`, `docs/11_DECISION_LOG.md`.
2. Update navigation paths and owner boundaries only when changed; preserve the map concise and navigational, never write full source summaries.
3. Link new implementation to FR/NFR/test IDs, accurately mark mock vs server-backed and implemented vs proposed.
4. Identify stale README claims and create a correction proposal; don't silently rewrite approved positioning.
5. Check each documented path exists, report stale links, and do not invent commands or test proof.
