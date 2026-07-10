import asyncio
import json
import traceback
from urllib.parse import unquote

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation, ConversationInitiationData
from google.cloud import firestore

from common.runtime_stack import get_telephony_provider, get_voice_ai_provider
from common.config import (
    ELEVENLABS_API_KEY,
    ELEVEN_LABS_COLD_CALLING_AGENT_ID,
    GEMINI_API_KEY,
    SARVAM_API_KEY,
)
from common.post_call import link_call_uuid, save_transcript, try_deliver_report
from common.functions import (
    add_call_staus_to_pubsub,
    end_call,
    end_call_by_internal_id,
    get_executive_summary,
)
from handleAudioCalls.kommuno_audio_interface import KommunoAudioInterface
from handleAudioCalls.plivo_audio_interface import PlivoAudioInterface
from handleAudioCalls.gemini_voice_agent import GeminiVoiceAgent
from handleAudioCalls.sarvam_voice_agent import SarvamVoiceAgent
from handleAudioCalls.teler_audio_interface import TelerAudioInterface
from handleAudioCalls.twilio_audio_interface import TwilioAudioInterface

router = APIRouter()


def log_conversation_to_firestore(conversation_id: str, to_number: str, internal_id: str):
    try:
        db = firestore.Client()
        doc_ref = (
            db.collection("conversation-history")
            .document(to_number)
            .collection("calls")
            .document(internal_id)
        )
        if doc_ref.get().exists:
            doc_ref.set({"conversation_id": conversation_id}, merge=True)
    except Exception as exc:
        print(f"[FIRESTORE] skip conversation log: {exc}")


def _get_telephony_interface(websocket: WebSocket):
    telephony = get_telephony_provider()
    if telephony == "plivo":
        return PlivoAudioInterface(websocket)
    if telephony == "frejun":
        return TelerAudioInterface(websocket)
    if telephony == "kommuno":
        return KommunoAudioInterface(websocket)
    return TwilioAudioInterface(websocket)


async def _handle_telephony_message(audio_interface, data: dict):
    telephony = get_telephony_provider()
    if telephony == "plivo":
        await audio_interface.handle_plivo_message(data)
    elif telephony == "frejun":
        await audio_interface.handle_teler_message(data)
    elif telephony == "kommuno":
        await audio_interface.handle_kommuno_message(data)
    else:
        await audio_interface.handle_twilio_message(data)


def _stream_is_ready(audio_interface) -> bool:
    return bool(
        getattr(audio_interface, "stream_id", None)
        or getattr(audio_interface, "call_uuid", None)
    )


def _bind_audio_input(audio_interface, on_audio_in):
    if get_telephony_provider() in ("plivo", "frejun"):
        audio_interface.set_input_callback(on_audio_in)
    elif hasattr(audio_interface, "start"):
        audio_interface.start(on_audio_in)


async def _run_elevenlabs_session(
    websocket: WebSocket,
    to_phone_number: str,
    internal_id: str,
    audio_interface,
):
    eleven_labs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    dynamic_vars = {"executive_summary": get_executive_summary(to_phone_number)}
    config = ConversationInitiationData(dynamic_variables=dynamic_vars)

    conversation = Conversation(
        client=eleven_labs_client,
        agent_id=ELEVEN_LABS_COLD_CALLING_AGENT_ID,
        config=config,
        requires_auth=False,
        audio_interface=audio_interface,
        callback_agent_response=lambda text: print(f"[AGENT] {to_phone_number}: {text}"),
        callback_user_transcript=lambda text: print(f"[USER] {to_phone_number}: {text}"),
    )
    conversation.start_session()

    if get_telephony_provider() == "kommuno":
        await audio_interface.send_session_start()

    conversation_id = None
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message["type"] != "websocket.receive" or "text" not in message:
                continue
            text_data = message["text"]
            if not text_data:
                continue
            data = json.loads(text_data)
            await _handle_telephony_message(audio_interface, data)
    finally:
        conversation.end_session()
        conversation_id = conversation.wait_for_session_end()
        end_call_by_internal_id(internal_id, to_phone_number)
        log_conversation_to_firestore(conversation_id, to_phone_number, internal_id)
        add_call_staus_to_pubsub("", internal_id, to_phone_number, "completed")

    return conversation_id


async def _run_sarvam_session(
    websocket: WebSocket,
    to_phone_number: str,
    internal_id: str,
    audio_interface,
):
    async def hangup_active_call():
        call_uuid = getattr(audio_interface, "call_uuid", None)
        provider = get_telephony_provider()
        if call_uuid:
            print(f"[SARVAM_HANGUP] ending {provider} call {call_uuid}")
            end_call(call_uuid)
            return
        print(f"[SARVAM_HANGUP] no call_uuid; trying Firestore internal_id={internal_id}")
        end_call_by_internal_id(internal_id, to_phone_number)

    agent = SarvamVoiceAgent(
        audio_interface=audio_interface,
        executive_summary=get_executive_summary(to_phone_number),
        on_agent_text=lambda t: print(f"[AGENT] {to_phone_number}: {t}"),
        on_user_text=lambda t: print(f"[USER] {to_phone_number}: {t}"),
        on_hangup=hangup_active_call,
    )

    pcm_buffer = []

    def on_audio_in(pcm_bytes):
        pcm_buffer.append(pcm_bytes)

    _bind_audio_input(audio_interface, on_audio_in)

    greeted = False
    await agent.prepare()
    conversation_id = agent.conversation_id

    try:
        while True:
            if agent.should_end_session():
                break
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if message["type"] == "websocket.disconnect":
                break
            if message["type"] != "websocket.receive" or "text" not in message:
                continue
            text_data = message["text"]
            if not text_data:
                continue
            data = json.loads(text_data)
            await _handle_telephony_message(audio_interface, data)

            if not greeted and _stream_is_ready(audio_interface):
                call_uuid = getattr(audio_interface, "call_uuid", None)
                if call_uuid:
                    link_call_uuid(call_uuid, internal_id)
                await agent.speak_greeting()
                greeted = True

            while pcm_buffer:
                chunk = pcm_buffer.pop(0)
                await agent.feed_audio(chunk)

            if greeted and agent.should_end_session():
                break
    finally:
        await agent.stop()
        conversation = agent.export_conversation()
        save_transcript(internal_id, conversation)
        try_deliver_report(internal_id)
        call_uuid = getattr(audio_interface, "call_uuid", None)
        if call_uuid and not agent._hangup_completed:
            print(f"[SARVAM_HANGUP] fallback hangup for {call_uuid}")
            end_call(call_uuid)
        elif not call_uuid and not agent._hangup_completed:
            end_call_by_internal_id(internal_id, to_phone_number)
        log_conversation_to_firestore(conversation_id, to_phone_number, internal_id)
        add_call_staus_to_pubsub(
            getattr(audio_interface, "call_uuid", "") or "",
            internal_id,
            to_phone_number,
            "completed",
        )

    return conversation_id


async def _run_gemini_session(
    websocket: WebSocket,
    to_phone_number: str,
    internal_id: str,
    audio_interface,
):
    async def hangup_active_call():
        call_uuid = getattr(audio_interface, "call_uuid", None)
        provider = get_telephony_provider()
        if call_uuid:
            print(f"[GEMINI_HANGUP] ending {provider} call {call_uuid}")
            end_call(call_uuid)
            return
        print(f"[GEMINI_HANGUP] no call_uuid; trying Firestore internal_id={internal_id}")
        end_call_by_internal_id(internal_id, to_phone_number)

    agent = GeminiVoiceAgent(
        audio_interface=audio_interface,
        executive_summary=get_executive_summary(to_phone_number),
        on_agent_text=lambda t: print(f"[AGENT] {to_phone_number}: {t}"),
        on_user_text=lambda t: print(f"[USER] {to_phone_number}: {t}"),
        on_hangup=hangup_active_call,
    )

    pcm_buffer = []

    def on_audio_in(pcm_bytes):
        pcm_buffer.append(pcm_bytes)

    _bind_audio_input(audio_interface, on_audio_in)

    greeted = False
    await agent.prepare()
    conversation_id = agent.conversation_id

    try:
        while True:
            if agent.should_end_session():
                break
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if message["type"] == "websocket.disconnect":
                break
            if message["type"] != "websocket.receive" or "text" not in message:
                continue
            text_data = message["text"]
            if not text_data:
                continue
            data = json.loads(text_data)
            await _handle_telephony_message(audio_interface, data)

            if not greeted and _stream_is_ready(audio_interface):
                call_uuid = getattr(audio_interface, "call_uuid", None)
                if call_uuid:
                    link_call_uuid(call_uuid, internal_id)
                await agent.speak_greeting()
                greeted = True

            while pcm_buffer:
                chunk = pcm_buffer.pop(0)
                await agent.feed_audio(chunk)

            if greeted and agent.should_end_session():
                break
    finally:
        await agent.stop()
        conversation = agent.export_conversation()
        save_transcript(internal_id, conversation)
        try_deliver_report(internal_id)
        call_uuid = getattr(audio_interface, "call_uuid", None)
        if call_uuid and not agent._hangup_completed:
            print(f"[GEMINI_HANGUP] fallback hangup for {call_uuid}")
            end_call(call_uuid)
        elif not call_uuid and not agent._hangup_completed:
            end_call_by_internal_id(internal_id, to_phone_number)
        log_conversation_to_firestore(conversation_id, to_phone_number, internal_id)
        add_call_staus_to_pubsub(
            getattr(audio_interface, "call_uuid", "") or "",
            internal_id,
            to_phone_number,
            "completed",
        )

    return conversation_id


@router.websocket("/simulate")
async def simulate_practice_call(websocket: WebSocket):
    """Browser practice call — same Sarvam agent as live Plivo calls."""
    from handleAudioCalls.browser_audio_interface import BrowserAudioInterface

    if get_voice_ai_provider() != "sarvam":
        await websocket.accept()
        await websocket.send_text(
            json.dumps({"event": "error", "message": "Practice call requires the Sarvam voice stack"})
        )
        await websocket.close()
        return
    if not SARVAM_API_KEY:
        await websocket.accept()
        await websocket.send_text(
            json.dumps({"event": "error", "message": "SARVAM_API_KEY not configured"})
        )
        await websocket.close()
        return

    await websocket.accept()
    interface = BrowserAudioInterface(websocket)
    pcm_buffer: list[bytes] = []
    interface.set_input_callback(lambda chunk: pcm_buffer.append(chunk))

    async def emit(event: str, **fields):
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text(json.dumps({"event": event, **fields}))

    async def on_agent_text(text: str):
        await emit("transcript", role="assistant", text=text)
        await emit("flow", **agent.flow_state())

    async def on_user_text(text: str):
        await emit("transcript", role="user", text=text)
        await emit("flow", **agent.flow_state())

    async def on_hangup():
        await emit("ended", reason="goodbye")
        await emit("flow", **agent.flow_state())

    agent = SarvamVoiceAgent(
        audio_interface=interface,
        executive_summary="",
        on_agent_text=on_agent_text,
        on_user_text=on_user_text,
        on_hangup=on_hangup,
        simulate_mode=True,
    )

    try:
        await agent.start()
        await emit("started", conversation_id=agent.conversation_id)
        await emit("flow", **agent.flow_state())

        while not agent.should_end_session():
            while pcm_buffer and not agent.should_end_session():
                chunk = pcm_buffer.pop(0)
                await agent.feed_audio(chunk)

            if agent.should_end_session():
                break

            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=0.2)
            except asyncio.TimeoutError:
                if agent.should_end_session():
                    break
                continue
            if message["type"] == "websocket.disconnect":
                break
            if message["type"] != "websocket.receive" or "text" not in message:
                continue
            text_data = message["text"]
            if not text_data:
                continue
            data = json.loads(text_data)
            event = data.get("event")
            if event == "media":
                await interface.handle_message(data)
            elif event == "text":
                user_text = (data.get("text") or "").strip()
                if user_text:
                    await agent._handle_user_utterance(user_text)
            elif event == "stop":
                break

            if agent.should_end_session():
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[SIMULATE] error: {exc}")
        traceback.print_exc()
        try:
            await emit("error", message=str(exc))
        except Exception:
            pass
    finally:
        await agent.stop()
        try:
            summary = agent.export_conversation()
            await emit(
                "summary",
                transcript=summary.get("transcript", []),
                flow=summary.get("flow", {}),
            )
        except Exception:
            pass
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass


@router.websocket("/media-stream/{to_phone_number}/{internal_id}")
async def handle_media_stream(websocket: WebSocket, to_phone_number: str, internal_id: str):
    to_phone_number = unquote(to_phone_number)
    print(f"[INIT] stack telephony={get_telephony_provider()} voice={get_voice_ai_provider()} phone={to_phone_number}")
    await websocket.accept()

    if get_voice_ai_provider() == "sarvam":
        if not SARVAM_API_KEY:
            await websocket.close(code=1008, reason="Sarvam API key not configured")
            return
    elif get_voice_ai_provider() == "gemini":
        if not GEMINI_API_KEY:
            await websocket.close(code=1008, reason="Gemini API key not configured")
            return
    else:
        if not ELEVENLABS_API_KEY or not ELEVEN_LABS_COLD_CALLING_AGENT_ID:
            await websocket.close(code=1008, reason="ElevenLabs configuration error")
            return

    audio_interface = _get_telephony_interface(websocket)

    try:
        if get_voice_ai_provider() == "sarvam":
            await _run_sarvam_session(websocket, to_phone_number, internal_id, audio_interface)
        elif get_voice_ai_provider() == "gemini":
            await _run_gemini_session(websocket, to_phone_number, internal_id, audio_interface)
        else:
            await _run_elevenlabs_session(websocket, to_phone_number, internal_id, audio_interface)
    except WebSocketDisconnect:
        print(f"[WEBSOCKET] disconnected {to_phone_number}")
    except Exception as exc:
        print(f"[ERROR] WebSocket handler: {exc}")
        traceback.print_exc()
    finally:
        if get_telephony_provider() == "kommuno" and hasattr(audio_interface, "send_session_end"):
            try:
                await audio_interface.send_session_end()
            except Exception:
                pass
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except RuntimeError:
                pass
