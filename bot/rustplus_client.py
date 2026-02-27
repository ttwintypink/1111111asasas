from __future__ import annotations
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import websockets
from google.protobuf.json_format import MessageToDict

from . import rustplus_pb2 as pb

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]

@dataclass(slots=True)
class RustCredentials:
    server_ip: str
    app_port: int
    player_id: int
    player_token: int
    use_facepunch_proxy: bool = False

class RustPlusError(Exception):
    pass

class RustPlusClient:
    def __init__(self, creds: RustCredentials):
        self.creds = creds
        self.seq = 0
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.pending: dict[int, asyncio.Future] = {}
        self.handlers: list[MessageHandler] = []
        self.reader_task: asyncio.Task | None = None
        self.connected = asyncio.Event()
        self._closing = False
        self._lock = asyncio.Lock()

    @property
    def address(self) -> str:
        if self.creds.use_facepunch_proxy:
            return f"wss://companion-rust.facepunch.com/game/{self.creds.server_ip}/{self.creds.app_port}"
        return f"ws://{self.creds.server_ip}:{self.creds.app_port}"

    def add_handler(self, handler: MessageHandler) -> None:
        self.handlers.append(handler)

    async def connect(self) -> None:
        if self.ws and not self.ws.closed:
            return
        self._closing = False
        self.ws = await websockets.connect(self.address, ping_interval=20, ping_timeout=20, max_size=None)
        self.connected.set()
        self.reader_task = asyncio.create_task(self._reader(), name='rustplus-reader')
        logger.info('Connected to Rust+ websocket %s', self.address)

    async def disconnect(self) -> None:
        self._closing = True
        self.connected.clear()
        if self.reader_task:
            self.reader_task.cancel()
            self.reader_task = None
        if self.ws:
            await self.ws.close()
            self.ws = None
        for fut in list(self.pending.values()):
            if not fut.done():
                fut.set_exception(RustPlusError('Disconnected'))
        self.pending.clear()

    async def _reader(self) -> None:
        assert self.ws is not None
        try:
            async for raw in self.ws:
                msg = pb.AppMessage()
                msg.ParseFromString(raw)
                data = MessageToDict(msg, preserving_proto_field_name=True)
                response = data.get('response')
                if response and 'seq' in response:
                    seq = int(response['seq'])
                    fut = self.pending.pop(seq, None)
                    if fut and not fut.done():
                        fut.set_result(data)
                        continue
                for handler in self.handlers:
                    try:
                        await handler(data)
                    except Exception:
                        logger.exception('Rust+ handler failed')
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.exception('Rust+ reader failed')
            if not self._closing:
                for fut in list(self.pending.values()):
                    if not fut.done():
                        fut.set_exception(exc)
                self.pending.clear()
        finally:
            self.connected.clear()

    def _next_seq(self) -> int:
        self.seq += 1
        return self.seq

    async def send_request(self, payload: dict[str, Any], timeout: float = 10.0) -> dict[str, Any]:
        async with self._lock:
            if not self.ws or self.ws.closed:
                raise RustPlusError('Not connected to Rust server')
            seq = self._next_seq()
            req = pb.AppRequest()
            req.seq = seq
            req.playerId = int(self.creds.player_id)
            req.playerToken = int(self.creds.player_token)
            entity_id = payload.get('entity_id')
            if entity_id is not None:
                req.entityId = int(entity_id)
            self._apply_payload(req, payload)
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            self.pending[seq] = fut
            await self.ws.send(req.SerializeToString())
        result = await asyncio.wait_for(fut, timeout=timeout)
        response = result.get('response', {})
        if 'error' in response:
            err = response['error']
            message = err['error'] if isinstance(err, dict) and 'error' in err else str(err)
            raise RustPlusError(message)
        return response

    def _apply_payload(self, req: pb.AppRequest, payload: dict[str, Any]) -> None:
        kind = payload['type']
        if kind == 'get_info':
            req.getInfo.SetInParent()
        elif kind == 'get_time':
            req.getTime.SetInParent()
        elif kind == 'get_map':
            req.getMap.SetInParent()
        elif kind == 'get_team_info':
            req.getTeamInfo.SetInParent()
        elif kind == 'get_team_chat':
            req.getTeamChat.SetInParent()
        elif kind == 'send_team_message':
            req.sendTeamMessage.message = payload['message']
        elif kind == 'get_entity_info':
            req.getEntityInfo.SetInParent()
        elif kind == 'set_entity_value':
            req.setEntityValue.value = bool(payload['value'])
        elif kind == 'check_subscription':
            req.checkSubscription.SetInParent()
        elif kind == 'set_subscription':
            req.setSubscription.value = bool(payload['value'])
        elif kind == 'get_map_markers':
            req.getMapMarkers.SetInParent()
        elif kind == 'promote_to_leader':
            req.promoteToLeader.steamId = int(payload['steam_id'])
        elif kind == 'camera_subscribe':
            req.cameraSubscribe.cameraId = payload['camera_id']
        elif kind == 'camera_unsubscribe':
            req.cameraUnsubscribe.SetInParent()
        elif kind == 'camera_input':
            req.cameraInput.buttons = int(payload['buttons'])
            req.cameraInput.mouseDelta.x = float(payload['x'])
            req.cameraInput.mouseDelta.y = float(payload['y'])
        else:
            raise RustPlusError(f'Unsupported request type: {kind}')

    async def get_info(self):
        return await self.send_request({'type': 'get_info'})

    async def get_time(self):
        return await self.send_request({'type': 'get_time'})

    async def get_map(self):
        return await self.send_request({'type': 'get_map'}, timeout=30)

    async def get_team_info(self):
        return await self.send_request({'type': 'get_team_info'})

    async def get_team_chat(self):
        return await self.send_request({'type': 'get_team_chat'})

    async def send_team_message(self, message: str):
        return await self.send_request({'type': 'send_team_message', 'message': message})

    async def get_entity_info(self, entity_id: int):
        return await self.send_request({'type': 'get_entity_info', 'entity_id': entity_id})

    async def set_entity_value(self, entity_id: int, value: bool):
        return await self.send_request({'type': 'set_entity_value', 'entity_id': entity_id, 'value': value})

    async def check_subscription(self, entity_id: int):
        return await self.send_request({'type': 'check_subscription', 'entity_id': entity_id})

    async def set_subscription(self, entity_id: int, value: bool):
        return await self.send_request({'type': 'set_subscription', 'entity_id': entity_id, 'value': value})

    async def get_map_markers(self):
        return await self.send_request({'type': 'get_map_markers'})

    async def promote_to_leader(self, steam_id: int):
        return await self.send_request({'type': 'promote_to_leader', 'steam_id': steam_id})
