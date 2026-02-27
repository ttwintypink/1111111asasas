from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .config import settings
from .rustplus_client import RustCredentials, RustPlusClient, RustPlusError
from .storage import Storage
from .translator import translator
from .utils import clamp_text, ts_to_iso

logger = logging.getLogger(__name__)

CHANNEL_NAMES = {
    'category': 'rust++',
    'teamchat': 'тимчат',
    'events': 'события',
    'commands': 'команды',
    'logs': 'логи',
}

class RustDiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        super().__init__(command_prefix=settings.command_prefix, intents=intents)
        self.storage = Storage()
        self.rust_clients: dict[int, RustPlusClient] = {}
        self.tree.on_error = self.on_app_command_error
        self.poll_snapshots.start()

    async def setup_hook(self) -> None:
        self.tree.add_command(setup_channels)
        self.tree.add_command(set_rust_server)
        self.tree.add_command(rust_connect)
        self.tree.add_command(rust_disconnect)
        self.tree.add_command(rust_status)
        self.tree.add_command(rust_team)
        self.tree.add_command(rust_time)
        self.tree.add_command(rust_map)
        self.tree.add_command(rust_markers)
        self.tree.add_command(rust_entity)
        self.tree.add_command(rust_switch)
        self.tree.add_command(rust_sendteam)
        self.tree.add_command(rust_watch_entity)
        self.tree.add_command(rust_unwatch_entity)
        await self.tree.sync()

    async def on_ready(self):
        logger.info('Discord bot ready as %s', self.user)

    async def close(self):
        self.poll_snapshots.cancel()
        for client in list(self.rust_clients.values()):
            await client.disconnect()
        await super().close()

    async def ensure_channels(self, guild: discord.Guild) -> dict[str, int | None]:
        data = self.storage.load_guild(guild.id)
        cat = discord.utils.get(guild.categories, name=CHANNEL_NAMES['category'])
        if cat is None:
            cat = await guild.create_category(CHANNEL_NAMES['category'])
        channels = data['channels']
        for key in ['teamchat', 'events', 'commands', 'logs']:
            target_name = CHANNEL_NAMES[key]
            channel = guild.get_channel(channels.get(key) or 0)
            if channel is None:
                channel = discord.utils.get(cat.text_channels, name=target_name)
            if channel is None:
                channel = await guild.create_text_channel(target_name, category=cat)
            elif channel.name != target_name:
                await channel.edit(name=target_name, category=cat)
            channels[key] = channel.id
        channels['category'] = cat.id
        self.storage.save_guild(guild.id, data)
        return channels

    async def get_or_create_client(self, guild_id: int) -> RustPlusClient:
        existing = self.rust_clients.get(guild_id)
        if existing and existing.connected.is_set():
            return existing
        data = self.storage.load_guild(guild_id)
        rust = data['rust']
        creds = RustCredentials(
            server_ip=rust['server_ip'],
            app_port=int(rust['app_port']),
            player_id=int(rust['player_id']),
            player_token=int(rust['player_token']),
            use_facepunch_proxy=bool(rust.get('use_proxy', settings.rust_proxy)),
        )
        client = RustPlusClient(creds)
        client.add_handler(lambda payload, gid=guild_id: self.handle_rust_message(gid, payload))
        await client.connect()
        self.rust_clients[guild_id] = client
        data['rust']['connected'] = True
        self.storage.save_guild(guild_id, data)
        await self.resubscribe_entities(guild_id)
        return client

    async def disconnect_client(self, guild_id: int) -> None:
        client = self.rust_clients.pop(guild_id, None)
        if client:
            await client.disconnect()
        data = self.storage.load_guild(guild_id)
        data['rust']['connected'] = False
        self.storage.save_guild(guild_id, data)

    async def resubscribe_entities(self, guild_id: int) -> None:
        client = self.rust_clients.get(guild_id)
        if not client:
            return
        data = self.storage.load_guild(guild_id)
        for entity_id, meta in data['watch_entities'].items():
            try:
                await client.get_entity_info(int(entity_id))
                await client.set_subscription(int(entity_id), True)
            except Exception:
                logger.exception('Failed to resubscribe entity %s (%s)', entity_id, meta)

    async def handle_rust_message(self, guild_id: int, payload: dict[str, Any]) -> None:
        data = self.storage.load_guild(guild_id)
        guild = self.get_guild(guild_id)
        if guild is None:
            return
        channels = data['channels']
        broadcast = payload.get('broadcast', {})

        if 'teamMessage' in broadcast:
            channel = guild.get_channel(channels.get('teamchat') or 0)
            if isinstance(channel, discord.TextChannel):
                message = broadcast['teamMessage']['message']
                name = message.get('name', 'Unknown')
                content = message.get('message', '')
                lines = [f'**{name}**: {content}']
                if data['relay'].get('translate_incoming', True):
                    translated = await translator.translate(content, 'en', 'ru')
                    if translated and translated != content:
                        lines.append(f'🇷🇺 **Перевод:** {translated}')
                await channel.send(clamp_text('\n'.join(lines)))

        if 'entityChanged' in broadcast:
            entity = broadcast['entityChanged']
            entity_id = str(entity.get('entityId'))
            watched = data['watch_entities'].get(entity_id)
            if watched:
                channel = guild.get_channel(channels.get('events') or 0)
                if isinstance(channel, discord.TextChannel):
                    payload_data = entity.get('payload', {})
                    value = payload_data.get('value')
                    items = payload_data.get('items', [])
                    if items:
                        item_text = ', '.join(f"{i.get('itemId')}×{i.get('quantity')}" for i in items[:10])
                        body = f"Контейнер **{watched.get('name','entity')}** (`{entity_id}`) обновился: {item_text}"
                    else:
                        state = 'ВКЛ' if value else 'ВЫКЛ'
                        body = f"Сущность **{watched.get('name','entity')}** (`{entity_id}`) изменилась: **{state}**"
                    await channel.send(body)

        if 'teamChanged' in broadcast:
            data['last_team'] = broadcast['teamChanged']
            self.storage.save_guild(guild_id, data)

    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        data = self.storage.load_guild(message.guild.id)
        teamchat_id = data['channels'].get('teamchat')
        if message.channel.id == teamchat_id and data['relay'].get('discord_to_rust', True):
            client = self.rust_clients.get(message.guild.id)
            if client and client.connected.is_set():
                outgoing = message.content.strip()
                if outgoing:
                    if data['relay'].get('translate_outgoing', True):
                        outgoing = await translator.translate(outgoing, 'ru', 'en')
                    try:
                        await client.send_team_message(outgoing)
                    except Exception as exc:
                        await message.channel.send(f'Не удалось отправить сообщение в Rust: `{exc}`')
        await self.process_commands(message)

    @tasks.loop(seconds=45)
    async def poll_snapshots(self):
        await self.wait_until_ready()
        for guild_id, client in list(self.rust_clients.items()):
            if not client.connected.is_set():
                continue
            data = self.storage.load_guild(guild_id)
            try:
                info = await client.get_info()
                team = await client.get_team_info()
                time = await client.get_time()
                data['snapshot'] = {
                    'info': info.get('info', {}),
                    'team': team.get('teamInfo', {}),
                    'time': time.get('time', {}),
                }
                self.storage.save_guild(guild_id, data)
            except Exception:
                logger.exception('Polling failed for guild %s', guild_id)

    @poll_snapshots.before_loop
    async def before_poll(self):
        await self.wait_until_ready()

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        logger.exception('App command failed', exc_info=error)
        msg = f'Ошибка: `{error}`'
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

bot = RustDiscordBot()


def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        return bool(interaction.user.guild_permissions.administrator)
    return app_commands.check(predicate)


@admin_only()
@app_commands.command(name='setup_channels', description='Создать или переименовать русские каналы Rust++')
async def setup_channels(interaction: discord.Interaction):
    assert interaction.guild
    channels = await bot.ensure_channels(interaction.guild)
    text = '\n'.join(f'- {k}: <#{v}>' for k, v in channels.items() if k != 'category' and v)
    await interaction.response.send_message(f'Каналы настроены:\n{text}', ephemeral=True)


@admin_only()
@app_commands.command(name='set_rust_server', description='Сохранить данные Rust+ сервера')
@app_commands.describe(server_ip='IP или домен Rust сервера', app_port='app.port', player_id='Steam ID', player_token='Player token', use_proxy='Использовать прокси Facepunch')
async def set_rust_server(interaction: discord.Interaction, server_ip: str, app_port: int, player_id: str, player_token: int, use_proxy: bool = False):
    assert interaction.guild
    data = bot.storage.load_guild(interaction.guild.id)
    data['rust'].update({
        'server_ip': server_ip.strip(),
        'app_port': int(app_port),
        'player_id': str(player_id).strip(),
        'player_token': int(player_token),
        'use_proxy': use_proxy,
    })
    bot.storage.save_guild(interaction.guild.id, data)
    await interaction.response.send_message('Данные Rust+ сервера сохранены.', ephemeral=True)


@admin_only()
@app_commands.command(name='rust_connect', description='Подключить бота к Rust+ серверу')
async def rust_connect(interaction: discord.Interaction):
    assert interaction.guild
    await interaction.response.defer(ephemeral=True, thinking=True)
    client = await bot.get_or_create_client(interaction.guild.id)
    info = await client.get_info()
    await bot.ensure_channels(interaction.guild)
    await interaction.followup.send(f"Подключено к **{info.get('info', {}).get('name', 'Rust серверу')}**.", ephemeral=True)


@admin_only()
@app_commands.command(name='rust_disconnect', description='Отключить бота от Rust+ сервера')
async def rust_disconnect(interaction: discord.Interaction):
    assert interaction.guild
    await bot.disconnect_client(interaction.guild.id)
    await interaction.response.send_message('Отключено от Rust+ сервера.', ephemeral=True)


@app_commands.command(name='rust_status', description='Показать статус Rust сервера')
async def rust_status(interaction: discord.Interaction):
    assert interaction.guild
    await interaction.response.defer(thinking=True)
    client = await bot.get_or_create_client(interaction.guild.id)
    info = await client.get_info()
    body = info.get('info', {})
    embed = discord.Embed(title=body.get('name', 'Rust сервер'))
    embed.add_field(name='Игроки', value=f"{body.get('players', 0)}/{body.get('maxPlayers', 0)}")
    embed.add_field(name='Очередь', value=str(body.get('queuedPlayers', 0)))
    embed.add_field(name='Карта', value=body.get('map', '—'), inline=False)
    embed.add_field(name='Wipe', value=ts_to_iso(body.get('wipeTime')))
    await interaction.followup.send(embed=embed)


@app_commands.command(name='rust_team', description='Показать участников команды')
async def rust_team(interaction: discord.Interaction):
    assert interaction.guild
    await interaction.response.defer(thinking=True)
    client = await bot.get_or_create_client(interaction.guild.id)
    team = await client.get_team_info()
    members = team.get('teamInfo', {}).get('members', [])
    if not members:
        await interaction.followup.send('Команда пуста или данные не получены.')
        return
    lines = []
    for m in members:
        state = '🟢 online' if m.get('isOnline') else '⚫ offline'
        alive = 'жив' if m.get('isAlive') else 'мёртв'
        lines.append(f"**{m.get('name','?')}** — {state}, {alive}, x={m.get('x','?')} y={m.get('y','?')}")
    await interaction.followup.send(clamp_text('\n'.join(lines)))


@app_commands.command(name='rust_time', description='Показать игровое время')
async def rust_time(interaction: discord.Interaction):
    assert interaction.guild
    await interaction.response.defer(thinking=True)
    client = await bot.get_or_create_client(interaction.guild.id)
    time = (await client.get_time()).get('time', {})
    await interaction.followup.send(
        f"Время: **{time.get('time', '—')}**\nВосход: **{time.get('sunrise', '—')}**\nЗакат: **{time.get('sunset', '—')}**\nДлина дня: **{time.get('dayLengthMinutes', '—')} мин**"
    )


@app_commands.command(name='rust_map', description='Получить текущую карту сервера')
async def rust_map(interaction: discord.Interaction):
    assert interaction.guild
    await interaction.response.defer(thinking=True)
    client = await bot.get_or_create_client(interaction.guild.id)
    response = await client.get_map()
    jpg_hex = response.get('map', {}).get('jpgImage')
    if not jpg_hex:
        await interaction.followup.send('Сервер не вернул изображение карты.')
        return
    if isinstance(jpg_hex, str):
        import base64
        jpg_bytes = base64.b64decode(jpg_hex)
    else:
        jpg_bytes = jpg_hex
    path = bot.storage.save_map(interaction.guild.id, jpg_bytes)
    await interaction.followup.send(file=discord.File(path, filename='rust_map.jpg'))


@app_commands.command(name='rust_markers', description='Показать маркеры карты')
async def rust_markers(interaction: discord.Interaction):
    assert interaction.guild
    await interaction.response.defer(thinking=True)
    client = await bot.get_or_create_client(interaction.guild.id)
    markers = (await client.get_map_markers()).get('mapMarkers', {}).get('markers', [])
    if not markers:
        await interaction.followup.send('Маркеры не найдены.')
        return
    lines = []
    for m in markers[:25]:
        lines.append(f"`{m.get('id')}` {m.get('type')} — {m.get('name', 'без имени')} (x={m.get('x')}, y={m.get('y')})")
    await interaction.followup.send(clamp_text('\n'.join(lines)))


@app_commands.command(name='rust_entity', description='Показать информацию о сущности')
@app_commands.describe(entity_id='ID smart switch / smart alarm / storage monitor')
async def rust_entity(interaction: discord.Interaction, entity_id: int):
    assert interaction.guild
    await interaction.response.defer(thinking=True)
    client = await bot.get_or_create_client(interaction.guild.id)
    entity = (await client.get_entity_info(entity_id)).get('entityInfo', {})
    payload = entity.get('payload', {})
    lines = [f"Тип: **{entity.get('type', '—')}**"]
    if 'value' in payload:
        lines.append(f"Состояние: **{'ВКЛ' if payload.get('value') else 'ВЫКЛ'}**")
    if 'capacity' in payload:
        lines.append(f"Вместимость: **{payload.get('capacity')}**")
    items = payload.get('items', [])
    if items:
        lines.append('Предметы:')
        lines.extend(f"- {i.get('itemId')} × {i.get('quantity')}" for i in items[:20])
    await interaction.followup.send(clamp_text('\n'.join(lines)))


@app_commands.command(name='rust_switch', description='Включить или выключить smart switch')
@app_commands.describe(entity_id='ID smart switch', state='on / off')
async def rust_switch(interaction: discord.Interaction, entity_id: int, state: str):
    assert interaction.guild
    await interaction.response.defer(thinking=True, ephemeral=True)
    client = await bot.get_or_create_client(interaction.guild.id)
    normalized = state.strip().lower()
    if normalized not in {'on', 'off', '1', '0', 'true', 'false'}:
        await interaction.followup.send('Используй state: `on` или `off`.', ephemeral=True)
        return
    value = normalized in {'on', '1', 'true'}
    await client.set_entity_value(entity_id, value)
    await interaction.followup.send(f'Сущность `{entity_id}` переключена в состояние **{"ON" if value else "OFF"}**.', ephemeral=True)


@app_commands.command(name='rust_sendteam', description='Отправить сообщение в team chat')
@app_commands.describe(message='Сообщение для team chat')
async def rust_sendteam(interaction: discord.Interaction, message: str):
    assert interaction.guild
    await interaction.response.defer(ephemeral=True)
    client = await bot.get_or_create_client(interaction.guild.id)
    data = bot.storage.load_guild(interaction.guild.id)
    outgoing = message
    if data['relay'].get('translate_outgoing', True):
        outgoing = await translator.translate(outgoing, 'ru', 'en')
    await client.send_team_message(outgoing)
    await interaction.followup.send('Сообщение отправлено в team chat.', ephemeral=True)


@admin_only()
@app_commands.command(name='rust_watch_entity', description='Подписаться на события сущности')
@app_commands.describe(entity_id='ID сущности', name='Понятное название')
async def rust_watch_entity(interaction: discord.Interaction, entity_id: int, name: str):
    assert interaction.guild
    await interaction.response.defer(ephemeral=True)
    client = await bot.get_or_create_client(interaction.guild.id)
    data = bot.storage.load_guild(interaction.guild.id)
    data['watch_entities'][str(entity_id)] = {'name': name}
    bot.storage.save_guild(interaction.guild.id, data)
    await client.get_entity_info(entity_id)
    await client.set_subscription(entity_id, True)
    await interaction.followup.send(f'Сущность `{entity_id}` добавлена в подписки.', ephemeral=True)


@admin_only()
@app_commands.command(name='rust_unwatch_entity', description='Убрать подписку на сущность')
async def rust_unwatch_entity(interaction: discord.Interaction, entity_id: int):
    assert interaction.guild
    await interaction.response.defer(ephemeral=True)
    client = await bot.get_or_create_client(interaction.guild.id)
    data = bot.storage.load_guild(interaction.guild.id)
    data['watch_entities'].pop(str(entity_id), None)
    bot.storage.save_guild(interaction.guild.id, data)
    try:
        await client.set_subscription(entity_id, False)
    except Exception:
        pass
    await interaction.followup.send(f'Сущность `{entity_id}` удалена из подписок.', ephemeral=True)
