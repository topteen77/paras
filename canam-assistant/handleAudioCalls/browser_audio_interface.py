"""Browser WebSocket audio for dashboard practice calls."""
from __future__ import annotations

import asyncio
import base64
import json

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState


class BrowserAudioInterface:
    """Bidirectional PCM audio over dashboard WebSocket (8 kHz, 16-bit mono)."""

    use_mulaw = False

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.input_callback = None
        self.loop = asyncio.get_event_loop()
        self._playback_queue: asyncio.Queue[bytes] = asyncio.Queue()

    def set_input_callback(self, callback):
        self.input_callback = callback

    async def send_audio(self, audio: bytes):
        if not audio:
            return
        duration = len(audio) / (8000 * 2)
        message = {
            "event": "playAudio",
            "media": {
                "contentType": "audio/pcm",
                "sampleRate": 8000,
                "payload": base64.b64encode(audio).decode("utf-8"),
            },
            "duration": duration,
        }
        try:
            if self.websocket.application_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(json.dumps(message))
        except (WebSocketDisconnect, RuntimeError):
            pass

    def send_audio_threadsafe(self, audio: bytes):
        asyncio.run_coroutine_threadsafe(self.send_audio(audio), self.loop)

    async def clear_audio(self):
        try:
            if self.websocket.application_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(json.dumps({"event": "clearAudio"}))
        except (WebSocketDisconnect, RuntimeError):
            pass

    def clear_audio_threadsafe(self):
        asyncio.run_coroutine_threadsafe(self.clear_audio(), self.loop)

    async def handle_message(self, data: dict):
        event_type = data.get("event")
        if event_type == "media" and self.input_callback:
            payload = data.get("media", {}).get("payload", "")
            if not payload:
                return
            self.input_callback(base64.b64decode(payload))
        elif event_type == "stop":
            pass
