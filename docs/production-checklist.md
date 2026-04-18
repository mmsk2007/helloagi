# Production Checklist

- [ ] Configure `helloagi.json` with explicit mission/style/domain
- [ ] Set storage paths for identity and journal persistence
- [ ] Run full test suite: `python -m unittest discover -s tests -p "test_*.py"`
- [ ] Verify governance deny/escalate behavior for risky prompts
- [ ] Validate API health and chat endpoint under load
- [ ] Run `helloagi doctor`, `helloagi health`, and `helloagi extensions doctor`
- [ ] Verify service install/start/status for the target platform
- [ ] Verify migration preview/apply if importing from OpenClaw or Hermes
- [ ] Confirm `.env`, onboarding state, and `memory/` are excluded from source control
- [ ] Containerize using Docker image and pin version tags
- [ ] Add external model/tool adapters as needed
