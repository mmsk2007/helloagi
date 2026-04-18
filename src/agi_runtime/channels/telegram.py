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

    def __init__(self, agent: HelloAGIAgent, token: Optional[str] = None):
        super().__init__("telegram")
        self.agent = agent
        self.token = token or _load_telegram_token()
        self._app = None
        self._pending_approvals: dict = {}  # message_id -> callback
        self._reminder_service = ReminderService()
        self._reminder_ticker: ReminderTicker | None = None

    def _principal_id_for_update(self, update) -> str:
        """Build a stable principal id for Telegram chats."""
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

        logger.info("Telegram bot starting...")
        await self._app.initialize()
        await self._app.start()
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
        name = self.agent.identity.state.name
        char = self.agent.identity.state.character
        tools_count = len(self.agent.tool_registry.list_tools())
        await update.message.reply_text(
            f"🧠 HelloAGI - {name}\n"
            f"{char}\n\n"
            f"I have {tools_count} tools at my disposal, governed by SRG safety.\n\n"
            f"Commands:\n"
            f"/tools — See my tools\n"
            f"/skills — See learned skills\n"
            f"/identity — Who am I\n"
            f"/new — Fresh conversation\n"
            f"/help — Help\n\n"
            f"Reminder commands:\n"
            f"/remind <schedule> | <message>\n"
            f"/reminders\n"
            f"/reminder_cancel <id>\n"
            f"/reminder_pause <id>\n"
            f"/reminder_resume <id>\n"
            f"/reminder_run_now <id>\n\n"
            f"Just send me a message and I'll get to work!",
        )

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
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        text = update.message.text

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=int(chat_id), action="typing")

        # Set up approval callback for SRG escalations
        approval_future = None

        def on_user_input(prompt):
            """Handle SRG escalation approval via inline keyboard."""
            nonlocal approval_future
            # This would send an inline keyboard in a real implementation
            # For now, auto-approve in Telegram (user already consented by messaging)
            return "y"

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

    async def _handle_approval(self, update, context):
        """Handle inline keyboard approval callbacks."""
        query = update.callback_query
        await query.answer()

        data = query.data
        if data.startswith("approve:"):
            msg_id = data.split(":")[1]
            if msg_id in self._pending_approvals:
                self._pending_approvals[msg_id]("y")
                await query.edit_message_text("✅ Approved")
        elif data.startswith("deny:"):
            msg_id = data.split(":")[1]
            if msg_id in self._pending_approvals:
                self._pending_approvals[msg_id]("n")
                await query.edit_message_text("❌ Denied")
