from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from rustplusplus_py.config import Settings
from rustplusplus_py.protocol.client import RustPlusProtocolClient
from rustplusplus_py.services.channel_setup import ChannelSetupService
from rustplusplus_py.services.guild_state import GuildStateService
from rustplusplus_py.services.http_bridge import HttpBridge
from rustplusplus_py.services.snapshot_formatter import format_entities, format_events, format_server, format_team
from rustplusplus_py.services.translation import TranslatorService


logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("rustplusplus_py")


class RustPlusPythonBot(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True

        super().__init__(
            command_prefix=settings.bot_prefix,
            intents=intents,
            help_command=None,
        )
        self.settings = settings
        self.guild_state_service = GuildStateService()
        self.channel_setup_service = ChannelSetupService(self.guild_state_service, settings.category_name)
        self.translator = TranslatorService(settings.translate_source, settings.translate_target)
        self.protocol = RustPlusProtocolClient()
        self.http_bridge: Optional[HttpBridge] = None

    async def setup_hook(self) -> None:
        for cmd in (
            self.cmd_setup,
            self.cmd_translate,
            self.cmd_channels,
            self.cmd_ping,
            self.cmd_config,
            self.cmd_rust_server,
            self.cmd_rust_team,
            self.cmd_rust_events,
            self.cmd_rust_entities,
            self.cmd_rust_setserver,
            self.cmd_rust_sendteam,
            self.cmd_rust_switch,
            self.cmd_rust_rawentity,
        ):
            self.tree.add_command(cmd)

        if self.settings.discord_guild_id:
            guild_obj = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
        else:
            await self.tree.sync()

        if self.settings.http_enabled:
            self.http_bridge = HttpBridge(self, self.settings.http_host, self.settings.http_port, self.settings.http_shared_secret)
            await self.http_bridge.start()
            log.info("HTTP bridge started on %s:%s", self.settings.http_host, self.settings.http_port)

    async def close(self) -> None:
        if self.http_bridge is not None:
            await self.http_bridge.stop()
        await super().close()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")
        for guild in self.guilds:
            try:
                await self.channel_setup_service.ensure(guild)
            except Exception as exc:
                log.exception("Failed to setup guild %s: %s", guild.id, exc)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.channel_setup_service.ensure(guild)

    async def maybe_publish_snapshot(self, guild_id: int) -> None:
        guild = self.get_guild(guild_id)
        if guild is None:
            return
        state = self.guild_state_service.load(guild_id)
        info_id = state.get("channels", {}).get("information")
        channel = guild.get_channel(info_id or 0)
        if isinstance(channel, discord.TextChannel):
            snapshot = state.get("snapshot", {})
            embed = discord.Embed(title="Rust+ информация")
            embed.description = format_server(snapshot)
            await channel.send(embed=embed)

    async def post_external_teamchat(self, guild_id: int, author: str, content: str) -> None:
        guild = self.get_guild(guild_id)
        if guild is None:
            raise ValueError(f"Guild {guild_id} not found")
        state = self.guild_state_service.load(guild.id)
        channel_id = state.get("channels", {}).get("teamchat")
        channel = guild.get_channel(channel_id or 0)
        if not isinstance(channel, discord.TextChannel):
            raise ValueError("Teamchat channel not found")
        await self._send_translated_message(channel, author, content, external=True)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        state = self.guild_state_service.load(message.guild.id)
        teamchat_id = state.get("channels", {}).get("teamchat")
        if message.channel.id == teamchat_id and state.get("translate_enabled", True):
            await self._send_translated_message(message.channel, message.author.display_name, message.content)
            await self.protocol.send_team_message(self.guild_state_service, message.guild.id, message.content)

        await self.process_commands(message)

    async def _send_translated_message(
        self,
        channel: discord.TextChannel,
        author_name: str,
        content: str,
        external: bool = False,
    ) -> None:
        content = (content or "").strip()
        if not content:
            return

        result = await self.translator.translate(content)
        embed = discord.Embed(title="Team Chat", description=result.original)
        embed.add_field(name="Автор", value=author_name, inline=False)
        if result.changed:
            embed.add_field(name="🇷🇺 Перевод", value=result.translated[:1024], inline=False)
        if external:
            embed.set_footer(text="Источник: Rust bridge")
        else:
            embed.set_footer(text="Источник: Discord → очередь Rust+")
        await channel.send(embed=embed)

    @app_commands.command(name="setup", description="Создать или обновить русские каналы бота")
    async def cmd_setup(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.channel_setup_service.ensure(interaction.guild)
        await interaction.followup.send("Готово: русские каналы и категория созданы/обновлены.", ephemeral=True)

    @app_commands.command(name="translate", description="Перевести текст с английского на русский")
    @app_commands.describe(text="Текст для перевода")
    async def cmd_translate(self, interaction: discord.Interaction, text: str) -> None:
        await interaction.response.defer(ephemeral=True)
        result = await self.translator.translate(text)
        await interaction.followup.send(f"**Оригинал:** {result.original}\n**Перевод:** {result.translated}", ephemeral=True)

    @app_commands.command(name="channels", description="Показать привязанные каналы")
    async def cmd_channels(self, interaction: discord.Interaction) -> None:
        state = self.guild_state_service.load(interaction.guild.id)
        channels = state.get("channels", {})
        lines = []
        for key, value in channels.items():
            channel = interaction.guild.get_channel(value) if value else None
            lines.append(f"- **{key}**: {channel.mention if channel else 'не найден'}")
        await interaction.response.send_message("\n".join(lines) or "Каналы ещё не созданы.", ephemeral=True)

    @app_commands.command(name="ping", description="Проверить, что бот жив")
    async def cmd_ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"pong ({round(self.latency * 1000)} ms)", ephemeral=True)

    @app_commands.command(name="config", description="Включить или выключить автоперевод")
    @app_commands.describe(enabled="true — включить, false — выключить")
    async def cmd_config(self, interaction: discord.Interaction, enabled: bool) -> None:
        state = self.guild_state_service.load(interaction.guild.id)
        state["translate_enabled"] = enabled
        self.guild_state_service.save(interaction.guild.id, state)
        await interaction.response.send_message(
            f"Автоперевод {'включён' if enabled else 'выключен'}.", ephemeral=True
        )

    @app_commands.command(name="rust_setserver", description="Сохранить данные Rust сервера")
    @app_commands.describe(server_ip="IP", app_port="App Port", steam_id="SteamID", player_token="Player Token", title="Название")
    async def cmd_rust_setserver(
        self,
        interaction: discord.Interaction,
        server_ip: str,
        app_port: int,
        steam_id: str,
        player_token: str,
        title: str = "",
    ) -> None:
        state = self.guild_state_service.load(interaction.guild.id)
        state["server_config"] = {
            "server_ip": server_ip,
            "app_port": app_port,
            "steam_id": steam_id,
            "player_token": player_token,
            "title": title,
        }
        self.guild_state_service.save(interaction.guild.id, state)
        await interaction.response.send_message("Конфиг сервера сохранён.", ephemeral=True)

    @app_commands.command(name="rust_server", description="Показать состояние Rust сервера")
    async def cmd_rust_server(self, interaction: discord.Interaction) -> None:
        state = self.guild_state_service.load(interaction.guild.id)
        await interaction.response.send_message(format_server(state.get("snapshot", {})), ephemeral=True)

    @app_commands.command(name="rust_team", description="Показать состояние команды")
    async def cmd_rust_team(self, interaction: discord.Interaction) -> None:
        state = self.guild_state_service.load(interaction.guild.id)
        await interaction.response.send_message(format_team(state.get("snapshot", {})), ephemeral=True)

    @app_commands.command(name="rust_events", description="Показать последние события")
    async def cmd_rust_events(self, interaction: discord.Interaction) -> None:
        state = self.guild_state_service.load(interaction.guild.id)
        await interaction.response.send_message(format_events(state.get("snapshot", {})), ephemeral=True)

    @app_commands.command(name="rust_entities", description="Показать устройства")
    async def cmd_rust_entities(self, interaction: discord.Interaction) -> None:
        state = self.guild_state_service.load(interaction.guild.id)
        await interaction.response.send_message(format_entities(state.get("snapshot", {})), ephemeral=True)

    @app_commands.command(name="rust_sendteam", description="Отправить сообщение в Rust team chat через очередь")
    @app_commands.describe(message="Текст сообщения")
    async def cmd_rust_sendteam(self, interaction: discord.Interaction, message: str) -> None:
        result = await self.protocol.send_team_message(self.guild_state_service, interaction.guild.id, message)
        await interaction.response.send_message(f"Команда поставлена в очередь: `{result['type']}`", ephemeral=True)

    @app_commands.command(name="rust_switch", description="Включить/выключить устройство через очередь")
    @app_commands.describe(entity_id="ID устройства", value="true/false")
    async def cmd_rust_switch(self, interaction: discord.Interaction, entity_id: str, value: bool) -> None:
        result = await self.protocol.set_entity_value(self.guild_state_service, interaction.guild.id, entity_id, value)
        await interaction.response.send_message(
            f"Команда поставлена в очередь: `{result['type']}` для `{entity_id}` = `{value}`",
            ephemeral=True,
        )

    @app_commands.command(name="rust_rawentity", description="Показать сырые данные устройства")
    @app_commands.describe(entity_id="ID устройства")
    async def cmd_rust_rawentity(self, interaction: discord.Interaction, entity_id: str) -> None:
        state = self.guild_state_service.load(interaction.guild.id)
        entity = await self.protocol.get_entity_info(interaction.guild.id, state, entity_id)
        if not entity:
            await interaction.response.send_message("Нет данных по этому entity_id.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Entity {entity_id}", description="Сырые данные")
        for k, v in list(entity.items())[:20]:
            embed.add_field(name=str(k), value=str(v)[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
