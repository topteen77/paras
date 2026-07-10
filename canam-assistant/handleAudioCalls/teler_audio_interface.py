"""Bidirectional FreJun Teler media stream WebSocket interface (L16 PCM 8 kHz)."""
import asyncio
import base64
import json

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState


class TelerAudioInterface:
    """Teler streams raw PCM16 mono @ 8 kHz as base64 JSON messages."""

    use_mulaw = False

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.stream_id = None
        self.call_uuid = None
        self.input_callback = None
        self.loop = asyncio.get_event_loop()
        self._chunk_id = 1

    def set_input_callback(self, callback):
        self.input_callback = callback

    async def send_audio(self, audio: bytes):
        """Send PCM16 8 kHz audio back to Teler."""
        if not audio:
            return
        message = {
            "type": "audio",
            "audio_b64": base64.b64encode(audio).decode("utf-8"),
            "chunk_id": self._chunk_id,
        }
        self._chunk_id += 1
        try:
            if self.websocket.application_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(json.dumps(message))
        except (WebSocketDisconnect, RuntimeError):
            pass

    def send_audio_threadsafe(self, audio: bytes):
        asyncio.run_coroutine_threadsafe(self.send_audio(audio), self.loop)

    async def clear_audio(self):
        message = {"type": "clear"}
        try:
            if self.websocket.application_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(json.dumps(message))
        except (WebSocketDisconnect, RuntimeError):
            pass

    def clear_audio_threadsafe(self):
        asyncio.run_coroutine_threadsafe(self.clear_audio(), self.loop)

    async def handle_teler_message(self, data: dict):
        event_type = data.get("type") or data.get("event")

        if event_type in ("start", "connected", "stream_started"):
            start = data.get("start") or data.get("data") or data
            self.stream_id = (
                start.get("streamId")
                or start.get("stream_id")
                or data.get("stream_id")
                or data.get("call_id")
            )
            self.call_uuid = (
                start.get("callId")
                or start.get("call_id")
                or data.get("call_id")
                or self.stream_id
            )
            print(f"[TELER_STREAM] start stream_id={self.stream_id} call_id={self.call_uuid}")

        elif event_type == "audio" and self.input_callback:
            payload_b64 = ""
            if isinstance(data.get("data"), dict):
                payload_b64 = data["data"].get("audio_b64") or data["data"].get("payload") or ""
            payload_b64 = payload_b64 or data.get("audio_b64") or data.get("payload") or ""
            if not payload_b64:
                media = data.get("media") or {}
                payload_b64 = media.get("payload") or media.get("audio_b64") or ""
            if payload_b64:
                self.input_callback(base64.b64decode(payload_b64))

        elif event_type in ("stop", "stream_stopped", "disconnected"):
            print(f"[TELER_STREAM] stop event={event_type}")

        elif event_type == "clear":
            pass
