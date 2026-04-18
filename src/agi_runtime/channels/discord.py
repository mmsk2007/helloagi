"""Discord channel adapter for HelloAGI.

Uses discord.py library to run HelloAGI as a Discord bot.
Supports:
  - Text messages in channels/DMs → agent.think()
  - Slash commands: /tools, /skills, /identity, /new
  - Per-user sessions
  - Typing indicator during thinking
  - Embed formatting for rich responses

Setup:
  1. pip install discord.py
  2. Set DISCORD_BOT_TOKEN environment variable
  3. helloagi serve --discord
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from agi_runtime.channels.base import BaseChannel, ChannelMessage, ChannelResponse
from agi_runtime.core.agent import HelloAGIAgent

logger = logging.getLogger("helloagi.discord")


class DiscordChannel(BaseChannel):
    """Discord bot channel for HelloAGI."""

    def __init__(self, agent: HelloAGIAgent, token: Optional[str] = None):
        super().__init__("discord")
        self.agent = agent
        self.token = token or os.environ.get("DISCORD_BOT_TOKEN", "")
        self._client = None

    @staticmethod
    def _is_dm_channel(channel) -> bool:
        channel_type = str(getattr(channel, "type", "")).lower()
        return "private" in channel_type or "dm" in channel_type

    def _principal_for_interaction(self, interaction) -> str:
        user_id = str(interaction.user.id)
        if self._is_dm_channel(interaction.channel):
            return f"discord:dm:{user_id}"
        channel_id = str(interaction.channel_id or "")
        return f"discord:channel:{channel_id}:user:{user_id}"

    def _principal_for_message(self, message) -> str:
        user_id = str(message.author.id)
        if self._is_dm_channel(message.channel):
            return f"discord:dm:{user_id}"
        channel_id = str(message.channel.id)
        return f"discord:channel:{channel_id}:user:{user_id}"

    async def start(self):
        """Start the Discord bot."""
        if not self.token:
            raise ValueError(
                "Discord bot token not configured. "
                "Set DISCORD_BOT_TOKEN environment variable."
            )

        try:
            import discord
            from discord.ext import commands
        except ImportError:
            raise ImportError("discord.py required: pip install discord.py")

        intents = discord.Intents.default()
        intents.message_content = True

        bot = commands.Bot(command_prefix="!", intents=intents)
        self._client = bot
        agent = self.agent
        channel_self = self

        @bot.event
        async def on_ready():
            logger.info(f"Discord bot connected as {bot.user}")
            try:
                synced = await bot.tree.sync()
                logger.info(f"Synced {len(synced)} slash commands")
            except Exception as e:
                logger.error(f"Failed to sync commands: {e}")

        @bot.tree.command(name="tools", description="List available tools")
        async def cmd_tools(interaction: discord.Interaction):
            info = agent.get_tools_info()
            if len(info) > 1900:
                info = info[:1900] + "\n..."
            await interaction.response.send_message(f"```\n{info}\n```")

        @bot.tree.command(name="skills", description="List learned skills")
        async def cmd_skills(interaction: discord.Interaction):
            skills = agent.skills.list_skills()
            if skills:
                lines = [f"**{s.name}**: {s.description} (used {s.invoke_count}x)" for s in skills]
                await interaction.response.send_message("\n".join(lines))
            else:
                await interaction.response.send_message("*No skills learned yet.*")

        @bot.tree.command(name="identity", description="Show agent identity")
        async def cmd_identity(interaction: discord.Interaction):
            state = agent.identity.state
            embed = discord.Embed(
                title=state.name,
                description=state.character,
                color=discord.Color.purple(),
            )
            embed.add_field(name="Purpose", value=state.purpose, inline=False)
            embed.add_field(
                name="Principles",
                value="\n".join(f"• {p}" for p in state.principles),
                inline=False,
            )
            await interaction.response.send_message(embed=embed)

        @bot.tree.command(name="new", description="Start fresh conversation")
        async def cmd_new(interaction: discord.Interaction):
            user_id = str(interaction.user.id)
            channel_self.clear_session(user_id)
            agent.clear_history(principal_id=channel_self._principal_for_interaction(interaction))
            await interaction.response.send_message("🔄 Fresh conversation started.")

        @bot.tree.command(name="ask", description="Ask HelloAGI a question")
        async def cmd_ask(interaction: discord.Interaction, message: str):
            await interaction.response.defer(thinking=True)

            original_input = agent.on_user_input
            agent.on_user_input = lambda prompt: "y"  # Auto-approve in Discord

            try:
                agent.set_principal(channel_self._principal_for_interaction(interaction))
                r = agent.think(message)

                gov_icon = {"allow": "🟢", "escalate": "🟡", "deny": "🔴"}.get(r.decision, "⬜")

                embed = discord.Embed(
                    description=r.text[:4000] if len(r.text) > 4000 else r.text,
                    color=discord.Color.green() if r.decision == "allow" else discord.Color.red(),
                )
                embed.set_footer(
                    text=f"{gov_icon} {r.decision} | risk: {r.risk:.2f} | "
                         f"{r.tool_calls_made} tools | {r.turns_used} turns"
                )

                await interaction.followup.send(embed=embed)

            except Exception as e:
                logger.error(f"Error in /ask: {e}")
                await interaction.followup.send(f"❌ Error: {str(e)[:200]}")
            finally:
                agent.on_user_input = original_input

        @bot.event
        async def on_message(message: discord.Message):
            if message.author == bot.user:
                return

            # Only respond to DMs or when mentioned
            if not isinstance(message.channel, discord.DMChannel) and bot.user not in message.mentions:
                return

            # Strip mention from message
            text = message.content.replace(f"<@{bot.user.id}>", "").strip()
            if not text:
                return

            async with message.channel.typing():
                original_input = agent.on_user_input
                agent.on_user_input = lambda prompt: "y"

                try:
                    agent.set_principal(channel_self._principal_for_message(message))
                    r = agent.think(text)

                    gov_icon = {"allow": "🟢", "escalate": "🟡", "deny": "🔴"}.get(r.decision, "⬜")
                    header = f"{gov_icon} `{r.decision}` | risk: {r.risk:.2f}"
                    if r.tool_calls_made > 0:
                        header += f" | {r.tool_calls_made} tools in {r.turns_used} turns"

                    response_text = f"{header}\n\n{r.text}"

                    # Discord 2000 char limit
                    if len(response_text) > 1900:
                        response_text = response_text[:1900] + "\n\n*...truncated*"

                    await message.reply(response_text)

                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    await message.reply(f"❌ Error: {str(e)[:200]}")
                finally:
                    agent.on_user_input = original_input

        await bot.start(self.token)

    async def stop(self):
        """Stop the Discord bot."""
        if self._client:
            await self._client.close()
            logger.info("Discord bot stopped")

    async def send(self, channel_id: str, text: str, **kwargs):
        """Send a message to a Discord channel."""
        if self._client:
            channel = self._client.get_channel(int(channel_id))
            if channel:
                await channel.send(text)
