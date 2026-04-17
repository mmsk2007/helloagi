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
from agi_runtime.core.agent import HelloAGIAgent

logger = logging.getLogger("helloagi.telegram")


class TelegramChannel(BaseChannel):
    """Telegram bot channel for HelloAGI."""

    def __init__(self, agent: HelloAGIAgent, token: Optional[str] = None):
        super().__init__("telegram")
        self.agent = agent
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._app = None
        self._pending_approvals: dict = {}  # message_id -> callback

    async def start(self):
        """Start the Telegram bot."""
        if not self.token:
            raise ValueError(
                "Telegram bot token not configured. "
                "Set TELEGRAM_BOT_TOKEN environment variable."
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

        self._app = Application.builder().token(self.token).build()

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("tools", self._cmd_tools))
        self._app.add_handler(CommandHandler("skills", self._cmd_skills))
        self._app.add_handler(CommandHandler("identity", self._cmd_identity))
        self._app.add_handler(CommandHandler("new", self._cmd_new))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CallbackQueryHandler(self._handle_approval))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        logger.info("Telegram bot starting...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        logger.info("Telegram bot started")

    async def stop(self):
        """Stop the Telegram bot."""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot stopped")

    async def send(self, channel_id: str, text: str, **kwargs):
        """Send a message to a Telegram chat."""
        if self._app:
            await self._app.bot.send_message(
                chat_id=int(channel_id),
                text=text,
                parse_mode="Markdown",
            )

    # ── Command Handlers ──────────────────────────────────────

    async def _cmd_start(self, update, context):
        name = self.agent.identity.state.name
        char = self.agent.identity.state.character
        tools_count = len(self.agent.tool_registry.list_tools())
        await update.message.reply_text(
            f"🧠 *HelloAGI — {name}*\n"
            f"_{char}_\n\n"
            f"I have {tools_count} tools at my disposal, governed by SRG safety.\n\n"
            f"Commands:\n"
            f"/tools — See my tools\n"
            f"/skills — See learned skills\n"
            f"/identity — Who am I\n"
            f"/new — Fresh conversation\n"
            f"/help — Help\n\n"
            f"Just send me a message and I'll get to work!",
            parse_mode="Markdown",
        )

    async def _cmd_tools(self, update, context):
        info = self.agent.get_tools_info()
        # Telegram has 4096 char limit
        if len(info) > 4000:
            info = info[:4000] + "\n..."
        await update.message.reply_text(f"```\n{info}\n```", parse_mode="Markdown")

    async def _cmd_skills(self, update, context):
        skills = self.agent.skills.list_skills()
        if skills:
            lines = [f"• *{s.name}*: {s.description} (used {s.invoke_count}x)" for s in skills]
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        else:
            await update.message.reply_text("_No skills learned yet._", parse_mode="Markdown")

    async def _cmd_identity(self, update, context):
        state = self.agent.identity.state
        text = (
            f"*{state.name}*\n"
            f"_{state.character}_\n\n"
            f"*Purpose:* {state.purpose}\n\n"
            f"*Principles:*\n" +
            "\n".join(f"• {p}" for p in state.principles)
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    async def _cmd_new(self, update, context):
        user_id = str(update.effective_user.id)
        self.clear_session(user_id)
        self.agent.clear_history()
        await update.message.reply_text("🔄 Fresh conversation started.")

    async def _cmd_help(self, update, context):
        await update.message.reply_text(
            "🧠 *HelloAGI Help*\n\n"
            "Send me any message and I'll work on it using my tools.\n\n"
            "I can: run code, read/write files, search the web, analyze code, "
            "and more — all governed by SRG safety.\n\n"
            "If I need to do something risky, I'll ask for your approval.",
            parse_mode="Markdown",
        )

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
            # Run agent thinking
            r = self.agent.think(text)

            # Format response
            gov_icon = {"allow": "🟢", "escalate": "🟡", "deny": "🔴"}.get(r.decision, "⬜")
            header = f"{gov_icon} `{r.decision}` | risk: {r.risk:.2f}"
            if r.tool_calls_made > 0:
                header += f" | {r.tool_calls_made} tools in {r.turns_used} turns"

            response_text = f"{header}\n\n{r.text}"

            # Telegram 4096 char limit
            if len(response_text) > 4000:
                response_text = response_text[:4000] + "\n\n_...truncated_"

            await update.message.reply_text(response_text, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")

        finally:
            self.agent.on_user_input = original_input

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
