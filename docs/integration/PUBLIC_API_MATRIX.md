# Public API matrix

Selected host: Hermes v0.21.7 / 71d34bad1045610252eda02ee79549436896e784.
Selected core: 0.2.1 / ec469007e530bae5de6328c25e848a82b479c79b.

| Interface | Source / documentation | Verified facts / limitation |
|---|---|---|
| register(ctx), register_command | hermes_cli/plugins.py; website/docs/developer-guide/plugins/index.md | raw string handler, no actor argument; cannot infer owner from command text |
| dispatch_tool | same | public dispatch with host context; not proof every arbitrary action requires fresh human approval |
| on_unload | same | registered cleanup, actual loader tested |
| register_tool | same | actual registry and default-hidden tool tested |
| Desktop register(ctx), ctx.rest/socket | website/docs/developer-guide/desktop-plugin-sdk.md | native ESM, React singleton; backend namespace shared with dashboard; no invented widgets |
| Desktop unified package | same | desktop/plugin.js + dashboard/manifest.json + plugin_api.py |
| Host LLM | agent/plugin_llm.py; plugin-llm-access.md | high-level normalization; not proven raw-wire diagnostic transport |
| Core plan_checks/run_checks | minefield/api.py, execution.py at 3425846 | additive raw all-HTTP/cancel context tested; exact preview only request_validation |
| Core match_symptom | minefield/api.py | offline lookup, candidate not confirmation |

Privileged slash actions remain blocked unless a trusted actor/approval seam is
proved. Backend auth/profile scope and actual Desktop runner still require tests.
No endpoint or credential resolver may run during this campaign.

Actual selected-SDK registration, React controls and delayed session-response
rejection pass (2 tests). Backend is synthetic at ctx.rest; context/registry/state
and SDK are real. This is not Electron or private-route authority proof. Five new
tools and the skill are discovered by the actual Python plugin manager.
