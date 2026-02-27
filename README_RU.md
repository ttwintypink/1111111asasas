# Rust++ Python bridge edition

Это **расширенная Python-версия** под Python-only хостинг.

Что уже умеет:
- Discord bot на `discord.py`
- русские каналы
- автоперевод EN -> RU для teamchat
- хранение конфигурации и последних snapshot-данных по guild
- slash-команды:
  - `/setup`
  - `/channels`
  - `/translate`
  - `/config`
  - `/rust_setserver`
  - `/rust_server`
  - `/rust_team`
  - `/rust_events`
  - `/rust_entities`
  - `/rust_sendteam`
  - `/rust_switch`
  - `/rust_rawentity`
- HTTP bridge для внешнего Rust worker:
  - `POST /bridge/push/teamchat`
  - `POST /bridge/push/snapshot`
  - `GET /bridge/pull/actions`

## Важное ограничение

В архиве оригинального Node.js проекта **нет исходников самой библиотеки `rustplus.js` и protobuf-схем**, поэтому
сделать полностью прямой низкоуровневый Rust+ transport в этой среде я не могу честно обещать.

Поэтому эта версия делает две вещи:
1. даёт **рабочего Python Discord-бота**;
2. даёт **протокольный слой и очередь действий**, чтобы отдельный Rust worker мог:
   - пушить snapshot-данные в бота,
   - забирать команды из очереди,
   - отправлять teamchat обратно.

## Пример bridge push snapshot

```json
{
  "guild_id": 1234567890,
  "secret": "change_me",
  "snapshot": {
    "server": {
      "name": "My Rust Server",
      "players": 120,
      "max_players": 200,
      "queue": 15,
      "map": "4250 / seed 12345",
      "wipe": "2d 4h ago"
    },
    "time": {
      "time": "14:32",
      "is_day": true
    },
    "team": {
      "players": [
        {"name": "Alex", "is_online": true, "is_leader": true, "is_paired": true},
        {"name": "Nick", "is_online": false, "is_leader": false, "is_paired": false}
      ]
    },
    "events": [
      {"time": "2026-02-27T18:00:00Z", "text": "Cargo ship spawned"}
    ],
    "entities": {
      "12345": {"name": "Main Gate", "type": "switch", "value": true, "reachable": true}
    },
    "map_markers": [
      {"type": "cargo", "x": 1200, "y": 3400}
    ]
  }
}
```

## Пример pull actions

`GET /bridge/pull/actions?guild_id=1234567890&secret=change_me`

Ответ:
```json
{
  "ok": true,
  "actions": [
    {"type": "send_team_message", "message": "hello"},
    {"type": "set_entity_value", "entity_id": "12345", "value": true}
  ]
}
```

## Установка

1. Скопируй `.env.example` в `.env`
2. Укажи `DISCORD_TOKEN`
3. Установи зависимости:
   - `pip install -r requirements.txt`
4. Запусти:
   - `python main.py`

## Что дальше

Если у тебя появится отдельный Python worker с реальной реализацией Rust+ websocket/protobuf,
его можно просто подключить к этому боту через HTTP bridge без переделки Discord-слоя.
