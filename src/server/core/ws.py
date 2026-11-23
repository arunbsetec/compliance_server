import asyncio
import json
import uuid
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, document_id: uuid.UUID, websocket: WebSocket) -> None:
        self._connections[document_id].add(websocket)

    def disconnect(self, document_id: uuid.UUID, websocket: WebSocket) -> None:
        sockets = self._connections.get(document_id)
        if sockets is None:
            return
        sockets.discard(websocket)
        if not sockets:
            self._connections.pop(document_id, None)

    async def broadcast(self, document_id: uuid.UUID, message: dict, close: bool = False) -> None:
        payload = json.dumps(message)
        for websocket in list(self._connections.get(document_id, ())):
            try:
                await websocket.send_text(payload)
                if close:
                    await websocket.close()
                    self.disconnect(document_id, websocket)
            except Exception:
                self.disconnect(document_id, websocket)

    def publish(self, document_id: uuid.UUID, message: dict, close: bool = False) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        future = asyncio.run_coroutine_threadsafe(
            self.broadcast(document_id, message, close),
            loop,
        )
        future.result(timeout=5)


connection_manager = ConnectionManager()
