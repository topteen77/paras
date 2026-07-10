import asyncio
import audioop
import base64
import json
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState


class PlivoAudioInterface:
    """Bidirectional Plivo Audio Stream WebSocket interface."""

    use_mulaw = True

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.stream_id = None
        self.call_uuid = None
        self.input_callback = None
        self.loop = asyncio.get_event_loop()
        self._use_mulaw = True

    def set_input_callback(self, callback):
        self.input_callback = callback

    async def send_audio(self, audio: bytes):
        """Send mulaw audio back to Plivo via playAudio event."""
        if not audio:
            return
        message = {
            "event": "playAudio",
            "media": {
                "contentType": "audio/x-mulaw",
                "sampleRate": 8000,
                "payload": base64.b64encode(audio).decode("utf-8"),
            },
        }
        try:
            if self.websocket.application_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(json.dumps(message))
        except (WebSocketDisconnect, RuntimeError):
            pass

    def send_audio_threadsafe(self, audio: bytes):
        asyncio.run_coroutine_threadsafe(self.send_audio(audio), self.loop)

    async def clear_audio(self):
        """Stop queued TTS on the call (barge-in)."""
        if not self.stream_id:
            return
        message = {"event": "clearAudio", "streamId": self.stream_id}
        try:
            if self.websocket.application_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(json.dumps(message))
        except (WebSocketDisconnect, RuntimeError):
            pass

    def clear_audio_threadsafe(self):
        asyncio.run_coroutine_threadsafe(self.clear_audio(), self.loop)

    async def handle_plivo_message(self, data: dict):
        event_type = data.get("event")

        if event_type == "start":
            start = data.get("start", {})
            self.stream_id = start.get("streamId") or start.get("stream_id")
            self.call_uuid = start.get("callId") or start.get("call_uuid")
            media_format = start.get("mediaFormat", {})
            encoding = media_format.get("encoding", "")
            self._use_mulaw = "mulaw" in encoding.lower() or "mulaw" in str(
                data.get("contentType", "")
            ).lower()

        elif event_type == "media" and self.input_callback:
            payload = data.get("media", {}).get("payload", "")
            if not payload:
                return
            audio_bytes = base64.b64decode(payload)
            content_type = data.get("media", {}).get("contentType", "")
            if "mulaw" in content_type.lower() or self._use_mulaw:
                audio_bytes = audioop.ulaw2lin(audio_bytes, 2)
            self.input_callback(audio_bytes)

        elif event_type in ("stop", "clearedAudio"):
            pass
