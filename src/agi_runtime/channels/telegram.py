"""Telegram channel adapter for HelloAGI.

Uses the Telegram Bot API via python-telegram-bot library.
Supports:
  - Text messages → agent.think()
  - SRG escalation via inline keyboard approve/deny
  - /start, /tools, /skills, /identity, /new commands
  - Per-user sessions with history
  - Typing indicator during agent thinking
  - Live tool progress on one preview message (on by default; HELLOAGI_TELEGRAM_LIVE=0 to disable)

Setup:
  1. pip install python-telegram-bot
  2. Set TELEGRAM_BOT_TOKEN environment variable
  3. helloagi serve --telegram
"""

from __future__ import annotations

import asyncio
import html as _html
import logging
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from agi_runtime.channels.base import BaseChannel, ChannelMessage, ChannelResponse
from agi_runtime.config.env import load_local_env
from agi_runtime.core.agent import HelloAGIAgent
from agi_runtime.reminders.service import ReminderService
from agi_runtime.reminders.store import ReminderStore
from agi_runtime.reminders.ticker import ReminderTicker

logger = logging.getLogger("helloagi.telegram")

_TG_TEXT_LIMIT = 4096
_TG_CAPTION_LIMIT = 1024
_TG_LIVE_PLACEHOLDER = "⏳ Working on your request…"
_TG_LIVE_MAX_PREVIEW = 3000
_TG_LIVE_DEFAULT_DEBOUNCE_S = 0.55


def _env_telegram_live_enabled() -> bool:
    """Default ON (OpenClaw-style tool preview). Set HELLOAGI_TELEGRAM_LIVE=0 to disable."""
    if "HELLOAGI_TELEGRAM_LIVE" not in os.environ:
        return True
    v = os.environ.get("HELLOAGI_TELEGRAM_LIVE", "").strip().lower()
    if v in ("0", "false", "no", "off", "disabled"):
        return False
    return v in ("1", "true", "yes", "on", "auto", "")


def _env_telegram_live_debounce_s() -> float:
    raw = os.environ.get("HELLOAGI_TELEGRAM_LIVE_MIN_INTERVAL_MS", "550").strip()
    try:
        ms = int(raw, 10)
    except ValueError:
        return _TG_LIVE_DEFAULT_DEBOUNCE_S
    return max(0.2, min(5.0, ms / 1000.0))


def _load_telegram_token() -> str:
    """Load Telegram token from env, falling back to local .env."""
    load_local_env()
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _markdownish_to_html(text: str) -> str:
    """Convert the narrow markdown subset Claude tends to emit into Telegram HTML.

    Telegram's HTML parser supports <b>, <i>, <code>, <pre>, <a>, <s>, <u>.
    We escape first so raw '<', '>', '&' in the model output never become tags,
    then layer code blocks → inline code → bold → italic. Underscores are left
    alone because tool/file identifiers (web_fetch, file_path) collide with the
    italic pattern.
    """
    if not text:
        return ""
    s = _html.escape(text, quote=False)
    s = re.sub(r"```(.*?)```", lambda m: f"<pre>{m.group(1)}</pre>", s, flags=re.DOTALL)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.DOTALL)
    s = re.sub(r"(?<![\*\w])\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", s)
    return s


class TelegramChannel(BaseChannel):
    """Telegram bot channel for HelloAGI."""

    APPROVAL_TIMEOUT_S = 300.0
    capabilities = frozenset({"text", "file", "image", "voice"})

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
        # principal_id -> {"started_at": monotonic, "preview": short text}
        self._inflight_by_principal: dict[str, dict[str, Any]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._reminder_service = ReminderService()
        self._reminder_ticker: ReminderTicker | None = None
        self._typing_interval_seconds = 4.0

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
        if _env_telegram_live_enabled():
            logger.info(
                "Telegram live tool preview: ON (one placeholder message, edits on tool use). "
                "Not token streaming — set HELLOAGI_TELEGRAM_LIVE=0 to disable."
            )

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
            await self._send_text(
                int(job.chat_id),
                f"⏰ Reminder ({job.id}): {job.message}",
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
        """Send a message to a Telegram chat with HTML-formatted markdown."""
        if self._app:
            await self._send_text(int(channel_id), text)

    async def _send_text(self, chat_id: int, text: str) -> None:
        """Send text rendered as Telegram HTML, falling back to plain on parse error.

        The model emits GFM markdown (**bold**, `code`, ```block```). Telegram's
        default sender treats '*' literally so the user sees raw asterisks. We
        escape + convert here. If Telegram rejects the markup (rare — usually a
        regex edge case in user-typed content), we retry once as plain text.
        """
        if not self._app or not text:
            return
        body = text if len(text) <= _TG_TEXT_LIMIT else text[: _TG_TEXT_LIMIT - 16] + "\n\n…truncated"
        try:
            await self._app.bot.send_message(
                chat_id=chat_id,
                text=_markdownish_to_html(body),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.debug("HTML send failed (%s); retrying as plain text", exc)
            try:
                await self._app.bot.send_message(chat_id=chat_id, text=body)
            except Exception:
                logger.exception("Plain-text retry to chat %s also failed", chat_id)

    @staticmethod
    def _format_tool_progress_start(tool_name: str, decision: str) -> str:
        if decision == "allow":
            return f"🛠 {tool_name}…"
        if decision == "deny":
            return f"🛑 {tool_name} (blocked)"
        if decision == "escalate":
            return f"🟡 {tool_name} (needs approval)"
        return f"⚪ {tool_name} ({decision})"

    @staticmethod
    def _format_tool_progress_end(tool_name: str, ok: bool) -> str:
        return f"{'✓' if ok else '✗'} {tool_name}"

    def _schedule_live_preview_fragment(self, live_st: dict, line: str, loop: asyncio.AbstractEventLoop) -> None:
        """Hop from the think() worker thread to PTB loop; log dropped Future exceptions."""
        try:
            fut = asyncio.run_coroutine_threadsafe(self._live_coalesce_edit(live_st, line), loop)

            def _done(f) -> None:
                exc = f.exception()
                if exc is not None:
                    logger.warning("telegram live preview task failed: %s", exc)

            fut.add_done_callback(_done)
        except Exception as exc:
            logger.debug("telegram live preview schedule: %s", exc)

    async def _live_coalesce_edit(self, st: dict, fragment: str) -> None:
        """Debounce: edit preview after quiet period; each new fragment resets the timer."""
        st.setdefault("lines", []).append(fragment)
        st["lines"] = st["lines"][-10:]
        joined = "\n".join(st["lines"])
        st["pending"] = joined
        if len(joined) > _TG_LIVE_MAX_PREVIEW:
            st["pending_for_edit"] = joined[: _TG_LIVE_MAX_PREVIEW - 8] + "\n…(trimmed)"
        else:
            st["pending_for_edit"] = joined
        prev = st.get("debounce_task")
        if prev is not None and not prev.done():
            prev.cancel()
        st["debounce_task"] = asyncio.create_task(self._live_after_quiet(st))

    async def _live_after_quiet(self, st: dict) -> None:
        try:
            await asyncio.sleep(st["debounce_s"])
            await self._live_flush_immediate(st)
        except asyncio.CancelledError:
            return

    async def _live_flush_immediate(self, st: dict) -> None:
        """Push accumulated tool lines to Telegram (plain text). Safe to call after debounce cancel."""
        text = (st.get("pending_for_edit") or "").strip() or (st.get("pending") or "").strip()
        if not text or st.get("message_id") is None:
            return
        body = text if len(text) <= _TG_TEXT_LIMIT else text[: _TG_TEXT_LIMIT - 8] + "\n…(trimmed)"
        try:
            await st["bot"].edit_message_text(
                chat_id=st["chat_id"],
                message_id=st["message_id"],
                text=body,
            )
        except Exception as exc:
            emsg = str(exc).lower()
            if "message is not modified" in emsg:
                return
            logger.debug("Telegram live preview edit failed: %s", exc)

    async def _cancel_live_debounce(self, st: dict) -> None:
        t = st.get("debounce_task")
        if t is not None and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        # Debounce cancel drops the scheduled edit; flush so the last tool lines still appear.
        await self._live_flush_immediate(st)

    async def _reply_user_message_html_or_plain(
        self, update, response_text: str, *, char_cap: int = 4000
    ) -> None:
        if len(response_text) > char_cap:
            response_text = response_text[:char_cap] + "\n\n...truncated"
        try:
            await update.message.reply_text(
                _markdownish_to_html(response_text),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.debug("HTML reply failed (%s); retrying as plain text", exc)
            await update.message.reply_text(response_text)

    async def _deliver_telegram_response(
        self,
        update,
        context,
        response_text: str,
        live_st: Optional[dict],
    ) -> None:
        """Send the final model reply, preferring in-place edit of the live placeholder."""
        if not live_st or live_st.get("message_id") is None:
            await self._reply_user_message_html_or_plain(update, response_text)
            return
        if len(response_text) > 4000:
            response_text = response_text[:4000] + "\n\n...truncated"
        html_body = _markdownish_to_html(response_text)
        try:
            await context.bot.edit_message_text(
                chat_id=live_st["chat_id"],
                message_id=live_st["message_id"],
                text=html_body,
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.debug("Telegram final edit failed (%s); replying in new message", exc)
            try:
                await self._reply_user_message_html_or_plain(update, response_text)
            finally:
                try:
                    await context.bot.delete_message(
                        chat_id=live_st["chat_id"],
                        message_id=live_st["message_id"],
                    )
                except Exception:
                    pass

    # ── Outbound media (file/image/voice) ─────────────────────

    async def send_file(
        self,
        channel_id: str,
        path: str,
        caption: str = "",
        filename: str = "",
    ) -> Dict[str, Any]:
        if not self._app:
            return {"ok": False, "message_id": None, "error": "telegram channel not started"}
        p = Path(path)
        if not p.exists() or not p.is_file():
            return {"ok": False, "message_id": None, "error": f"file not found: {path}"}
        cap = (caption or "")[:_TG_CAPTION_LIMIT] or None
        try:
            with p.open("rb") as f:
                msg = await self._app.bot.send_document(
                    chat_id=int(channel_id),
                    document=f,
                    filename=filename or p.name,
                    caption=cap,
                )
            return {"ok": True, "message_id": str(msg.message_id), "error": None}
        except Exception as exc:
            return {"ok": False, "message_id": None, "error": str(exc)}

    async def send_image(
        self,
        channel_id: str,
        path_or_url: str,
        caption: str = "",
    ) -> Dict[str, Any]:
        if not self._app:
            return {"ok": False, "message_id": None, "error": "telegram channel not started"}
        cap = (caption or "")[:_TG_CAPTION_LIMIT] or None
        is_url = path_or_url.lower().startswith(("http://", "https://"))
        try:
            if is_url:
                msg = await self._app.bot.send_photo(
                    chat_id=int(channel_id),
                    photo=path_or_url,
                    caption=cap,
                )
            else:
                p = Path(path_or_url)
                if not p.exists() or not p.is_file():
                    return {"ok": False, "message_id": None, "error": f"file not found: {path_or_url}"}
                with p.open("rb") as f:
                    msg = await self._app.bot.send_photo(
                        chat_id=int(channel_id),
                        photo=f,
                        caption=cap,
                    )
            return {"ok": True, "message_id": str(msg.message_id), "error": None}
        except Exception as exc:
            return {"ok": False, "message_id": None, "error": str(exc)}

    async def send_voice(
        self,
        channel_id: str,
        path: str,
        caption: str = "",
    ) -> Dict[str, Any]:
        if not self._app:
            return {"ok": False, "message_id": None, "error": "telegram channel not started"}
        p = Path(path)
        if not p.exists() or not p.is_file():
            return {"ok": False, "message_id": None, "error": f"file not found: {path}"}
        cap = (caption or "")[:_TG_CAPTION_LIMIT] or None
        try:
            with p.open("rb") as f:
                msg = await self._app.bot.send_voice(
                    chat_id=int(channel_id),
                    voice=f,
                    caption=cap,
                )
            return {"ok": True, "message_id": str(msg.message_id), "error": None}
        except Exception as exc:
            return {"ok": False, "message_id": None, "error": str(exc)}

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

        preview = text.replace("\n", " ")
        if len(preview) > 80:
            preview = preview[:77] + "..."
        logger.info("msg in  | pid=%s | %s", principal_id, preview)

        busy = self._inflight_by_principal.get(principal_id)
        if busy:
            import time as _time

            elapsed = max(_time.monotonic() - float(busy.get("started_at", _time.monotonic())), 0.0)
            current_preview = str(busy.get("preview", "your previous request")).strip() or "your previous request"
            await update.message.reply_text(
                f"⏳ I'm still working on your previous task ({elapsed:.0f}s so far): {current_preview}\n\n"
                "I can't safely start a second run in this chat yet. Wait for the current one to finish."
            )
            logger.info("msg busy| pid=%s | rejected overlap while previous run active", principal_id)
            return

        # First-run: route through the onboarding wizard until it completes.
        if not state.onboarded:
            if user_id not in self._wizard_state:
                logger.info("wizard  | pid=%s | starting first-run flow", principal_id)
                await self._begin_wizard(update)
                return
            consumed = await self._continue_wizard(update, text)
            if consumed:
                logger.info("wizard  | pid=%s | step=%s", principal_id, self._wizard_state.get(user_id, {}).get("step", "done"))
                return

        # Show typing indicator immediately, then keep it alive for long-running tasks.
        await context.bot.send_chat_action(chat_id=int(chat_id), action="typing")
        typing_task = asyncio.create_task(self._typing_keepalive(context.bot, int(chat_id)))

        on_user_input = self._build_approval_handler(
            chat_id=int(chat_id), context=context, principal_id=principal_id
        )
        original_input = self.agent.on_user_input
        self.agent.on_user_input = on_user_input

        import time as _time

        live_st: Optional[dict] = None
        if _env_telegram_live_enabled() and self._loop and self._app:
            try:
                pm = await context.bot.send_message(
                    chat_id=int(chat_id),
                    text=f"{_TG_LIVE_PLACEHOLDER}\n\n{preview}",
                    reply_to_message_id=update.message.message_id,
                )
                live_st = {
                    "chat_id": int(chat_id),
                    "message_id": pm.message_id,
                    "bot": context.bot,
                    "debounce_s": _env_telegram_live_debounce_s(),
                    "lines": [],
                    "debounce_task": None,
                }
            except Exception as ex:
                logger.debug("Telegram live preview placeholder send failed: %s", ex)

        original_on_tool_start = self.agent.on_tool_start
        original_on_tool_end = self.agent.on_tool_end
        if live_st and self._loop is not None:
            ploop = self._loop

            def on_tool_start(name, input_data, decision):
                line = self._format_tool_progress_start(name, decision)
                self._schedule_live_preview_fragment(live_st, line, ploop)

            def on_tool_end(name, ok, output):
                line = self._format_tool_progress_end(name, ok)
                self._schedule_live_preview_fragment(live_st, line, ploop)

            self.agent.on_tool_start = on_tool_start
            self.agent.on_tool_end = on_tool_end

        t0 = _time.monotonic()
        self._inflight_by_principal[principal_id] = {"started_at": t0, "preview": preview}
        try:
            # Run sync think() off the asyncio loop — calling think() directly blocks PTB's
            # event loop (think() uses future.result() when a loop is already running).
            r = await asyncio.wait_for(
                asyncio.to_thread(self._think_for_principal, principal_id, text),
                timeout=600.0,
            )
            logger.info(
                "msg out | pid=%s | %s risk=%.2f tools=%d turns=%d chars=%d in %.1fs",
                principal_id, r.decision, r.risk, r.tool_calls_made, r.turns_used, len(r.text or ""),
                _time.monotonic() - t0,
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

            if live_st and live_st.get("message_id") is not None:
                await self._cancel_live_debounce(live_st)

            # Telegram 4096 char limit
            if len(response_text) > 4000:
                response_text = response_text[:4000] + "\n\n...truncated"

            await self._deliver_telegram_response(update, context, response_text, live_st)

        except asyncio.TimeoutError:
            logger.warning("Telegram handler: think() exceeded 600s")
            if live_st and live_st.get("message_id") is not None:
                try:
                    await self._cancel_live_debounce(live_st)
                except Exception:
                    pass
            err = "⏱ That took too long (10 minute limit). Try a shorter question or check server logs."
            if live_st and live_st.get("message_id") is not None:
                try:
                    await context.bot.delete_message(
                        chat_id=live_st["chat_id"],
                        message_id=live_st["message_id"],
                    )
                except Exception:
                    pass
            await update.message.reply_text(err)
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            if live_st and live_st.get("message_id") is not None:
                try:
                    await self._cancel_live_debounce(live_st)
                except Exception:
                    pass
            if live_st and live_st.get("message_id") is not None:
                try:
                    await context.bot.delete_message(
                        chat_id=live_st["chat_id"],
                        message_id=live_st["message_id"],
                    )
                except Exception:
                    pass
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")

        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass
            self._inflight_by_principal.pop(principal_id, None)
            self.agent.on_user_input = original_input
            self.agent.on_tool_start = original_on_tool_start
            self.agent.on_tool_end = original_on_tool_end
            if live_st and live_st.get("debounce_task") is not None:
                tsk = live_st.get("debounce_task")
                if tsk and not tsk.done():
                    tsk.cancel()
                    try:
                        await tsk
                    except asyncio.CancelledError:
                        pass

    async def _typing_keepalive(self, bot, chat_id: int):
        """Keep Telegram's typing indicator visible during long-running tasks."""
        try:
            while True:
                await asyncio.sleep(self._typing_interval_seconds)
                await bot.send_chat_action(chat_id=chat_id, action="typing")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Telegram typing keepalive stopped: %s", exc)

    def _think_for_principal(self, principal_id: str, text: str):
        self.agent.set_principal(principal_id)
        # Bind this Telegram chat as the active outbound channel so tools like
        # send_file deliver attachments back to the same conversation. The
        # principal_id format is "telegram:dm:{user_id}" or
        # "telegram:group:{chat_id}:user:{user_id}" — extract the chat id
        # accordingly so groups stay routed to the room, not the user's DM.
        chat_id: Optional[str] = None
        parts = principal_id.split(":")
        if len(parts) >= 3 and parts[0] == "telegram":
            if parts[1] == "dm":
                chat_id = parts[2]
            elif parts[1] == "group" and len(parts) >= 3:
                chat_id = parts[2]
        self.agent.set_active_channel(self, chat_id)
        try:
            return self.agent.think(text)
        finally:
            self.agent.set_active_channel(None, None)

    def _build_approval_handler(self, *, chat_id: int, context, principal_id: str = "telegram"):
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

            logger.info("approval| pid=%s | id=%s awaiting user", principal_id, approval_id)
            if not event.wait(timeout=self.APPROVAL_TIMEOUT_S):
                self._pending_approvals.pop(approval_id, None)
                logger.info("approval| pid=%s | id=%s TIMEOUT -> deny", principal_id, approval_id)
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
            logger.info("approval| pid=%s | id=%s answer=%s", principal_id, approval_id, result["answer"])
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
