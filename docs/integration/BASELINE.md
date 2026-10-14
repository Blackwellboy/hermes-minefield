# Baseline — 2026-10-14

No live endpoints contacted. Separate source clones and Python environments.

| Component | Fresh source |
|---|---|
| Adapter main | 008e12c6ac6fad1b05e744392883dc58200baa3b |
| Adapter draft PR #2, still open/draft | 50ebb68277ed74b30e0c4aba2064a23ec4243b67 |
| Integration branch base | PR #2 head; main is its ancestor |
| Core main / 0.2.1 | ec469007e530bae5de6328c25e848a82b479c79b |
| Hermes stable v0.21.7 | 71d34bad1045610252eda02ee79549436896e784 |
| Hermes rolling main (observed only) | d97007c32d6340f7ba79ac1dfb5773cc00846448 |

PR #2 conversation comments: none returned. Its description records reconciliation
of owner PRs #3/#4. No older draft files were copied over later main changes.

## Executed baseline

`python scripts/isolated_test.py pytest -q`, unmodified draft source except runner:
- Python 3.12.7, core current, no Hermes: 255 passed, 11 skipped, 2 failed.
  Equal timestamps sort by random event ID; argument event order and newest
  persisted session tests fail. Deterministic regression added and observed red.
- Python 3.14.5, real Hermes stable editable source, core current:
  294 passed, 4 skipped, 7 deselected. Includes real plugin loader/hook dispatch.
  This timing-dependent green does not invalidate the deterministic regression.
- Existing Gate A is not included by default and remains NOT_RUN at baseline.

Logs are outside checkout; they include temporary paths and are not publication
artifacts. The runner replaces environment/home and denies connections except to
loopback ports bound by the test process. Dependencies installed separately.

## Migration

| Existing feature | Source | Decision | Proof |
|---|---|---|---|
| Recorder and classification | PR #2 | retain, repair ordering/profile bounds | existing tests + ordering regression |
| Reviewed issue drafts | PR #2 | retain, never auto-publish | existing contribute tests |
| match_symptom contract | main PR #3 | retain | integration contract tests |
| Transient stack/model hints | main PR #4 | retain offline behavior | existing wtf tests |
| check/doctor flags | PR #2 | retain compatibility; new workflow needs stronger authority | existing dispatch tests |
| auto_lite | PR #2 | must be disabled in new workflow; no passive probing | acceptance pending |

GitHub CLI is unauthenticated; connected GitHub read access works. Historical
`theaaronhughes` paths fail; `Blackwellboy/openclaw-workspace` resolves. Return
index is historical discovery; it is not a source of runtime-test permission.
