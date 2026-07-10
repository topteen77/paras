"""Sarvam STT + LLM + TTS voice agent for phone calls."""
import asyncio
import audioop
import base64
import re
import time
import uuid

from sarvamai import AsyncSarvamAI, SarvamAI

from common.conversation_flow import MonicaConversationFlow
from common.pronunciation import apply_pronunciation
from common.prompt_manager import get_effective_prompt
from common.voice_settings import get_effective_voice_settings


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
    _CLOSING_USER_MARKERS = (
        "goodbye",
        "good bye",
        "bye",
        "alvida",
        "अलविदा",
        "not interested",
        "i am busy",
        "busy now",
    )
    _MIN_USER_CHARS = 2
    _PLAYBACK_PAD_S = 0.35

    def __init__(
        self,
        audio_interface,
        executive_summary: str,
        on_agent_text=None,
        on_user_text=None,
        on_hangup=None,
        simulate_mode: bool = False,
    ):
        self.audio_interface = audio_interface
        self.on_agent_text = on_agent_text or (lambda t: None)
        self.on_user_text = on_user_text or (lambda t: None)
        self.on_hangup = on_hangup
        self.simulate_mode = simulate_mode
        self.conversation_id = str(uuid.uuid4())
        self._running = False
        self._hangup_scheduled = False
        self._hangup_completed = False
        self._speaking = False
        self._waiting_for_user = False
        self._agent_audio_until = 0.0
        self._stt_ws = None
        self._stt_context = None
        self._stt_receive_task = None
        self._processing = False
        self._latest_transcript = ""
        self._user_speaking = False
        self._last_user_text = ""
        self._last_finalized_at = 0.0
        self._flow = MonicaConversationFlow()
        self._voice = get_effective_voice_settings()
        self._base_system_prompt = self._load_system_prompt(executive_summary)
        self._async_client = AsyncSarvamAI(api_subscription_key=self._api_key())
        self._client = SarvamAI(api_subscription_key=self._api_key())
        self.messages = [{"role": "system", "content": self._system_content()}]

    @staticmethod
    def _api_key():
        from common.config import SARVAM_API_KEY

        return SARVAM_API_KEY

    def _system_content(self) -> str:
        return f"{self._base_system_prompt}\n\n{self._flow.llm_context()}"

    def _refresh_system_message(self) -> None:
        self.messages[0]["content"] = self._system_content()

    async def _notify(self, callback, text: str) -> None:
        try:
            result = callback(text)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            print(f"[SARVAM] callback error: {exc}")

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

    def flow_state(self) -> dict:
        return self._flow.state_snapshot()

    def is_agent_playing(self) -> bool:
        return self._speaking or time.monotonic() < self._agent_audio_until

    @classmethod
    def _sanitize_reply(cls, raw: str) -> str:
        if not raw:
            return ""
        text = raw.strip()
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"#+\s*", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        q_end = text.find("?")
        if q_end >= 0:
            text = text[: q_end + 1].strip()
        return text

    def _load_system_prompt(self, executive_summary: str) -> str:
        return get_effective_prompt(executive_summary)

    async def prepare(self):
        self._running = True
        self._voice = get_effective_voice_settings()
        self._flow.reset()
        self._waiting_for_user = False
        self._agent_audio_until = 0.0
        self._refresh_system_message()

    async def _wait_until_listen_ready(self):
        while self._running and time.monotonic() < self._agent_audio_until:
            await asyncio.sleep(0.05)

    async def speak_greeting(self):
        greeting = self._sanitize_reply(self._flow.build_greeting())
        await self._speak(greeting)
        await self._notify(self.on_agent_text, greeting)
        self.messages.append({"role": "assistant", "content": greeting})
        await self._wait_until_listen_ready()
        await self._connect_stt()
        self._waiting_for_user = True
        print("[SARVAM] greeting done — listening for caller")

    async def start_text_session(self) -> str:
        await self.prepare()
        greeting = self._sanitize_reply(self._flow.build_greeting())
        self.messages.append({"role": "assistant", "content": greeting})
        self._waiting_for_user = True
        return greeting

    async def start(self):
        await self.prepare()
        await self.speak_greeting()

    async def stop(self):
        self._running = False
        self._waiting_for_user = False
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
            "flow": self._flow.state_snapshot(),
        }

    async def feed_audio(self, pcm16_8k: bytes):
        if not self._running or not pcm16_8k or not self._stt_ws:
            return
        if not self._waiting_for_user or self.is_agent_playing() or self._processing:
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

    async def _interrupt_agent_speech(self):
        if not self._speaking and not self.is_agent_playing():
            return
        print("[SARVAM] user barge-in — clearing agent audio")
        self._speaking = False
        self._agent_audio_until = 0.0
        if hasattr(self.audio_interface, "clear_audio_threadsafe"):
            self.audio_interface.clear_audio_threadsafe()
        elif hasattr(self.audio_interface, "clear_audio"):
            try:
                result = self.audio_interface.clear_audio()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    def _is_likely_echo(self, text: str) -> bool:
        lowered = text.lower().strip()
        if len(lowered) < self._MIN_USER_CHARS:
            return True
        user_words = lowered.split()
        # Short valid answers (country, level, city) often overlap agent question words.
        if len(user_words) <= 4:
            for msg in reversed(self.messages[-3:]):
                if msg.get("role") != "assistant":
                    continue
                agent = (msg.get("content") or "").lower()
                if len(lowered) > 24 and lowered in agent:
                    return True
            return False
        for msg in reversed(self.messages[-4:]):
            if msg.get("role") != "assistant":
                continue
            agent = (msg.get("content") or "").lower()
            if not agent:
                continue
            if lowered in agent and len(lowered) > 20:
                return True
            uw = set(user_words)
            aw = set(agent.split())
            if uw and len(uw & aw) / len(uw) > 0.8 and len(uw) >= 5:
                return True
        return False

    @staticmethod
    def _is_speech_start(signal: str) -> bool:
        s = (signal or "").lower()
        return "start" in s or s in ("speech_started", "speech_start")

    @staticmethod
    def _is_speech_end(signal: str) -> bool:
        s = (signal or "").lower()
        return "end" in s or s in ("speech_ended", "speech_end", "flush", "utterance_end")

    async def _connect_stt(self):
        from common.config import SARVAM_LANGUAGE_CODE, SARVAM_STT_MODEL

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
        if self.is_agent_playing() or not self._waiting_for_user:
            return
        msg_type = getattr(message, "type", None)
        if msg_type == "error":
            err = getattr(getattr(message, "data", None), "message", str(message))
            print(f"[SARVAM_STT] server error: {err}")
            return
        if msg_type == "events":
            signal = getattr(getattr(message, "data", None), "signal_type", "") or ""
            if signal:
                print(f"[SARVAM_STT] vad: {signal}")
            if self._is_speech_start(signal):
                self._user_speaking = True
                if self.is_agent_playing():
                    await self._interrupt_agent_speech()
            elif self._is_speech_end(signal):
                self._user_speaking = False
                await self._finalize_user_utterance()
            return
        if msg_type != "data":
            return
        transcript = (getattr(getattr(message, "data", None), "transcript", "") or "").strip()
        if transcript:
            self._latest_transcript = transcript
            print(f"[SARVAM_STT] partial: {transcript}")

    async def _finalize_user_utterance(self):
        if not self._waiting_for_user or self.is_agent_playing() or self._processing:
            return
        text = (self._latest_transcript or "").strip()
        self._latest_transcript = ""
        if not text or self._hangup_scheduled:
            return
        if self._is_likely_echo(text):
            print(f"[SARVAM_STT] ignored echo: {text[:60]}")
            return
        now = time.monotonic()
        if now - self._last_finalized_at < 0.8:
            return
        await asyncio.sleep(0.15)
        if self._user_speaking or self.is_agent_playing() or not self._waiting_for_user:
            return
        self._last_finalized_at = now
        await self._handle_user_utterance(text)

    async def _handle_user_utterance(self, text: str, speak: bool = True):
        if not text or self._processing or self._hangup_scheduled or not self._waiting_for_user:
            return
        if self._is_likely_echo(text):
            return

        self._processing = True
        self._waiting_for_user = False
        self._last_user_text = text
        await self._notify(self.on_user_text, text)
        self.messages.append({"role": "user", "content": text})
        self._flow.record_user_answer(text)
        self._refresh_system_message()

        if self._user_wants_to_end(text):
            reply = "Thank you for your time. Goodbye."
            self.messages.append({"role": "assistant", "content": reply})
            await self._notify(self.on_agent_text, reply)
            if speak:
                await self._speak(reply)
                await self._wait_until_listen_ready()
            await self._end_call(immediate=True)
            self._processing = False
            return

        reply = self._flow.build_reply_after_answer()
        if self._flow.all_collected():
            reply = reply.strip()
        else:
            reply = self._sanitize_reply(reply)
        self.messages.append({"role": "assistant", "content": reply})
        self._refresh_system_message()
        await self._notify(self.on_agent_text, reply)

        try:
            if speak:
                await self._speak(reply)
                await self._wait_until_listen_ready()
        finally:
            if self._flow.all_collected():
                await self._end_call(immediate=True)
            else:
                self._waiting_for_user = True
                print("[SARVAM] waiting for caller answer")

        self._processing = False

    async def _end_call(self, immediate: bool = False):
        if self._hangup_scheduled:
            return
        self._hangup_scheduled = True
        self._waiting_for_user = False
        self._hangup_completed = True
        self._running = False
        if not immediate and not self.simulate_mode:
            await asyncio.sleep(0.5)
        if self.on_hangup:
            try:
                result = self.on_hangup()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                print(f"[SARVAM_HANGUP] error: {exc}")

    def _estimate_pcm_duration(self, pcm: bytes) -> float:
        if not pcm:
            return 0.0
        return len(pcm) / (8000 * 2)

    async def _speak(self, text: str):
        spoken = self._sanitize_reply(text)
        if not spoken:
            return
        tts_text = apply_pronunciation(spoken)
        self._speaking = True
        self._waiting_for_user = False
        self._voice = get_effective_voice_settings()
        pcm = b""
        try:
            kwargs = {
                "text": tts_text,
                "target_language_code": self._voice["language_code"],
                "model": self._voice["tts_model"],
                "speaker": self._voice["speaker"],
                "speech_sample_rate": 8000,
                "enable_preprocessing": self._voice.get("enable_preprocessing", True),
            }
            if str(self._voice.get("tts_model", "")).startswith("bulbul:v2"):
                kwargs["pace"] = self._voice.get("pace", 0.95)
                kwargs["pitch"] = self._voice.get("pitch", 0.0)
                kwargs["loudness"] = self._voice.get("loudness", 1.1)

            tts_response = self._client.text_to_speech.convert(**kwargs)
            if not self._speaking:
                return
            audios = getattr(tts_response, "audios", None)
            if isinstance(audios, list) and audios:
                wav_bytes = base64.b64decode(audios[0])
            elif isinstance(audios, str):
                wav_bytes = base64.b64decode(audios)
            else:
                wav_bytes = b""
            if not wav_bytes or not self._speaking:
                return
            pcm = wav_bytes[44:] if wav_bytes[:4] == b"RIFF" else wav_bytes
            duration = self._estimate_pcm_duration(pcm)
            self._agent_audio_until = time.monotonic() + duration + self._PLAYBACK_PAD_S
            if getattr(self.audio_interface, "use_mulaw", True):
                self.audio_interface.send_audio_threadsafe(audioop.lin2ulaw(pcm, 2))
            else:
                self.audio_interface.send_audio_threadsafe(pcm)
            if hasattr(self.audio_interface, "notify_playback_duration"):
                self.audio_interface.notify_playback_duration(duration)
        except Exception as exc:
            print(f"[SARVAM_TTS] error: {exc}")
        finally:
            self._speaking = False
