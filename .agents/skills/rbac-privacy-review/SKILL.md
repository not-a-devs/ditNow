---
name: rbac-privacy-review
description: Security review for DIT NOW identity, anonymous community, official notices, class membership, cross-account authorization, secrets, and student-data boundaries.
---

# rbac-privacy-review

## Workflow
1. Read `docs/04_POLICY_RBAC.md`, `docs/03_NFR.md`, relevant FR and real auth/storage code.
2. Threat-model every read/write, author role and scope, including guessed URLs, direct API calls, cross-department attempts, and staff privilege escalation.
3. Verify anonymous student-facing content cannot reveal author identity through responses, IDs, logs, or linked public profiles. Do not claim server enforcement if only JS mock checks exist.
4. Verify official staff provenance and notice revisions; ensure chat event references don't create cloned sources of truth.
5. Check student records, uploads, secrets and keys in public repository; never use real data as seed.
6. Return findings ordered by severity with affected files, exploit scenario, test proof and remediation; no speculative PASS.
