"""Telegram channel adapter for HelloAGI.

Uses the Telegram Bot API via python-telegram-bot library.
Supports:
  - Text messages → agent.think()
  - SRG escalation via inline keyboard approve/deny
  - /start, /tools, /skills, /identity, /new commands
  - Per-user sessions with history
  - Typing indicator during agent thinking

Setup:
  1. pip install python-telegram-bot
  2. Set TELEGRAM_BOT_TOKEN environment variable
  3. helloagi serve --telegram
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import uuid
from typing import Optional

from agi_runtime.channels.base import BaseChannel, ChannelMessage, ChannelResponse
from agi_runtime.config.env import load_local_env
from agi_runtime.core.agent import HelloAGIAgent
from agi_runtime.reminders.service import ReminderService
from agi_runtime.reminders.store import ReminderStore
from agi_runtime.reminders.ticker import ReminderTicker

logger = logging.getLogger("helloagi.telegram")


def _load_telegram_token() -> str:
    """Load Telegram token from env, falling back to local .env."""
    load_local_env()
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


class TelegramChannel(BaseChannel):
    """Telegram bot channel for HelloAGI."""

    APPROVAL_TIMEOUT_S = 300.0

    def __init__(self, agent: HelloAGIAgent, token: Optional[str] = None):
        super().__init__("telegram")
        self.agent = agent
        self.token = token or _load_telegram_token()
        self._app = None
        # approval_id -> (threading.Event, result_dict) — set by _handle_approval,
        # awaited by the blocking on_user_input shim that runs in the think() thread.
        self._pending_approvals: dict = {}
        # user_id -> {"step": "awaiting_name" | "awaiting_tz", ...} for first-run flow.
        self._wizard_state: dict = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._reminder_service = ReminderService()
        self._reminder_ticker: ReminderTicker | None = None

    def _principal_id_for_update(self, update) -> str:
        """Build a stable principal id for Telegram chats."""
        if not update or not update.effective_user or not update.effective_chat:
            return "telegram:unknown"
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        chat_type = getattr(update.effective_chat, "type", "")
        if chat_type == "private":
            return f"telegram:dm:{user_id}"
        return f"telegram:group:{chat_id}:user:{user_id}"

    async def start(self):
        """Start the Telegram bot."""
        if not self.token:
            raise ValueError(
                "Telegram bot token not configured. "
                "Set TELEGRAM_BOT_TOKEN or run helloagi onboard."
            )

        try:
            from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                CallbackQueryHandler,
                filters,
            )
        except ImportError:
            raise ImportError(
                "python-telegram-bot required: pip install python-telegram-bot"
            )

        # getUpdates uses a separate HTTPX pool; default pool size is 1, so the long-poll
        # holds the only connection and shutdown's final getUpdates hits PoolTimeout.
        # See: https://github.com/python-telegram-bot/python-telegram-bot/wiki/Frequently-Asked-Questions
        self._app = (
            Application.builder()
            .token(self.token)
            .get_updates_connection_pool_size(8)
            .get_updates_pool_timeout(60.0)
            .get_updates_read_timeout(60.0)
            .get_updates_write_timeout(60.0)
            .get_updates_connect_timeout(30.0)
            .pool_timeout(60.0)
            .read_timeout(120.0)
            .write_timeout(60.0)
            .connect_timeout(30.0)
            .build()
        )

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("tools", self._cmd_tools))
        self._app.add_handler(CommandHandler("skills", self._cmd_skills))
        self._app.add_handler(CommandHandler("identity", self._cmd_identity))
        self._app.add_handler(CommandHandler("new", self._cmd_new))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("remind", self._cmd_remind))
        self._app.add_handler(CommandHandler("reminders", self._cmd_reminders))
        self._app.add_handler(CommandHandler("reminder_cancel", self._cmd_reminder_cancel))
        self._app.add_handler(CommandHandler("reminder_pause", self._cmd_reminder_pause))
        self._app.add_handler(CommandHandler("reminder_resume", self._cmd_reminder_resume))
        self._app.add_handler(CommandHandler("reminder_run_now", self._cmd_reminder_run_now))
        self._app.add_handler(CallbackQueryHandler(self._handle_approval))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        self._app.add_error_handler(self._on_error)

        logger.info("Telegram bot starting...")
        await self._app.initialize()
        await self._app.start()
        self._loop = asyncio.get_running_loop()
        await self._app.updater.start_polling()
        await self.start_background_tasks()
        logger.info("Telegram bot started")

    async def stop(self):
        """Stop the Telegram bot."""
        if self._app:
            await self.stop_background_tasks()
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot stopped")

    async def start_background_tasks(self):
        if not self._app:
            return
        if self._reminder_ticker:
            return

        async def dispatch(job):
            await self._app.bot.send_message(
                chat_id=int(job.chat_id),
                text=f"⏰ Reminder ({job.id}): {job.message}",
            )

        self._reminder_ticker = ReminderTicker(
            store=ReminderStore(),
            dispatch=dispatch,
        )
        await self._reminder_ticker.start()

    async def stop_background_tasks(self):
        if self._reminder_ticker:
            await self._reminder_ticker.stop()
            self._reminder_ticker = None

    async def send(self, channel_id: str, text: str, **kwargs):
        """Send a message to a Telegram chat."""
        if self._app:
            await self._app.bot.send_message(
                chat_id=int(channel_id),
                text=text,
            )

    # ── Command Handlers ──────────────────────────────────────

    async def _cmd_start(self, update, context):
        principal_id = self._principal_id_for_update(update)
        state = self.agent.principals.get(principal_id)
        if not state.onboarded:
            await self._begin_wizard(update)
            return
        await self._send_welcome(update, state)

    async def _send_welcome(self, update, state):
        name = self.agent.identity.state.name
        char = self.agent.identity.state.character
        tools_count = len(self.agent.tool_registry.list_tools())
        greeting = f"Welcome back, {state.preferred_name}." if state.preferred_name else "Welcome back."
        await update.message.reply_text(
            f"🧠 HelloAGI - {name}\n"
            f"{char}\n\n"
            f"{greeting} I have {tools_count} tools, governed by SRG safety.\n\n"
            f"Core: /tools /skills /identity /new /help\n"
            f"Reminders: /remind <schedule> | <message> /reminders\n"
            f"            /reminder_cancel|pause|resume|run_now <id>\n\n"
            f"Just send me a message and I'll get to work.",
        )

    async def _begin_wizard(self, update):
        user_id = str(update.effective_user.id)
        self._wizard_state[user_id] = {"step": "awaiting_name"}
        first_name = getattr(update.effective_user, "first_name", "") or ""
        hint = f" (send '{first_name}' to use that)" if first_name else ""
        await update.message.reply_text(
            "👋 Hi, I'm HelloAGI — a governed autonomous agent.\n\n"
            f"What should I call you?{hint}"
        )

    async def _continue_wizard(self, update, text: str) -> bool:
        """Return True if the message was consumed by the wizard."""
        user_id = str(update.effective_user.id)
        principal_id = self._principal_id_for_update(update)
        w = self._wizard_state.get(user_id)
        if not w:
            return False

        step = w.get("step")
        if step == "awaiting_name":
            name = text.strip() or (getattr(update.effective_user, "first_name", "") or "")
            if not name:
                await update.message.reply_text("Give me a name or nickname I can use for you.")
                return True
            w["name"] = name
            w["step"] = "awaiting_tz"
            await update.message.reply_text(
                f"Nice to meet you, {name}.\n\n"
                "What's your IANA timezone? (e.g. Asia/Riyadh, Europe/London, America/New_York)\n"
                "Reply 'skip' to use the server's local zone."
            )
            return True

        if step == "awaiting_tz":
            raw = text.strip()
            tz_value = ""
            if raw.lower() not in {"skip", "-", "none"}:
                try:
                    from zoneinfo import ZoneInfo
                    ZoneInfo(raw)
                    tz_value = raw
                except Exception:
                    await update.message.reply_text(
                        f"'{raw}' isn't a valid IANA zone. Try e.g. Asia/Riyadh, or say 'skip'."
                    )
                    return True
            self.agent.principals.update(
                principal_id,
                preferred_name=w.get("name", ""),
                timezone=tz_value,
                onboarded=True,
            )
            self._wizard_state.pop(user_id, None)
            state = self.agent.principals.get(principal_id)
            tz_note = f" Timezone: {tz_value}." if tz_value else " Using server-local time."
            await update.message.reply_text(
                f"✅ You're set up, {state.preferred_name}.{tz_note}\n\n"
                "I'm time-aware and remember who you are across conversations. "
                "High-risk actions will ask for your approval before running."
            )
            await self._send_welcome(update, state)
            return True

        return False

    async def _cmd_tools(self, update, context):
        info = self.agent.get_tools_info()
        # Telegram has 4096 char limit
        if len(info) > 4000:
            info = info[:4000] + "\n..."
        await update.message.reply_text(info)

    async def _cmd_skills(self, update, context):
        skills = self.agent.skills.list_skills()
        if skills:
            lines = [f"- {s.name}: {s.description} (used {s.invoke_count}x)" for s in skills]
            await update.message.reply_text("\n".join(lines))
        else:
            await update.message.reply_text("No skills learned yet.")

    async def _cmd_identity(self, update, context):
        state = self.agent.identity.state
        text = (
            f"{state.name}\n"
            f"{state.character}\n\n"
            f"Purpose: {state.purpose}\n\n"
            f"Principles:\n" +
            "\n".join(f"- {p}" for p in state.principles)
        )
        await update.message.reply_text(text)

    async def _cmd_new(self, update, context):
        user_id = str(update.effective_user.id)
        self.clear_session(user_id)
        principal_id = self._principal_id_for_update(update)
        self.agent.clear_history(principal_id=principal_id)
        await update.message.reply_text("🔄 Fresh conversation started.")

    async def _cmd_help(self, update, context):
        await update.message.reply_text(
            "🧠 HelloAGI Help\n\n"
            "Send me any message and I'll work on it using my tools.\n\n"
            "I can: run code, read/write files, search the web, analyze code, "
            "and more — all governed by SRG safety.\n\n"
            "If I need to do something risky, I'll ask for your approval.\n\n"
            "Reminders:\n"
            "- /remind in 30m | stretch and drink water\n"
            "- /remind tomorrow 9am | standup prep\n"
            "- /remind cron:0 9 * * * | daily planning\n"
            "- /reminders, /reminder_cancel <id>, /reminder_pause <id>, /reminder_resume <id>\n"
            "- /reminder_run_now <id>",
        )

    async def _cmd_remind(self, update, context):
        principal_id = self._principal_id_for_update(update)
        raw = " ".join(context.args or []).strip()
        if not raw or "|" not in raw:
            await update.message.reply_text(
                "Usage: /remind <schedule> | <message>\n"
                "Examples:\n"
                "- /remind in 30m | check deployment\n"
                "- /remind tomorrow 9am | standup prep\n"
                "- /remind cron:0 9 * * * | daily planning"
            )
            return
        schedule, message = [x.strip() for x in raw.split("|", 1)]
        if not schedule or not message:
            await update.message.reply_text("Both schedule and message are required.")
            return
        res = self._reminder_service.create(
            principal_id=principal_id,
            message=message,
            schedule=schedule,
        )
        await update.message.reply_text(res.message)

    async def _cmd_reminders(self, update, context):
        principal_id = self._principal_id_for_update(update)
        text = self._reminder_service.list_for_principal(principal_id)
        await update.message.reply_text(text)

    async def _cmd_reminder_cancel(self, update, context):
        principal_id = self._principal_id_for_update(update)
        if not context.args:
            await update.message.reply_text("Usage: /reminder_cancel <id>")
            return
        await update.message.reply_text(self._reminder_service.cancel(principal_id, context.args[0].strip()))

    async def _cmd_reminder_pause(self, update, context):
        principal_id = self._principal_id_for_update(update)
        if not context.args:
            await update.message.reply_text("Usage: /reminder_pause <id>")
            return
        await update.message.reply_text(self._reminder_service.pause(principal_id, context.args[0].strip()))

    async def _cmd_reminder_resume(self, update, context):
        principal_id = self._principal_id_for_update(update)
        if not context.args:
            await update.message.reply_text("Usage: /reminder_resume <id>")
            return
        await update.message.reply_text(self._reminder_service.resume(principal_id, context.args[0].strip()))

    async def _cmd_reminder_run_now(self, update, context):
        principal_id = self._principal_id_for_update(update)
        if not context.args:
            await update.message.reply_text("Usage: /reminder_run_now <id>")
            return
        await update.message.reply_text(self._reminder_service.run_now(principal_id, context.args[0].strip()))

    # ── Message Handler ───────────────────────────────────────

    async def _handle_message(self, update, context):
        """Handle incoming text messages."""
        if (
            not update
            or not update.effective_user
            or not update.effective_chat
            or not update.message
            or not update.message.text
        ):
            logger.debug("Telegram: skipping non-user/non-text update")
            return
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        text = update.message.text

        principal_id = self._principal_id_for_update(update)
        state = self.agent.principals.get(principal_id)

        # First-run: route through the onboarding wizard until it completes.
        if not state.onboarded:
            if user_id not in self._wizard_state:
                await self._begin_wizard(update)
                return
            consumed = await self._continue_wizard(update, text)
            if consumed:
                return

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=int(chat_id), action="typing")

        on_user_input = self._build_approval_handler(chat_id=int(chat_id), context=context)
        original_input = self.agent.on_user_input
        self.agent.on_user_input = on_user_input

        try:
            principal_id = self._principal_id_for_update(update)
            # Run sync think() off the asyncio loop — calling think() directly blocks PTB's
            # event loop (think() uses future.result() when a loop is already running).
            r = await asyncio.wait_for(
                asyncio.to_thread(self._think_for_principal, principal_id, text),
                timeout=600.0,
            )

            show_gov = os.environ.get("HELLOAGI_TELEGRAM_SHOW_GOV", "0").strip().lower() in (
                "1", "true", "yes", "on"
            )
            meta_line = ""
            if r.decision != "allow":
                gov_icon = {"escalate": "🟡", "deny": "🔴"}.get(r.decision, "⬜")
                meta_line = f"{gov_icon} {r.decision.upper()} | risk: {r.risk:.2f}"
            elif show_gov:
                meta_line = f"🟢 ALLOW | risk: {r.risk:.2f}"
                if r.tool_calls_made > 0:
                    meta_line += f" | {r.tool_calls_made} tools in {r.turns_used} turns"

            response_text = r.text if not meta_line else f"{meta_line}\n\n{r.text}"

            # Telegram 4096 char limit
            if len(response_text) > 4000:
                response_text = response_text[:4000] + "\n\n...truncated"

            # Agent text includes arbitrary tool names (underscores) and paths; legacy
            # Markdown breaks on unpaired "_" (e.g. web_fetch). Send as plain text.
            await update.message.reply_text(response_text)

        except asyncio.TimeoutError:
            logger.warning("Telegram handler: think() exceeded 600s")
            await update.message.reply_text(
                "⏱ That took too long (10 minute limit). Try a shorter question or check server logs."
            )
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")

        finally:
            self.agent.on_user_input = original_input

    def _think_for_principal(self, principal_id: str, text: str):
        self.agent.set_principal(principal_id)
        return self.agent.think(text)

    def _build_approval_handler(self, *, chat_id: int, context):
        """Return a blocking on_user_input callback that surfaces SRG prompts to Telegram.

        The agentic loop runs in a thread (see asyncio.to_thread); this callback
        blocks that thread on a threading.Event while the asyncio loop drives
        the inline-keyboard callback. Timeout defaults to APPROVAL_TIMEOUT_S and
        a timeout is treated as deny.
        """
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        loop = self._loop

        def on_user_input(prompt: str) -> str:
            if loop is None:
                return "n"
            approval_id = uuid.uuid4().hex[:8]
            event = threading.Event()
            result = {"answer": "n"}
            self._pending_approvals[approval_id] = (event, result)

            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{approval_id}"),
                InlineKeyboardButton("❌ Deny", callback_data=f"deny:{approval_id}"),
            ]])
            preview = (prompt or "").strip()
            if len(preview) > 3500:
                preview = preview[:3500] + "…"
            body = f"🟡 SRG approval needed:\n\n{preview}"

            try:
                asyncio.run_coroutine_threadsafe(
                    context.bot.send_message(chat_id=chat_id, text=body, reply_markup=keyboard),
                    loop,
                ).result(timeout=10.0)
            except Exception as exc:
                logger.warning("Telegram approval prompt failed to send: %s", exc)
                self._pending_approvals.pop(approval_id, None)
                return "n"

            if not event.wait(timeout=self.APPROVAL_TIMEOUT_S):
                self._pending_approvals.pop(approval_id, None)
                try:
                    asyncio.run_coroutine_threadsafe(
                        context.bot.send_message(
                            chat_id=chat_id,
                            text="⌛ Approval timed out — treating as deny.",
                        ),
                        loop,
                    ).result(timeout=5.0)
                except Exception:
                    pass
                return "n"
            return result["answer"]

        return on_user_input

    async def _on_error(self, update, context):
        """Global PTB error handler to avoid noisy unhandled exceptions."""
        logger.exception("Telegram update error", exc_info=context.error)
        try:
            if update and getattr(update, "message", None):
                await update.message.reply_text("❌ Internal error while processing your message.")
        except Exception:
            pass

    async def _handle_approval(self, update, context):
        """Handle inline keyboard approval callbacks."""
        query = update.callback_query
        await query.answer()

        data = query.data or ""
        if ":" not in data:
            return
        op, approval_id = data.split(":", 1)
        entry = self._pending_approvals.pop(approval_id, None)
        if not entry:
            await query.edit_message_text("(expired approval)")
            return
        event, result = entry
        result["answer"] = "y" if op == "approve" else "n"
        event.set()
        await query.edit_message_text("✅ Approved" if op == "approve" else "❌ Denied")
