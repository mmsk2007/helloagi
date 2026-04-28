# Reminders and scheduling scope

## What HelloAGI ships today

- **Reminders** live under [`src/agi_runtime/reminders/`](../src/agi_runtime/reminders/): `ReminderService`, SQLite-backed `ReminderStore`, and `ReminderTicker`.
- **Formats:** relative (`in 30m`), absolute (`tomorrow 9am`), and **`cron:...`** expressions parsed by [`parse_schedule_input`](../src/agi_runtime/reminders/parse.py).
- **Delivery:** reminders target **Telegram principals** (see `ReminderService.create` — non-Telegram principals get a clear error). When a job fires, the ticker delivers the **stored reminder text** through Telegram; it does **not** automatically run a full `HelloAGIAgent.think()` with tools unless you extend the ticker fire path yourself.

## SRG and scheduled text

User-authored reminder **messages** are not re-evaluated by SRG at fire time in the default path (they are outbound notifications). If you add **scheduled agent runs** (Hermes/OpenClaw-style cron prompts), run the synthetic user payload through the same **`governor.evaluate`** path as live chat before calling `think()`.

## Comparison (high level)

| System | Scheduled work |
|--------|----------------|
| **HelloAGI** | User reminders + optional agent tools (`reminder_*`) |
| **Hermes** | `cronjob` tool + gateway `cron.manage`, prompt threat scan |
| **OpenClaw** | `src/cron` store, timer, concurrency caps, ledger hooks |
| **Thoth** | `tasks.db`, APScheduler, workflows, channel delivery, allowlists |

## Future: “agent cron”

To reach Hermes/OpenClaw parity for **autonomous scheduled runs**:

1. On tick, call `agent.think(...)` with a synthetic envelope and a dedicated `run_id` (reuse [`run_log.py`](../src/agi_runtime/reminders/run_log.py) for audit).
2. Add **single-flight** / min-gap between fires (OpenClaw timer patterns) per principal.
3. Optionally port **Hermes-style** high-severity regex scans for stored prompts before first run.

Document any custom extension in your deployment README so operators know reminders ≠ full agent unless configured.
