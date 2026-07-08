"""Sarvam STT + LLM + TTS voice agent for phone calls."""
import asyncio
import audioop
import base64
import json
import uuid
from pathlib import Path

import websockets
from sarvamai import SarvamAI

from common.config import (
    SARVAM_API_KEY,
    SARVAM_CHAT_MODEL,
    SARVAM_LANGUAGE_CODE,
    SARVAM_STT_MODEL,
    SARVAM_SYSTEM_PROMPT_PATH,
    SARVAM_TTS_MODEL,
    SARVAM_TTS_SPEAKER,
)


class SarvamVoiceAgent:
    def __init__(self, audio_interface, executive_summary: str, on_agent_text=None, on_user_text=None):
        self.audio_interface = audio_interface
        self.on_agent_text = on_agent_text or (lambda t: None)
        self.on_user_text = on_user_text or (lambda t: None)
        self.conversation_id = str(uuid.uuid4())
        self._running = False
        self._stt_ws = None
        self._audio_buffer = bytearray()
        self._processing = False
        self._client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
        self.messages = [{"role": "system", "content": self._load_system_prompt(executive_summary)}]

    def _load_system_prompt(self, executive_summary: str) -> str:
        prompt_path = Path(SARVAM_SYSTEM_PROMPT_PATH)
        if prompt_path.is_file():
            base = prompt_path.read_text(encoding="utf-8")
        else:
            base = (
                "You are Monica, study abroad assistant for Canam Consultants. "
                "Collect country, study level, timeline, location, callback time. "
                "Keep replies under 2 sentences. End with Goodbye when done."
            )
        if executive_summary and executive_summary != "No executive summary available":
            base += f"\n\nPrior context:\n{executive_summary}"
        return base

    async def start(self):
        self._running = True
        await self._connect_stt()
        greeting = (
            "Hello! Ready to explore your study abroad adventure? "
            "Which country are you most interested in studying in?"
        )
        await self._speak(greeting)
        self.on_agent_text(greeting)
        self.messages.append({"role": "assistant", "content": greeting})

    async def stop(self):
        self._running = False
        if self._stt_ws:
            try:
                await self._stt_ws.close()
            except Exception:
                pass
            self._stt_ws = None

    async def feed_audio(self, pcm16_8k: bytes):
        if not self._running or not pcm16_8k or not self._stt_ws:
            return
        self._audio_buffer.extend(pcm16_8k)
        while len(self._audio_buffer) >= 3200:
            chunk = bytes(self._audio_buffer[:3200])
            del self._audio_buffer[:3200]
            try:
                await self._stt_ws.send(chunk)
            except Exception as exc:
                print(f"[SARVAM_STT] send error: {exc}")

    async def _connect_stt(self):
        self._stt_ws = await websockets.connect(
            "wss://api.sarvam.ai/speech-to-text/ws",
            additional_headers={"api-subscription-key": SARVAM_API_KEY},
            ping_interval=20,
        )
        await self._stt_ws.send(json.dumps({
            "language_code": SARVAM_LANGUAGE_CODE,
            "model": SARVAM_STT_MODEL,
            "sample_rate": 8000,
            "input_audio_codec": "pcm_s16le",
            "high_vad_sensitivity": True,
            "vad_signals": True,
        }))
        asyncio.create_task(self._stt_receive_loop())

    async def _stt_receive_loop(self):
        try:
            async for message in self._stt_ws:
                if not self._running or isinstance(message, bytes):
                    continue
                data = json.loads(message)
                transcript = (
                    data.get("data", {}).get("transcript")
                    or data.get("transcript")
                    or data.get("text")
                    or ""
                )
                is_final = data.get("data", {}).get("is_final", data.get("is_final", False))
                if transcript and is_final and not self._processing:
                    await self._handle_user_utterance(transcript.strip())
        except Exception as exc:
            print(f"[SARVAM_STT] receive error: {exc}")

    async def _handle_user_utterance(self, text: str):
        if not text or self._processing:
            return
        self._processing = True
        self.on_user_text(text)
        self.messages.append({"role": "user", "content": text})
        try:
            response = self._client.chat.completions(
                model=SARVAM_CHAT_MODEL,
                messages=self.messages,
                temperature=0.4,
                max_tokens=300,
            )
            reply = (response.choices[0].message.content or "").strip()
        except Exception as exc:
            print(f"[SARVAM_LLM] error: {exc}")
            reply = "Sorry, could you please repeat that?"
        if not reply:
            reply = "Could you please repeat that?"
        self.messages.append({"role": "assistant", "content": reply})
        self.on_agent_text(reply)
        await self._speak(reply)
        if "goodbye" in reply.lower():
            self._running = False
        self._processing = False

    async def _speak(self, text: str):
        try:
            tts_response = self._client.text_to_speech.convert(
                text=text,
                target_language_code=SARVAM_LANGUAGE_CODE,
                model=SARVAM_TTS_MODEL,
                speaker=SARVAM_TTS_SPEAKER,
                speech_sample_rate=8000,
                enable_preprocessing=True,
            )
            audios = getattr(tts_response, "audios", None)
            if isinstance(audios, list) and audios:
                wav_bytes = base64.b64decode(audios[0])
            elif isinstance(audios, str):
                wav_bytes = base64.b64decode(audios)
            else:
                wav_bytes = b""
            if not wav_bytes:
                return
            pcm = wav_bytes[44:] if wav_bytes[:4] == b"RIFF" else wav_bytes
            self.audio_interface.send_audio_threadsafe(audioop.lin2ulaw(pcm, 2))
        except Exception as exc:
            print(f"[SARVAM_TTS] error: {exc}")
