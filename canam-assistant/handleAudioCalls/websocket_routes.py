import json
import traceback
from urllib.parse import unquote

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation, ConversationInitiationData
from google.cloud import firestore

from common.config import (
    ELEVENLABS_API_KEY,
    ELEVEN_LABS_COLD_CALLING_AGENT_ID,
    SARVAM_API_KEY,
    TELEPHONY_PROVIDER,
    VOICE_AI_PROVIDER,
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
from handleAudioCalls.sarvam_voice_agent import SarvamVoiceAgent
from handleAudioCalls.twilio_audio_interface import TwilioAudioInterface

router = APIRouter()


def log_conversation_to_firestore(conversation_id: str, to_number: str, internal_id: str):
    db = firestore.Client()
    doc_ref = (
        db.collection("conversation-history")
        .document(to_number)
        .collection("calls")
        .document(internal_id)
    )
    if doc_ref.get().exists:
        doc_ref.set({"conversation_id": conversation_id}, merge=True)


def _get_telephony_interface(websocket: WebSocket):
    if TELEPHONY_PROVIDER == "plivo":
        return PlivoAudioInterface(websocket)
    if TELEPHONY_PROVIDER == "kommuno":
        return KommunoAudioInterface(websocket)
    return TwilioAudioInterface(websocket)


async def _handle_telephony_message(audio_interface, data: dict):
    if TELEPHONY_PROVIDER == "plivo":
        await audio_interface.handle_plivo_message(data)
    elif TELEPHONY_PROVIDER == "kommuno":
        await audio_interface.handle_kommuno_message(data)
    else:
        await audio_interface.handle_twilio_message(data)


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

    if TELEPHONY_PROVIDER == "kommuno":
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
        if call_uuid:
            print(f"[SARVAM_HANGUP] ending Plivo call {call_uuid}")
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

    if TELEPHONY_PROVIDER == "plivo":
        audio_interface.set_input_callback(on_audio_in)
    elif hasattr(audio_interface, "start"):
        audio_interface.start(on_audio_in)

    greeted = False
    await agent.prepare()
    conversation_id = agent.conversation_id

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

            if not greeted and getattr(audio_interface, "stream_id", None):
                call_uuid = getattr(audio_interface, "call_uuid", None)
                if call_uuid:
                    link_call_uuid(call_uuid, internal_id)
                await agent.speak_greeting()
                greeted = True

            while pcm_buffer:
                chunk = pcm_buffer.pop(0)
                await agent.feed_audio(chunk)

            if greeted and not agent._running:
                break
    finally:
        await agent.stop()
        conversation = agent.export_conversation()
        save_transcript(internal_id, conversation)
        try_deliver_report(internal_id)
        if not agent._hangup_scheduled:
            call_uuid = getattr(audio_interface, "call_uuid", None)
            if call_uuid:
                end_call(call_uuid)
            else:
                end_call_by_internal_id(internal_id, to_phone_number)
        log_conversation_to_firestore(conversation_id, to_phone_number, internal_id)
        add_call_staus_to_pubsub(
            getattr(audio_interface, "call_uuid", "") or "",
            internal_id,
            to_phone_number,
            "completed",
        )

    return conversation_id


@router.websocket("/media-stream/{to_phone_number}/{internal_id}")
async def handle_media_stream(websocket: WebSocket, to_phone_number: str, internal_id: str):
    to_phone_number = unquote(to_phone_number)
    print(f"[INIT] stack telephony={TELEPHONY_PROVIDER} voice={VOICE_AI_PROVIDER} phone={to_phone_number}")
    await websocket.accept()

    if VOICE_AI_PROVIDER == "sarvam":
        if not SARVAM_API_KEY:
            await websocket.close(code=1008, reason="Sarvam API key not configured")
            return
    else:
        if not ELEVENLABS_API_KEY or not ELEVEN_LABS_COLD_CALLING_AGENT_ID:
            await websocket.close(code=1008, reason="ElevenLabs configuration error")
            return

    audio_interface = _get_telephony_interface(websocket)

    try:
        if VOICE_AI_PROVIDER == "sarvam":
            await _run_sarvam_session(websocket, to_phone_number, internal_id, audio_interface)
        else:
            await _run_elevenlabs_session(websocket, to_phone_number, internal_id, audio_interface)
    except WebSocketDisconnect:
        print(f"[WEBSOCKET] disconnected {to_phone_number}")
    except Exception as exc:
        print(f"[ERROR] WebSocket handler: {exc}")
        traceback.print_exc()
    finally:
        if TELEPHONY_PROVIDER == "kommuno" and hasattr(audio_interface, "send_session_end"):
            try:
                await audio_interface.send_session_end()
            except Exception:
                pass
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except RuntimeError:
                pass
