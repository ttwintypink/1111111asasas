# Python Rust++ Bot

Это Python-версия Discord-бота для Rust+, адаптированная под Python-only хостинг.

## Что уже умеет
- подключаться к Rust+ websocket напрямую по protobuf + WebSocket;
- создавать русские каналы (`тимчат`, `события`, `команды`, `логи`);
- пересылать входящий team chat из Rust в Discord;
- автоматически переводить входящий team chat **EN -> RU**;
- по умолчанию переводить сообщения из Discord в **RU -> EN** перед отправкой в Rust;
- показывать статус сервера, команду, время, карту, маркеры;
- получать информацию о smart-entity;
- включать/выключать smart switch;
- подписываться на broadcast-события сущностей.

## Установка
1. Распакуй архив.
2. Скопируй `.env.example` в `.env`.
3. Заполни `DISCORD_TOKEN`.
4. Установи зависимости:
   ```bash
   pip install -r requirements.txt
   ```
5. Запусти:
   ```bash
   python main.py
   ```

## Настройка в Discord
После запуска используй slash-команды:

- `/setup_channels`
- `/set_rust_server server_ip:<ip> app_port:<port> player_id:<steamid> player_token:<token> use_proxy:false`
- `/rust_connect`

## Основные команды
- `/rust_status`
- `/rust_team`
- `/rust_time`
- `/rust_map`
- `/rust_markers`
- `/rust_entity entity_id:<id>`
- `/rust_switch entity_id:<id> state:on`
- `/rust_sendteam message:<текст>`
- `/rust_watch_entity entity_id:<id> name:<название>`
- `/rust_unwatch_entity entity_id:<id>`

## Что важно
Это уже **прямой Python transport Rust+**, а не внешний bridge.
Поддержаны основные AppRequest/AppBroadcast из `rustplus.proto`.

Камеры / clan / nexus / расширенные фичи оригинального RUST++ не доведены до полного паритета.
Но ядро Rust+ (информация, map, markers, team chat, smart entities, subscriptions) реализовано нативно на Python.
