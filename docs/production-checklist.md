# Production Checklist

- [ ] Configure `helloagi.json` with explicit mission/style/domain
- [ ] Set storage paths for identity and journal persistence
- [ ] Run full test suite: `make test`
- [ ] Verify governance deny/escalate behavior for risky prompts
- [ ] Validate API health and chat endpoint under load
- [ ] Containerize using Docker image and pin version tags
- [ ] Add external model/tool adapters as needed
