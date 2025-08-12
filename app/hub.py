"""WebSocket hub for broadcasting messages to connected clients."""
from __future__ import annotations

from typing import Dict, Set

from fastapi import WebSocket


class Hub:
    """Tracks active WebSocket connections and sends broadcasts."""

    def __init__(self) -> None:
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, payload: Dict) -> None:
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = Hub()
