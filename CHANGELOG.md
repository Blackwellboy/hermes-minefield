# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

Every pull request that changes the plugin, its tests or its docs adds a line here under the current version (CI: `.github/workflows/changelog.yml`; label `no-changelog` to skip a typo fix).

## [0.2.0] — unreleased

Implements `docs/IMPROVEMENT_PLAN.md` (review of 0.1.0 against Hermes 0.21.x). Status: experimental until the owner signs off Gate A on a real install.

### Fixed — runs on Hermes 0.22 (2026-10-15)
- Hermes 0.22 enforces `requires_hermes`, so the plugin's `>=0.21,<0.22` made 0.22.1 refuse to load it ("requires hermes >=0.21,<0.22, running 0.22.1") and `/minefield` disappeared after updating. Range widened to `<0.23` after the full suite passed on 0.22.1 (319 passed) and Gate A ran 7/7 against real 0.22.1 processes; `hermes-compat` CI gains a `release v0.22.1` row on Python 3.14.

### Fixed — Hermes can install the core again (2026-10-15)
- The core dependency was a `git+https` pin. Hermes PM does not install direct-URL requirements (`hermes plugins validate`: "direct URL requirement(s) are not managed by PM", 0 installable), so on a fresh Hermes 0.21.6+ runtime the core was never installed and `check`, `doctor`, `guide` and `scan` said the core was missing even after `hermes pm repair`. Declared as `model-serving-minefield>=0.2.1,<0.3` (on PyPI) in `pyproject.toml` and `plugin.yaml`; CI still checks out the exact core commit. A test fails if a direct-URL dependency is declared again.

### Added — the `/minefield` menu (2026-10-15)
- `/minefield` on its own (and `hermes minefield` / `hermes minefield menu`) shows a numbered menu: 1 quick check, 2 what just happened, 3 look up a symptom, 4 scan my Hermes config, 5 full Doctor, 6 status, 7 incidents and issues, 8 draft a trap report. Each item says what it touches before it runs. `/minefield <number> [args]` runs the item exactly like its named command, so every guard still applies (`--base-url` CLI-only, Doctor needs `--yes`, nothing uploads without approval). `/minefield help` lists every command and flag.
- `guide <symptom>`: offline lookup of a plain-words symptom in the trap registry (no verdict: a lookup is not a test of your setup).
- `scan [path ...]`: read-only static scan for known traps. From chat it scans only the active Hermes config (naming paths is CLI-only, for the same reason as `--base-url`); nothing readable is `UNKNOWN`.
- CI: a changelog check fails a PR that changes the plugin without a CHANGELOG line.
- Core pin moved from `12822f3` (0.2.0) to `f74e109` (0.2.1 plus the core menu), because `guide` and `scan` need 0.2.1's renderer and static scanner. On an older core they say so (`UNKNOWN`, with the upgrade command) instead of failing; the suite passes on both pins.

### Fixed — diagnosis could say the opposite of reality
- **F1** Recorder read `params=`; Hermes sends `args=`. Every tool call got the fingerprint of `None`, so any 10+ distinct calls became `AGENT_TOOL_LOOP`/HIGH. (T1.1)
- **F2** Tool failures were recorded as successes (Hermes sends `status`/`error_type`, not an exception). (T1.1)
- **F3/F4** API hooks read the wrong keys: latency, status codes, TTFT and response length were lost, and `error_class` was `"dict"`. (T1.1)
- **F6** `check` against a dead endpoint printed "0 problems", exited 0 and cached it. It's now `UNKNOWN`, exit 3, and nothing is cached. (T1.3)
- **F7** Loops now need *consecutive* calls with the same arguments **and the same result**. Polling and re-reading after an edit are not loops, and pollers are exempt, mirroring Hermes guardrails. (T1.2, T3.2)
- **F24** The "prepare storm" rule could never fire on real data. Prepared/requested/executed now come from the right hooks. (T3.1)

### Fixed — safety, robustness, privacy
- **F15** No disk I/O on the hook thread (Hermes fails *closed* on a slow `pre_tool_call`). A background flusher does it. Recording is also ~2× cheaper. (T2.4)
- **F16** Per-process recorder segment files: concurrent CLI and gateway processes no longer lose each other's evidence. Atomic `0600` writes everywhere. (T2.5, T2.6)
- **F9** The Lite cache TTL is enforced, and stale results read `UNKNOWN (stale)`. (T1.4)
- **F13** No exception reaches the chat. Slash and CLI share one argparse parser. `--base-url` is CLI-only. (T1.5)
- **F17/F18** Canonical `plugins.entries.<id>.settings`, validated and clamped. Hermes-native home and config resolution. (T2.1, T2.2, T5.2)
- **F8** Target resolution goes through Hermes's provider ladder with API key support. The key is exact-value scrubbed from all output. Non-OpenAI-compatible providers are `UNKNOWN`. (T2.3)
- **F19** The plugin no longer inserts itself into `sys.path`. (T2.8)
- Security: `--incident ../../x` could read any `.json` file into a draft. Incident ids are now validated. (T2.7)
- **F11/F12** Submitted issues are linked back to their incident. `contribute` no longer matches itself or silently picks another incident. (T4.1, T4.3, T1.6)

### Added
- Explicit `PASS` / `FAIL` / `UNKNOWN` verdicts on every diagnostic command. Exit codes 0 / 1 / 3, and 2 for blocked. (T1.8)
- `wtf` rules: auth failure, 429 storm, 5xx storm, tool hang, failure storm, slow model (`docs/CLASSIFICATION.md`). (T3.4)
- `wtf` is scoped to the current session by default (`--session all`). Quiet windows aren't saved (`--save`/`--no-save`). (T3.5, T1.6)
- `--json` on every command. `prune` command. Bounded incident index. (T3.6, T2.7)
- Exact-draft submission (`--submit-draft <id>`, SHA-256 verified). Opt-in, transparent remote duplicate search. Real submission from chat is off by default. (T4.2, T4.4, T4.5)
- Manifest v2 (`requires_hermes >=0.21,<0.22`, `config_schema`, pinned dependency). Safe `auto_lite`. Opt-in read-only `minefield_recent_incident` agent tool. (T5.1, T5.3, T5.4)
- CI: lint; tests on 3.11–3.13; `hermes-compat` matrix (0.21.0, pinned, 0.21.5, and `main` non-blocking) with the hook contract test, real-loader tests and the Gate A scenario suite. (T0.3–T0.5, T3.8)

### Added — trap-form drafts (2026-10-15, from #5)
- `contribute` drafts aimed at `Blackwellboy/model-serving-minefield` use the public trap form's headings (What broke / What you saw / What fixed it / What were you serving / Optional diagnostic evidence) and carry the incident's known trap matches. "What fixed it" says `Not fixed yet.` and shows the rule's suggestion labelled *not yet applied*, so a report never claims a fix nobody made. The repository match ignores case.

### Fixed — integration onto main (2026-10-15)
- Carries main's #7: the file loader falls back to `ruamel.yaml` when PyYAML is missing (Hermes 0.21.6+ environments ship only ruamel), records why a read came back empty, and `target unresolved` says so. Provider blocks written as `api:` resolve.
- A missing Minefield core package is now `UNKNOWN` with an install hint (`pip install "model-serving-minefield>=0.2,<0.3"` or `hermes pm repair`), not "internal error (ModuleNotFoundError)".
- A Lite plan over budget shows its `HARD_BUDGET_VIOLATION` reason as `UNKNOWN` instead of "internal error (RuntimeError)".
- `HERMES_PLUGINS_DEBUG=1` now actually adds the traceback to an internal error. Without it, only the exception class is shown (exception text can carry paths or secrets).

### Changed
- Python `>=3.11` (Hermes's own floor). `auto_lite: prompt` is retired (it reads as `false`). Incident render drops duplicated lines. `NO_PROGRESS_STREAK` is now the real streak.
- Settings lookup order changed: `plugins.entries.<id>.settings` (then `.config`, then the entry itself) now wins over a top-level `minefield:` block, and settings written directly at the config root are no longer read. 0.1.x preferred the top-level `minefield:` block. Move settings under `plugins.entries.hermes-minefield.settings`.
- Dated notes moved to `docs/history/`.

## [0.1.0] — 2026-08-25
- Initial plugin: Lite check, guarded Doctor, flight recorder, `/minefield wtf`, review-gated contribution and issues.
