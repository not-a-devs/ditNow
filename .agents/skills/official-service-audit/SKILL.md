---
name: official-service-audit
description: Research official DIT university website and linked school services, map evidence and verification status into existing campus specifications; use for site or feature inventory, not coding.
---

# official-service-audit

## Workflow
1. Read `NAV.md`, `docs/13_EXISTING_SERVICE_AUDIT.md`, `docs/15_PLATFORM_BASELINE.md`, and related FRD rows.
2. Discover public pages and linked services, including site maps and manuals. No login bypass, scraping private user data, or guessed internal features.
3. For each discovered function store `source_url`, `checked_at`, `evidence_excerpt_or_description`, `verification_status` (VERIFIED/PARTIAL/INFERRED/UNKNOWN), `source_system`, `student_or_staff_role`, and `required_action`.
4. Distinguish a verified menu link from verified behavior behind login. Do not conflate.
5. Write reports under `docs/research/` and propose FRD additions with stable IDs, avoiding silent edits to approved specs.
6. Output coverage, unverified high-impact areas, exact sources, and follow-up plan.
