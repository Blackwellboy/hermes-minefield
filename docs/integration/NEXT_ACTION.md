# Next action

1. Complete M2 persistent bounded receipts and interrupted-job recovery; expand
   exact core previews beyond request_validation without weakening bounds.
2. Verify a public trusted owner-event seam, then wire shared native approval,
   progress and consent. See UPSTREAM_SEAMS.md; slash text/renderer flags are not proof.
3. Connect passive projection to a lifecycle-owned export worker, add receipt
   rotation and failure/unload/upgrade tests.
4. Run Electron, native scripted acceptance, minimum host, complete core gates,
   and packaging lifecycle. Do not claim OFFLINE_BETA_READY before these pass.

Use the isolated Python environments adjacent to this checkout. Run tests via
`python scripts/isolated_test.py pytest ...`; never inherit active profile config.
Read BASELINE.md for source SHAs. Current branch preserves PR #2 and main.

Desktop tests: cwd `../host/apps/desktop`, Node 24.11+,
`node ../../node_modules/vitest/vitest.mjs run --config ../../../adapter/tests/desktop/vitest.config.mts`.
Dependencies were installed with lifecycle scripts disabled. Real SDK/registry,
synthetic backend, no renderer network. Not Electron/visual geometry verification.

Unified review zip: `python scripts/package_unified.py <outside-checkout-output.zip>`.
Wheel alone includes Python/resources, not native UI. Never install in active home.
