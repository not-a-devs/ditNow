---
name: quality-release-gate
description: Run DIT NOW integration, CI, browser, DB persistence, performance, and hackathon submission checks; use at review or release readiness.
---

# quality-release-gate

## Workflow
1. Read `docs/08_TEST_QA.md`, `docs/09_RELEASE_SCOPE.md`, and `docs/12_HACKATHON_GATE.md`, validate official rubric is current before final submission.
2. Confirm available commands instead of inventing them. Current `mvp/package.json` exposes typecheck and build; no dedicated unit test command as of initial audit.
3. Verify auth and two account isolation on server, DB persistence after refresh/new session, 3 primary feature CRUD, staff-to-student notice delivery, AI actually data-backed if claimed.
4. Test mobile 390px / desktop 1280px, browser console, Lighthouse, API failures, and media/streaming only if implemented.
5. Report PASS/FAIL/NOT_RUN/BLOCKED with commands, evidence, env, and reviewer. No merge/deploy by default.
