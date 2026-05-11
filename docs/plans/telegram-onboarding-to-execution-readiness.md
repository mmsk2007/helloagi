# Telegram Onboarding-to-Execution Readiness Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make HelloAGI feel natural and reliable from first Telegram contact through useful task execution, without leaking personal runtime state into the open-source repository.

**Architecture:** Separate Telegram conversation routing, onboarding state, LLM provider readiness, and task execution readiness into independently tested layers. Keep local deployment state in ignored runtime files, and keep reusable product behavior in tracked source/tests/docs.

**Tech Stack:** Python, pytest, python-telegram-bot, HelloAGI runtime service, provider credential resolution, SQLite/journal runtime state.

---

## Acceptance Criteria

- Group chats never receive repeated first-run wizard prompts during normal conversation.
- If a user completed onboarding in DM, group messages reuse that profile naturally.
- If a group-only user speaks, HelloAGI can answer naturally with light defaults and does not start a disruptive wizard.
- Telegram bot replies only when appropriate for the chat mode and does not spam group rooms.
- Startup health clearly distinguishes: Telegram configured, LLM configured, LLM usable, and task execution ready.
- Local secrets, DBs, logs, OAuth files, company-specific configs, and scratch artifacts remain ignored and untracked.
- Full test suite passes before release.

---

## Task 1: Add explicit Telegram chat-mode policy

**Objective:** Make when-to-reply behavior configurable and testable.

**Files:**
- Modify: `src/agi_runtime/channels/telegram.py`
- Modify: `src/agi_runtime/config/settings.py`
- Test: `tests/channels/test_telegram_chat_policy.py`

**Step 1: Write failing tests**

Create tests for:
- private chats always process user text
- groups process `/commands`
- groups process direct mentions/replies to the bot
- groups ignore unrelated chatter by default
- optional always-on group mode can be enabled explicitly

**Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/channels/test_telegram_chat_policy.py -v
```

Expected: FAIL because policy helpers/settings do not exist yet.

**Step 3: Implement minimal policy helper**

Add a helper that receives `update`, bot username, and configured policy, then returns `True/False` plus a reason.

**Step 4: Verify**

Run:

```bash
pytest tests/channels/test_telegram_chat_policy.py -v
pytest tests/channels -q
```

**Step 5: Commit**

```bash
git add src/agi_runtime/channels/telegram.py src/agi_runtime/config/settings.py tests/channels/test_telegram_chat_policy.py
git commit -m "feat: add telegram group reply policy"
```

---

## Task 2: Harden onboarding state transitions

**Objective:** Ensure onboarding prompts appear only in intentional onboarding flows.

**Files:**
- Modify: `src/agi_runtime/channels/telegram.py`
- Modify: `src/agi_runtime/memory/principals.py` if needed
- Test: `tests/channels/test_telegram_group_onboarding.py`

**Step 1: Expand failing tests**

Add cases for:
- completed DM profile linked into multiple groups
- group-only user does not enter wizard on normal text
- `/start` in DM can still launch onboarding
- `/start` in group gives a short help message, not the full wizard

**Step 2: Run tests**

```bash
pytest tests/channels/test_telegram_group_onboarding.py -v
```

Expected: FAIL for any missing behavior.

**Step 3: Implement minimal fixes**

Keep wizard state private-chat-first unless explicitly requested. Reuse DM profiles in group contexts.

**Step 4: Verify**

```bash
pytest tests/channels/test_telegram_group_onboarding.py -v
pytest tests/channels -q
```

**Step 5: Commit**

```bash
git add src/agi_runtime/channels/telegram.py src/agi_runtime/memory/principals.py tests/channels/test_telegram_group_onboarding.py
git commit -m "fix: constrain telegram onboarding prompts"
```

---

## Task 3: Add provider readiness diagnostics users can understand

**Objective:** Prevent confusing runtime failures like `missing_scope: model.request` by surfacing provider status before the bot joins a group.

**Files:**
- Modify: `src/agi_runtime/config/providers.py`
- Modify: `src/agi_runtime/diagnostics/scorecard.py`
- Test: `tests/diagnostics/test_scorecard.py`

**Step 1: Write failing tests**

Test these statuses:
- no provider configured
- API key configured and usable
- OAuth/Codex token configured but not model-request usable
- configured provider present but health check fails

**Step 2: Run tests**

```bash
pytest tests/diagnostics/test_scorecard.py -v
```

Expected: FAIL until readiness states are separated.

**Step 3: Implement readiness model**

Expose separate booleans/details:
- `configured`
- `credential_present`
- `llm_usable`
- `last_health_error`
- `recommended_action`

**Step 4: Verify**

```bash
pytest tests/diagnostics/test_scorecard.py -v
pytest -q
```

**Step 5: Commit**

```bash
git add src/agi_runtime/config/providers.py src/agi_runtime/diagnostics/scorecard.py tests/diagnostics/test_scorecard.py
git commit -m "feat: clarify llm provider readiness"
```

---

## Task 4: Add a Telegram preflight command

**Objective:** Let operators verify the bot before adding it to production groups.

**Files:**
- Modify: `src/agi_runtime/channels/telegram.py`
- Test: `tests/channels/test_telegram_preflight.py`
- Docs: `README.md`

**Step 1: Write failing tests**

Test `/preflight` returns:
- Telegram identity
- service health
- provider readiness
- group reply policy
- whether task tools are enabled
- no secrets in output

**Step 2: Run tests**

```bash
pytest tests/channels/test_telegram_preflight.py -v
```

Expected: FAIL until command exists.

**Step 3: Implement command**

Add `/preflight` as a safe diagnostic command. Redact secrets and tokens.

**Step 4: Verify**

```bash
pytest tests/channels/test_telegram_preflight.py -v
pytest tests/channels -q
```

**Step 5: Commit**

```bash
git add src/agi_runtime/channels/telegram.py tests/channels/test_telegram_preflight.py README.md
git commit -m "feat: add telegram preflight diagnostics"
```

---

## Task 5: Add execution safety gates

**Objective:** Make it clear when HelloAGI can only chat versus when it can execute tasks/tools.

**Files:**
- Modify: `src/agi_runtime/core/agent.py`
- Modify: `src/agi_runtime/api/server.py`
- Test: `tests/core/test_execution_readiness.py`

**Step 1: Write failing tests**

Test states:
- chat-only mode
- tools disabled by policy
- tools enabled with safe policy
- denied risky action creates clear user-facing response

**Step 2: Run tests**

```bash
pytest tests/core/test_execution_readiness.py -v
```

Expected: FAIL until readiness gates exist.

**Step 3: Implement readiness state**

Expose a small readiness object on the agent and health endpoint.

**Step 4: Verify**

```bash
pytest tests/core/test_execution_readiness.py -v
pytest -q
```

**Step 5: Commit**

```bash
git add src/agi_runtime/core/agent.py src/agi_runtime/api/server.py tests/core/test_execution_readiness.py
git commit -m "feat: expose execution readiness gates"
```

---

## Task 6: Document safe open-source deployment

**Objective:** Make the project easy for outside users to onboard without exposing private state.

**Files:**
- Modify: `README.md`
- Create: `docs/deployment/telegram-safe-setup.md`
- Modify: `.gitignore`

**Step 1: Write docs checklist**

Document:
- clone/install
- configure `.env`
- run tests
- run `/preflight`
- add bot to group
- recommended group reply policy
- secret/file safety checklist

**Step 2: Verify docs links**

Run:

```bash
python - <<'PY'
from pathlib import Path
for path in ['README.md', 'docs/deployment/telegram-safe-setup.md']:
    text = Path(path).read_text()
    assert 'TELEGRAM_BOT_TOKEN' in text
    assert '.env' in text
print('docs smoke ok')
PY
```

**Step 3: Commit**

```bash
git add README.md docs/deployment/telegram-safe-setup.md .gitignore
git commit -m "docs: add safe telegram deployment guide"
```

---

## Release Verification

Run before merging/releasing:

```bash
python -m pip install -e '.[telegram,openai,rich,dev]'
pytest -q
helloagi health
helloagi service status
```

Manual Telegram smoke test:

1. DM bot `/start` and complete onboarding.
2. Send normal message in DM; expect natural answer.
3. Add bot to a test group.
4. Send unrelated group chatter; expect no disruptive onboarding prompt.
5. Mention bot or reply to bot; expect natural answer.
6. Run `/preflight`; expect redacted status and clear readiness.
7. Remove bot from test group if provider readiness is not green.

---

## Open-Source Safety Checklist

Before every commit:

```bash
git status --short --untracked-files=all
git check-ignore -v .env helloagi.json helloagi.onboard.json memory/identity_state.json || true
git diff --cached | grep '^+' | grep -Ei '(api_key|secret|password|token|passwd)\s*=\s*["'"'][^"'"']{6,}["'"']|BEGIN .*PRIVATE|TELEGRAM_BOT_TOKEN\s*=' || true
pytest -q
```

No local runtime files, credentials, company-specific configs, DBs, logs, OAuth tokens, screenshots, or scratch outputs should be committed.
