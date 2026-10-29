# DIT NOW — Repository Rules for Coding Agents

## Required navigation
- At the start of a repository task, read `NAV.md` to locate the relevant domain and documentation. Read **only applicable** PRD/FRD/NFR/RBAC/architecture/test files, not all docs on every small edit.
- `docs/00_START_HERE.md` defines document status and conflict priority. `docs/11_DECISION_LOG.md` records approved product decisions. Do not elevate a proposal to an approved decision.
- Shared workflow: `docs/10_AI_RUNBOOK.md`. Task status and proof follow that file.

## Source of truth and current limitations
- This repository is a **new campus platform**, not an integration into private DIT systems. Published DIT pages may be cited, not silently imported as personal/academic records.
- `README.md` currently emphasizes AI navigation, while `docs/` and `mvp/` emphasize integrated campus services. Flag and reconcile the scope conflict before rewriting the product positioning; do not silently change product goals.
- `mvp/` currently uses `localStorage` and fake sessions, **not** production identity, shared server persistence, or database-enforced access control. Never claim mock/API-like wrappers are real backend security.

## Task discipline
1. Declare TASK ID, affected domain/files, FR/NFR/test IDs, assumptions, dependency blockers, and acceptance criteria before major changes.
2. During research tasks, **do not modify application code**. Distinguish VERIFIED/PARTIAL/INFERRED/UNKNOWN and link factual claims to source URL + checked date.
3. During coding tasks, make the smallest scoped change. Preserve existing public contracts unless a reviewed task explicitly changes them. Add tests for changed behavior; run available checks and honestly report NOT_RUN when missing.
4. Database/auth/RBAC changes require server-side checks; UI hiding is never authorization. Anonymous posts must never leak private identity in student-facing responses.
5. Official notices have one authoritative record; chat cards reference it. External scholarship submission is user-reported, not assumed verified.
6. For monorepo coordination, define API/shared types before parallel frontend/backend development; assign shared files and migrations to one owner at a time.
7. Do not commit secrets, real student records, personal information, tokens, or generated sensitive artifacts. Public repo means mock data only unless sourced from lawful public data.
8. Do not delete/move existing code or rewrite prior docs merely to match an assumed target structure. Propose migration sequence and run regression checks.
9. Do not auto-merge, deploy, push, incur cost, or modify high-impact institutional/privacy policy without authorized human approval.
10. End each task with changes, actual checks and output, unresolved risks, NAV/docs update status, and next ready task.

## Skills
Use repo skills in `.agents/skills/` for research, specs, planning, implementation, security, QA, UX, and navigation. Skill descriptions decide when to load full guidance; do not read all skills routinely.
