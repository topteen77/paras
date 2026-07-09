"""Sarvam STT + LLM + TTS voice agent for phone calls."""
import asyncio
import audioop
import base64
import re
import uuid

from sarvamai import AsyncSarvamAI, SarvamAI

from common.config import (
    SARVAM_API_KEY,
    SARVAM_CHAT_MODEL,
    SARVAM_LANGUAGE_CODE,
    SARVAM_STT_MODEL,
    SARVAM_TTS_MODEL,
    SARVAM_TTS_SPEAKER,
)
from common.prompt_manager import get_effective_prompt


class SarvamVoiceAgent:
    _GOODBYE_MARKERS = (
        "goodbye",
        "good bye",
        "bye bye",
        " bye",
        "alvida",
        "अलविदा",
        "alvidaa",
    )
    _CLOSING_USER_MARKERS = ("goodbye", "good bye", "bye", "alvida", "अलविदा", "not interested", "i am busy", "busy now")

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
        self._speaking = False
        self._stt_ws = None
        self._stt_context = None
        self._stt_receive_task = None
        self._processing = False
        self._async_client = AsyncSarvamAI(api_subscription_key=SARVAM_API_KEY)
        self._client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
        self.messages = [{"role": "system", "content": self._load_system_prompt(executive_summary)}]

    @classmethod
    def _is_goodbye(cls, text: str) -> bool:
        lowered = (text or "").lower()
        return any(marker in lowered for marker in cls._GOODBYE_MARKERS)

    @classmethod
    def _user_wants_to_end(cls, text: str) -> bool:
        lowered = (text or "").lower()
        return any(marker in lowered for marker in cls._CLOSING_USER_MARKERS)

    def should_end_session(self) -> bool:
        return self._hangup_completed

    @classmethod
    def _sanitize_reply(cls, raw: str) -> str:
        """Keep only natural spoken dialogue; drop markdown and internal slot tracking."""
        if not raw:
            return ""
        text = raw.strip()
        for marker in (
            "\n---",
            "\n***",
            "\n**Slot",
            "\nSlot 1:",
            "\nSlot 2:",
            "\n(Slot",
            "\n(If user",
            "\n**User Input",
            "\n**Status",
            "\n**Action",
        ):
            idx = text.find(marker)
            if idx > 0:
                text = text[:idx].strip()
        text = re.sub(
            r"\([^)]*(?:user|slot|assuming|proceed|status|action)[^)]*\)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"#+\s*", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\bwe(?:'re| are) looking for\b.*?(?=[.?!]|$)", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\bwhat(?:'s| is) the next detail\b.*?(?=[.?!]|$)", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\blet me confirm\b.*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\bso, to confirm\b.*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\d+\.\s*", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 220:
            q_end = text.find("?")
            if 0 < q_end < 220:
                text = text[: q_end + 1].strip()
            else:
                sentences = re.split(r"(?<=[.!?])\s+", text)
                text = " ".join(sentences[:3]).strip()
        return text

    def _load_system_prompt(self, executive_summary: str) -> str:
        return get_effective_prompt(executive_summary)

    async def prepare(self):
        """Mark session running. STT connects after greeting so idle timeout does not fire."""
        self._running = True

    async def speak_greeting(self):
        greeting = (
            "Hello! Ready to explore your study abroad adventure? "
            "Which country are you most interested in studying in?"
        )
        await self._speak(greeting)
        self.on_agent_text(greeting)
        self.messages.append({"role": "assistant", "content": greeting})
        await self._connect_stt()

    async def start(self):
        await self.prepare()
        await self.speak_greeting()

    async def stop(self):
        self._running = False
        if self._stt_receive_task:
            self._stt_receive_task.cancel()
            try:
                await self._stt_receive_task
            except asyncio.CancelledError:
                pass
            self._stt_receive_task = None
        if self._stt_context is not None:
            try:
                await self._stt_context.__aexit__(None, None, None)
            except Exception:
                pass
            self._stt_context = None
            self._stt_ws = None

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

    async def feed_audio(self, pcm16_8k: bytes):
        if (
            not self._running
            or not pcm16_8k
            or not self._stt_ws
            or self._speaking
            or self._processing
        ):
            return
        try:
            audio_b64 = base64.b64encode(pcm16_8k).decode("utf-8")
            await self._stt_ws.transcribe(
                audio=audio_b64,
                sample_rate=8000,
                encoding="audio/wav",
            )
        except Exception as exc:
            print(f"[SARVAM_STT] send error: {exc}")
            await self._reconnect_stt()

    async def _connect_stt(self):
        await self._disconnect_stt()
        self._stt_context = self._async_client.speech_to_text_streaming.connect(
            model=SARVAM_STT_MODEL,
            mode="transcribe",
            language_code=SARVAM_LANGUAGE_CODE,
            sample_rate="8000",
            input_audio_codec="pcm_s16le",
            high_vad_sensitivity="true",
            vad_signals="true",
            flush_signal="true",
        )
        self._stt_ws = await self._stt_context.__aenter__()
        self._stt_receive_task = asyncio.create_task(self._stt_receive_loop())
        print("[SARVAM_STT] connected (saaras v3 streaming)")

    async def _disconnect_stt(self):
        if self._stt_receive_task:
            self._stt_receive_task.cancel()
            try:
                await self._stt_receive_task
            except asyncio.CancelledError:
                pass
            self._stt_receive_task = None
        if self._stt_context is not None:
            try:
                await self._stt_context.__aexit__(None, None, None)
            except Exception:
                pass
        self._stt_context = None
        self._stt_ws = None

    async def _reconnect_stt(self):
        if not self._running:
            return
        print("[SARVAM_STT] reconnecting...")
        try:
            await self._connect_stt()
        except Exception as exc:
            print(f"[SARVAM_STT] reconnect failed: {exc}")

    async def _stt_receive_loop(self):
        try:
            while self._running and self._stt_ws:
                try:
                    message = await asyncio.wait_for(self._stt_ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                await self._handle_stt_message(message)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[SARVAM_STT] receive error: {exc}")

    async def _handle_stt_message(self, message):
        msg_type = getattr(message, "type", None)
        if msg_type == "error":
            err = getattr(getattr(message, "data", None), "message", str(message))
            print(f"[SARVAM_STT] server error: {err}")
            return
        if msg_type == "events":
            signal = getattr(getattr(message, "data", None), "signal_type", "")
            if signal:
                print(f"[SARVAM_STT] vad: {signal}")
            return
        if msg_type != "data":
            return
        transcript = (getattr(getattr(message, "data", None), "transcript", "") or "").strip()
        if transcript and not self._processing:
            print(f"[SARVAM_STT] transcript: {transcript}")
            await self._handle_user_utterance(transcript)

    async def _handle_user_utterance(self, text: str):
        if not text or self._processing or self._hangup_scheduled:
            return
        self._processing = True
        self.on_user_text(text)
        self.messages.append({"role": "user", "content": text})

        if self._user_wants_to_end(text):
            reply = "Thank you for your time. Your details are saved. Goodbye."
            self.messages.append({"role": "assistant", "content": reply})
            self.on_agent_text(reply)
            await self._speak(reply)
            await self._handle_goodbye(reply)
            self._processing = False
            return

        try:
            response = self._client.chat.completions(
                model=SARVAM_CHAT_MODEL,
                messages=self.messages,
                temperature=0.3,
                max_tokens=100,
                reasoning_effort=None,
            )
            msg = response.choices[0].message
            raw_reply = (msg.content or "").strip()
            if not raw_reply:
                raw_reply = (getattr(msg, "reasoning_content", None) or "").strip()
            reply = self._sanitize_reply(raw_reply)
            if raw_reply and reply != raw_reply:
                print(f"[SARVAM_LLM] sanitized reply ({len(raw_reply)} -> {len(reply)} chars)")
        except Exception as exc:
            print(f"[SARVAM_LLM] error: {exc}")
            reply = "Sorry, could you please repeat that?"
        if not reply:
            reply = "Could you please repeat that?"
        self.messages.append({"role": "assistant", "content": reply})
        self.on_agent_text(reply)
        await self._speak(reply)
        await self._handle_goodbye(reply)
        self._processing = False

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
                print(f"[SARVAM_HANGUP] error: {exc}")
        self._hangup_completed = True
        self._running = False

    async def _speak(self, text: str):
        spoken = self._sanitize_reply(text)
        if not spoken:
            return
        self._speaking = True
        try:
            tts_response = self._client.text_to_speech.convert(
                text=spoken,
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
        finally:
            self._speaking = False
