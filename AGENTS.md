# Instructions for coding agents

This repo is **hermes-minefield**, a standalone Hermes Agent plugin that adapts
[Model Serving Minefield](https://github.com/Blackwellboy/model-serving-minefield) into Hermes.

## If you were asked to "work on the plan"

1. Open `docs/IMPROVEMENT_PLAN.md` and read **§0 (How to execute)** and **§2 (Hermes facts)** in full.
2. Pick the **first unticked task** (`- [ ]`) in §4. Do only that task.
3. Follow its **Do** steps exactly. Meet its **Accept** criteria and pass the check gate in §0.1.
4. Open one PR for that task. Tick its box. Stop.

## Hard rules (always, even outside the plan)

- Never store raw tool args, tool results, prompts, conversation text, or API keys. Store hashes, lengths, and counts only.
- Never add automatic GitHub submission, and never let model output approve anything.
- Hook callbacks must be pure and fast, and must never raise. `pre_tool_call` failing or timing out **blocks the user's tool** in Hermes.
- `pre_llm_call` callbacks must return `None`. Anything else is injected into the prompt.
- No new runtime dependencies. Don't weaken or delete tests to get green.
- Don't open PRs or issues outside `Blackwellboy/hermes-minefield` without written owner approval.
- If this repo's code disagrees with `docs/IMPROVEMENT_PLAN.md`, stop and report the discrepancy. Don't guess.

## Quick commands

```bash
./scripts/dev_setup.sh && source .venv/bin/activate   # after plan task T0.1 exists
ruff check hermes_minefield tests && ruff format --check hermes_minefield tests
pytest -q
hermes plugins validate .
```
