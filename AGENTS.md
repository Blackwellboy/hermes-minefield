# Minefield integration operating rules

Implement docs/integration/BUILD_SPEC.md (owner handoff, 2026-10-14).
Read docs/integration/NEXT_ACTION.md and Git status before resuming.
The old docs/IMPROVEMENT_PLAN.md is retained as migration history; its one-task
stop rule is superseded by the owner's M0-M7 assignment.

- Never contact real model endpoints, SSH, inspect private runtime configuration,
  install into an active profile, load models, or mutate services.
- Use scripts/isolated_test.py for tests. Downloads/installations are separate.
- Missing, cancelled, stale or unexecuted evidence is UNKNOWN, never PASS.
- Preserve draft PR #2 and later main work. Explicit-path Git staging only.
- Sharing OFF by default; no model argument grants human authority.
- No raw private data, secrets, content hashes or arbitrary logs in exports.
- No merge, release, production collector, catalogue/Nous contact or third-party
  submission. Keep checkpoints and acceptance evidence honest.
- Retain existing tests and security gates. Use stdlib where possible.
