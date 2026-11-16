from fastapi import APIRouter, WebSocket

from config import settings
from services.ws_hub import ConnectionClosed, hub, origin_allowed, serve_connection

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/prices")
async def ws_prices(ws: WebSocket):
    if not origin_allowed(ws.headers.get("origin"), settings.cors_origin_list):
        await ws.close(code=1008)
        return
    await ws.accept()

    async def receive():
        try:
            message = await ws.receive()
        except Exception:
            raise ConnectionClosed()
        if message.get("type") == "websocket.disconnect":
            raise ConnectionClosed()
        if message.get("text") is not None:
            return message["text"]
        return message.get("bytes") or b""

    code, reason = await serve_connection(hub, receive, ws.send_text)
    try:
        await ws.close(code=code, reason=reason)
    except Exception:
        pass


@router.get("/ws/status", summary="WebSocket hub status: clients, subscriptions, latest ticks, counters")
def ws_status():
    return hub.status()
