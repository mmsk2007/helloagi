# Upgrade guide — feature flags

Copy `helloagi.example.json` from the repository root to `helloagi.json` if you do not have a local config yet (`helloagi.json` is gitignored).

New sections in `helloagi.json` (all optional with defaults):

- **`reliability`:** `enabled`, `loop_threshold`, `verify_completions`, `soft_timeout_sec` (wall-clock cap for the main `think()` loop; `0` disables).
- **`skill_bank`:** `enabled`, `auto_extract`, `decay_days` (decay applied by bank utilities).
- **`context`:** `managed`, `max_budget_tokens`.
- **`browser`:** `enabled`, `headless`, `max_nav_per_min`.

Disable browser tools entirely:

```json
"browser": { "enabled": false }
```

Install Playwright stack:

```bash
pip install "helloagi[browser]"
```

TriLoop skill extraction uses `agent.create_tri_loop()` which inherits `skill_bank.auto_extract` from settings. Set `"skill_bank": { "auto_extract": false }` to disable.

Semantic skill hints appear in the system prompt when `skill_bank.enabled` is true.
