# hermes-minefield

Standalone **Hermes Agent plugin** that integrates [Model Serving Minefield](https://github.com/Blackwellboy/model-serving-minefield) without modifying Hermes core.

Minefield stays framework-neutral. This plugin is the Hermes-specific adapter.

## Commands

| CLI | Slash | Purpose |
|-----|-------|---------|
| `hermes minefield check` | `/minefield check` | Lite preflight (≤5 requests) |
| `hermes minefield doctor` | `/minefield doctor` | Full Doctor (explicit; single-slot guard) |
| `hermes minefield wtf` | `/minefield wtf` | Freeze flight recorder → explain weirdness |
| `hermes minefield incident` | `/minefield incident` | Alias for `wtf` |
| `hermes minefield contribute` | `/minefield contribute` | Sanitized candidate / issue draft |
| `hermes minefield issues` | `/minefield issues` | Local incidents + linked GitHub status |
| `hermes minefield status` | `/minefield status` | Fingerprint / cache / recorder health |

## Install (opt-in)

```bash
# 1) Ensure Minefield Phase 0 library is importable
pip install -e /path/to/model-serving-minefield   # main @ a4369c61+

# 2) Link this plugin into Hermes
ln -sfn /path/to/hermes-minefield ~/.hermes/plugins/hermes-minefield

# 3) Enable in ~/.hermes/config.yaml
# plugins:
#   enabled:
#     - hermes-minefield
```

Or install the package (entry point `hermes_agent.plugins`):

```bash
pip install -e .
```

## Safety

- **No automatic GitHub upload**
- **Model output cannot approve submission**
- **Trap markdown is never executed**
- **Flight recorder is metadata-first** (hashes/lengths/counts)
- **Full Doctor never auto-runs**
- **Single-slot endpoints require `--yes`**
- **No private fleet / Dexter / :8007 assumptions in core behaviour**

## Architecture

```
model-serving-minefield  (plan_checks / run_checks / summarize)
            ↑
   hermes-minefield plugin  (commands, recorder, incidents, issues)
            ↑
         Hermes
```

## Development

```bash
PYTHONPATH=.:/path/to/model-serving-minefield pytest -q
```

Do **not** open NousResearch PRs from this repo without separate owner approval.
