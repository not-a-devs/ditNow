# DIT NOW — Claude Code entrypoint

1. Start by reading `NAV.md`, then `AGENTS.md`. Treat `AGENTS.md` as the shared repository rules for Codex and Claude.
2. Read only documentation relevant to the requested task. See `docs/00_START_HERE.md` for document precedence and `docs/10_AI_RUNBOOK.md` for execution/review rules.
3. Use repository-specific skills in `.claude/skills/` when their description matches the task. They are synchronized copies of `.agents/skills/`.
4. For research requests, do not implement app code. For implementation requests, trace the related FR/NFR/RBAC/TC and demonstrate actual tests. Never treat the `mvp/` mock API as authenticated server persistence.
5. Update `NAV.md` only when navigational facts change. Do not inflate it with full documentation or unrelated file lists.
6. No autonomous deployment, merging, destructive cleanup, secret exposure, or chargeable third-party services.
