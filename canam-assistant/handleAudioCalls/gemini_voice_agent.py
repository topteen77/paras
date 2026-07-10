"""Gemini Live native-audio voice agent for Plivo phone calls."""
from __future__ import annotations

import asyncio
import audioop
import uuid
from typing import Optional

from google import genai
from google.genai import types

from common.prompt_manager import get_effective_prompt

PLIVO_SAMPLE_RATE = 8000
GEMINI_INPUT_SAMPLE_RATE = 16000
GEMINI_OUTPUT_SAMPLE_RATE = 24000
MULAW_FRAME_SIZE = 160  # 20 ms at 8 kHz


class GeminiVoiceAgent:
    _GOODBYE_MARKERS = (
        "goodbye",
        "good bye",
        "bye bye",
        " bye",
        "alvida",
        "अलविदा",
    )

    def __init__(
        self,
        audio_interface,
        executive_summary: str,
        on_agent_text=None,
        on_user_text=None,
        on_hangup=None,
    ):
        self.audio_interface = audio_interface
        self.on_agent_text = on_agent_text or (lambda t: None)
        self.on_user_text = on_user_text or (lambda t: None)
        self.on_hangup = on_hangup
        self.conversation_id = str(uuid.uuid4())
        self._running = False
        self._hangup_scheduled = False
        self._hangup_completed = False
        self._session = None
        self._session_context = None
        self._receive_task: Optional[asyncio.Task] = None
        self._ratecv_in_state = None
        self._ratecv_out_state_24_16 = None
        self._ratecv_out_state_16_8 = None
        self._mulaw_out_buffer = bytearray()
        self._pending_user_text = ""
        self._pending_agent_text = ""
        self.messages: list[dict[str, str]] = [
            {"role": "system", "content": get_effective_prompt(executive_summary)}
        ]
        self._client = genai.Client(api_key=self._api_key())

    @staticmethod
    def _api_key() -> str:
        from common.config import GEMINI_API_KEY

        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY (or GOOGLE_API_KEY) is not configured")
        return GEMINI_API_KEY

    @classmethod
    def _is_goodbye(cls, text: str) -> bool:
        lowered = (text or "").lower()
        return any(marker in lowered for marker in cls._GOODBYE_MARKERS)

    def should_end_session(self) -> bool:
        return self._hangup_completed

    def _live_config(self) -> types.LiveConnectConfig:
        from common.config import GEMINI_LANGUAGE_CODE, GEMINI_VOICE_NAME

        speech_config = types.SpeechConfig(language_code=GEMINI_LANGUAGE_CODE)
        if GEMINI_VOICE_NAME:
            speech_config.voice_config = types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=GEMINI_VOICE_NAME)
            )
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part(text=self.messages[0]["content"])]
            ),
            speech_config=speech_config,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

    async def prepare(self):
        from common.config import GEMINI_LIVE_MODEL

        self._running = True
        self._session_context = self._client.aio.live.connect(
            model=GEMINI_LIVE_MODEL,
            config=self._live_config(),
        )
        self._session = await self._session_context.__aenter__()
        self._receive_task = asyncio.create_task(self._receive_loop())
        print(f"[GEMINI_LIVE] connected model={GEMINI_LIVE_MODEL}")

    async def speak_greeting(self):
        await self._session.send_client_content(
            turns={
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "The outbound call just connected. Greet the caller briefly "
                            "per your instructions, then ask which country they want to study in."
                        )
                    }
                ],
            },
            turn_complete=True,
        )

    async def start(self):
        await self.prepare()
        await self.speak_greeting()

    async def stop(self):
        self._running = False
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        if self._session_context is not None:
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception:
                pass
            self._session_context = None
            self._session = None

    def export_conversation(self) -> dict:
        transcript = [
            {"role": m["role"], "text": m["content"]}
            for m in self.messages
            if m.get("role") != "system" and m.get("content")
        ]
        from common.post_call import build_qa_pairs

        return {
            "conversation_id": self.conversation_id,
            "transcript": transcript,
            "qa_pairs": build_qa_pairs(self.messages),
        }

    def _plivo_to_gemini_pcm(self, pcm16_8k: bytes) -> bytes:
        if not pcm16_8k:
            return b""
        resampled, self._ratecv_in_state = audioop.ratecv(
            pcm16_8k, 2, 1, PLIVO_SAMPLE_RATE, GEMINI_INPUT_SAMPLE_RATE, self._ratecv_in_state
        )
        return resampled

    def _gemini_to_output_audio(self, pcm16_24k: bytes) -> bytes:
        if not pcm16_24k:
            return b""
        pcm16_16k, self._ratecv_out_state_24_16 = audioop.ratecv(
            pcm16_24k,
            2,
            1,
            GEMINI_OUTPUT_SAMPLE_RATE,
            16000,
            self._ratecv_out_state_24_16,
        )
        pcm16_8k, self._ratecv_out_state_16_8 = audioop.ratecv(
            pcm16_16k, 2, 1, 16000, PLIVO_SAMPLE_RATE, self._ratecv_out_state_16_8
        )
        if getattr(self.audio_interface, "use_mulaw", True):
            return audioop.lin2ulaw(pcm16_8k, 2)
        return pcm16_8k

    def _enqueue_output_audio(self, audio_chunk: bytes):
        if not audio_chunk:
            return
        if getattr(self.audio_interface, "use_mulaw", True):
            self._mulaw_out_buffer.extend(audio_chunk)
            frame_size = MULAW_FRAME_SIZE
        else:
            self._mulaw_out_buffer.extend(audio_chunk)
            frame_size = 320  # 20 ms PCM16 @ 8 kHz
        while len(self._mulaw_out_buffer) >= frame_size:
            frame = bytes(self._mulaw_out_buffer[:frame_size])
            del self._mulaw_out_buffer[:frame_size]
            self.audio_interface.send_audio_threadsafe(frame)

    async def feed_audio(self, pcm16_8k: bytes):
        if not self._running or not pcm16_8k or not self._session:
            return
        pcm16_16k = self._plivo_to_gemini_pcm(pcm16_8k)
        if not pcm16_16k:
            return
        try:
            await self._session.send_realtime_input(
                audio=types.Blob(
                    data=pcm16_16k,
                    mime_type=f"audio/pcm;rate={GEMINI_INPUT_SAMPLE_RATE}",
                )
            )
        except Exception as exc:
            print(f"[GEMINI_LIVE] send audio error: {exc}")

    def _commit_user_text(self, text: str):
        cleaned = (text or "").strip()
        if not cleaned:
            return
        self.on_user_text(cleaned)
        self.messages.append({"role": "user", "content": cleaned})

    def _commit_agent_text(self, text: str):
        cleaned = (text or "").strip()
        if not cleaned:
            return
        self.on_agent_text(cleaned)
        self.messages.append({"role": "assistant", "content": cleaned})

    async def _handle_goodbye(self, text: str):
        if not self._is_goodbye(text) or self._hangup_scheduled:
            return
        self._hangup_scheduled = True
        playback_seconds = min(max(len(text) * 0.07, 2.0), 6.0)
        await asyncio.sleep(playback_seconds)
        if self.on_hangup:
            try:
                result = self.on_hangup()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                print(f"[GEMINI_HANGUP] error: {exc}")
        self._hangup_completed = True
        self._running = False

    async def _receive_loop(self):
        try:
            while self._running and self._session:
                async for response in self._session.receive():
                    if not self._running:
                        break

                    server_content = response.server_content
                    if not server_content:
                        continue

                    if server_content.interrupted:
                        print("[GEMINI_LIVE] interrupted — clearing Plivo audio")
                        self._mulaw_out_buffer.clear()
                        if hasattr(self.audio_interface, "clear_audio_threadsafe"):
                            self.audio_interface.clear_audio_threadsafe()

                    if server_content.input_transcription:
                        text = (server_content.input_transcription.text or "").strip()
                        if text:
                            self._pending_user_text = text

                    if server_content.output_transcription:
                        text = (server_content.output_transcription.text or "").strip()
                        if text:
                            self._pending_agent_text = text

                    model_turn = server_content.model_turn
                    if model_turn and model_turn.parts:
                        for part in model_turn.parts:
                            inline = getattr(part, "inline_data", None)
                            if inline and inline.data:
                                self._enqueue_output_audio(
                                    self._gemini_to_output_audio(inline.data)
                                )

                    if server_content.turn_complete:
                        if self._pending_user_text:
                            self._commit_user_text(self._pending_user_text)
                            self._pending_user_text = ""
                        if self._pending_agent_text:
                            agent_text = self._pending_agent_text
                            self._commit_agent_text(agent_text)
                            self._pending_agent_text = ""
                            await self._handle_goodbye(agent_text)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[GEMINI_LIVE] receive error: {exc}")
