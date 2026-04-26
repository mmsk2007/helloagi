# HelloAGI implementation plan (continuation)

This document tracks **safe milestones** after the architecture audit and target design. Order prioritizes wiring existing modules, configuration truth, then optional browser scale-out.

## Milestone A — Configuration and documentation

- Extend `RuntimeSettings` with `reliability`, `skill_bank`, `context`, and `browser` dict sections merged from `helloagi.json`.
- Add research summaries under `docs/research/`.
- Keep SRG core modules (`srg.py`, guards, posture) **unchanged**; use `SRGAdapter` + `GovernanceLogger` for new gates.

## Milestone B — Skill bank integration

- `SkillManager` delegates to `SkillBank` + `SkillRetriever`; legacy markdown preserved.
- `TriLoop` optionally extracts `SkillContract` on `status=passed` when `skill_bank.auto_extract` is true, with `check_skill_promotion` before `add`.

## Milestone C — Governance adapter in the agent

- `HelloAGIAgent` constructs `SRGAdapter` sharing journal; completion/stop failures log `governance.completion` records.

## Milestone D — Context manager

- `agi_runtime/context/` builds a bounded supplement; `_build_system_prompt` uses it when `context.managed` is true.

## Milestone E — Browser (optional dependency)

- `helloagi[browser]` installs Playwright; tools `browser_navigate`, `browser_read`, `browser_screenshot` register at import; SSRF reuse from `web_fetch`; agent hides tools when `browser.enabled` is false or Playwright is missing.

## Milestone F — Tests and scorecard

- Unit tests for each layer; e2e files as **stubs** until LLM-in-the-loop harness exists.
- Maintain `docs/EVALUATION_SCORECARD.md` as capabilities evolve.

## Verification

```bash
cd helloagi
python -m pytest tests/ -q --tb=short
```

Install optional browser stack:

```bash
pip install "helloagi[browser]"
```
