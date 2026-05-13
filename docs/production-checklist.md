# Production Checklist

## Runtime readiness

- [ ] Configure `helloagi.json` with explicit mission/style/domain
- [ ] Set storage paths for identity and journal persistence
- [ ] Run full test suite: `python -m pytest -q`
- [ ] Verify governance deny/escalate behavior for risky prompts
- [ ] Validate API health and chat endpoint under load
- [ ] Run `helloagi doctor`, `helloagi health`, and `helloagi extensions doctor`
- [ ] Verify service install/start/status for the target platform
- [ ] Verify migration preview/apply if importing from OpenClaw or Hermes
- [ ] Containerize using Docker image and pin version tags
- [ ] Add external model/tool adapters as needed

## Public/open-source release gate

Run this while preparing a change, then again from a clean checkout before tagging, publishing to PyPI, or telling users the checkout is ready:

```bash
helloagi readiness --allow-dirty          # pre-commit / while editing
helloagi readiness                        # clean release checkout
helloagi readiness --json > readiness-report.json
```

The readiness gate checks that:

- required user docs are present (`README`, install, CLI, channels, deployment, environment, security, privacy, troubleshooting, production checklist)
- `.env`, `helloagi.json`, `helloagi.onboard.json`, `memory/`, service scratch files, and operator status files are ignored
- tracked files do not include runtime memory/state databases, OAuth stores, logs, or obvious token/secret filenames
- tracked text does not contain obvious provider tokens, Telegram bot tokens, private IPs, or known private chat IDs
- package metadata, README, Unix installer, and Windows installer are present
- tests are tracked
- user-facing runtime features are discoverable in code/docs: visible work/streaming, Telegram, service install, providers, tools, memory, reminders, and workflow runs

If `helloagi readiness` fails, fix the named blocker before pushing to `main` or cutting a release.
