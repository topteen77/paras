import json
import traceback
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation, ConversationInitiationData

from common.functions import end_call_by_internal_id, get_executive_summary
from handleAudioCalls.call_routes import add_call_staus_to_pubsub
from .twilio_audio_interface import TwilioAudioInterface
from .kommuno_audio_interface import KommunoAudioInterface
from common.config import (
    ELEVENLABS_API_KEY, 
    ELEVEN_LABS_COLD_CALLING_AGENT_ID, 
    AUDIO_PROVIDER
)
from google.cloud import firestore

router = APIRouter()

def log_conversation_to_firestore(conversation_id: str, to_number: str, internal_id: str):
    db = firestore.Client()
    # Get ref to document
    print(f"updating : conversation_id={conversation_id}, to_number={to_number}, internal_id={internal_id}")
    doc_ref = db.collection('conversation-history').document(to_number).collection('calls').document(internal_id)
    doc = doc_ref.get()
    if doc.exists:
        doc_ref.set({
            'conversation_id': conversation_id,
            }, merge=True)
        
@router.websocket("/media-stream/{to_phone_number}/{internal_id}")
async def handle_media_stream(
    websocket: WebSocket, 
    to_phone_number: str, 
    internal_id: str
):
    """
    WebSocket endpoint for handling media streams from different providers
    Provider is determined by the AUDIO_PROVIDER environment variable
    
    Args:
        websocket: WebSocket connection
        to_phone_number: Phone number being called
        internal_id: Internal call identifier
    """
    print(f"[INIT] Starting WebSocket connection for phone: {to_phone_number}, internal_id: {internal_id}")
    
    await websocket.accept()
    print(f"[WEBSOCKET] WebSocket connection accepted for {to_phone_number}")
    
    # Get provider from environment variable
    provider = AUDIO_PROVIDER
    print(f"[CONFIG] Using {provider} provider for {to_phone_number}, internal_id: {internal_id}")

    # Check configuration based on provider
    if not ELEVENLABS_API_KEY or not ELEVEN_LABS_COLD_CALLING_AGENT_ID:
        print(f"[ERROR] ElevenLabs API Key or Agent ID not configured for {to_phone_number}")
        await websocket.close(code=1008, reason="ElevenLabs configuration error")
        return

    print(f"[CONFIG] ElevenLabs configuration validated for {to_phone_number}")

    # Initialize the appropriate audio interface based on provider
    if provider == "kommuno":
        audio_interface = KommunoAudioInterface(websocket)
        print(f"[INTERFACE] Using Kommuno audio interface for {to_phone_number}")
    else:
        audio_interface = TwilioAudioInterface(websocket)
        print(f"[INTERFACE] Using Twilio audio interface for {to_phone_number}")

    print(f"[ELEVENLABS] Initializing ElevenLabs client for {to_phone_number}")
    eleven_labs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    conversation = None  # Initialize conversation to None

    dynamic_vars = {
        "executive_summary": get_executive_summary(to_phone_number),
    }
    print(f"[DYNAMIC_VARS] Dynamic Variables loaded for {to_phone_number}: {dynamic_vars}")
    
    config = ConversationInitiationData(
        dynamic_variables=dynamic_vars
    )
    print(f"[CONFIG] ConversationInitiationData created for {to_phone_number}")
    
    try:
        print(f"[CONVERSATION] Creating ElevenLabs conversation for {to_phone_number}")
        conversation = Conversation(
            client=eleven_labs_client,
            agent_id=ELEVEN_LABS_COLD_CALLING_AGENT_ID,
            config=config,
            requires_auth=False,  # Security > Enable authentication
            audio_interface=audio_interface,
            callback_agent_response=lambda text: print(f"[AGENT] {to_phone_number}: {text}"),
            callback_user_transcript=lambda text: print(f"[USER] {to_phone_number}: {text}"),
        )

        print(f"[CONVERSATION] Starting conversation session for {to_phone_number}")
        conversation.start_session()
        print(f"[CONVERSATION] Conversation session started successfully for {to_phone_number}")

        # For Kommuno, send session start message
        if provider == "kommuno":
            print(f"[KOMMUNO] Sending session start message for {to_phone_number}")
            await audio_interface.send_session_start()
            print(f"[KOMMUNO] Session start message sent for {to_phone_number}")

        print(f"[WEBSOCKET] Starting to listen for messages from {to_phone_number}")
        message_count = 0
        
        try:
            while True:
                try:
                    # Receive raw message to handle both text and binary
                    message = await websocket.receive()
                    message_count += 1
                    
                    # Handle different message types
                    if message["type"] == "websocket.disconnect":
                        print(f"[WEBSOCKET] Disconnect message received for {to_phone_number}")
                        break
                    elif message["type"] == "websocket.receive":
                        # Handle text messages (JSON)
                        if "text" in message:
                            text_data = message["text"]
                            if not text_data:
                                continue
                            
                            print(f"[MESSAGE] Received text message #{message_count} from {to_phone_number} (length: {len(text_data)})")
                            
                            try:
                                data = json.loads(text_data)
                                print(f"[MESSAGE] Parsed JSON message #{message_count} from {to_phone_number}: {data.get('type', 'unknown_type') if isinstance(data, dict) else 'invalid_format'}")
                                
                                if provider == "kommuno":
                                    print(f"[KOMMUNO] Handling message #{message_count} for {to_phone_number}")
                                    await audio_interface.handle_kommuno_message(data)
                                else:
                                    print(f"[TWILIO] Handling message #{message_count} for {to_phone_number}")
                                    await audio_interface.handle_twilio_message(data)
                                    
                            except json.JSONDecodeError as e:
                                print(f"[ERROR] JSON parsing error for message #{message_count} from {to_phone_number}: {e}")
                            except Exception as e:
                                print(f"[ERROR] Error handling message #{message_count} from {to_phone_number}: {e}")
                                traceback.print_exc()
                        
                        # Handle binary messages (if any)
                        elif "bytes" in message:
                            binary_data = message["bytes"]
                            print(f"[MESSAGE] Received binary message #{message_count} from {to_phone_number} (length: {len(binary_data)})")
                            # Binary messages are typically not used in Twilio/Kommuno text-based protocols
                            # But we handle them gracefully without crashing
                        
                        else:
                            print(f"[MESSAGE] Unknown message format #{message_count} from {to_phone_number}: {message}")
                    
                    else:
                        print(f"[MESSAGE] Unhandled message type #{message_count} from {to_phone_number}: {message.get('type', 'unknown')}")
                        
                except WebSocketDisconnect:
                    print(f"[WEBSOCKET] WebSocket disconnected during message processing for {to_phone_number}")
                    break
                except Exception as e:
                    print(f"[ERROR] Error receiving message #{message_count} from {to_phone_number}: {e}")
                    traceback.print_exc()
                    break
                    
        except WebSocketDisconnect:
            print(f"[WEBSOCKET] WebSocket disconnected during message iteration for {to_phone_number}")
        except Exception as e:
            print(f"[ERROR] Error in WebSocket message iteration for {to_phone_number}: {e}")
            traceback.print_exc()

    except WebSocketDisconnect:
        print(f"[WEBSOCKET] WebSocket disconnected for {to_phone_number}, internal_id: {internal_id}")
    except Exception as e:
        print(f"[ERROR] Unexpected error in WebSocket handler for {to_phone_number}: {e}")
        traceback.print_exc()
    finally:
        print(f"[CLEANUP] Starting cleanup for {to_phone_number}, internal_id: {internal_id}")
        if conversation:
            try:
                print(f"[CONVERSATION] Ending conversation session for {to_phone_number}")
                conversation.end_session()
                print(f"[CONVERSATION] Conversation session ended for {to_phone_number}")
                
                print(f"[CLEANUP] Calling end_call_by_internal_id for {to_phone_number}")
                end_call_by_internal_id(internal_id, to_phone_number)
                
                print(f"[CONVERSATION] Waiting for session end for {to_phone_number}")
                conversation_id = conversation.wait_for_session_end()
                print(f"[CONVERSATION] Session ended with conversation_id: {conversation_id} for {to_phone_number}")
                
                print(f"[FIRESTORE] Logging conversation to Firestore for {to_phone_number}")
                log_conversation_to_firestore(conversation_id, to_phone_number, internal_id)
                
                print(f"[PUBSUB] Adding call status to pubsub for {to_phone_number}")
                add_call_staus_to_pubsub('', internal_id, to_phone_number, 'completed')
                
                print(f"[CLEANUP] Conversation cleanup completed for {to_phone_number}")
            except Exception as e:
                print(f"[ERROR] Error during conversation cleanup for {to_phone_number}: {e}")
                traceback.print_exc()
        
        # For Kommuno, send session end message
        if provider == "kommuno" and hasattr(audio_interface, 'send_session_end'):
            try:
                print(f"[KOMMUNO] Sending session end message for {to_phone_number}")
                await audio_interface.send_session_end()
                print(f"[KOMMUNO] Session end message sent for {to_phone_number}")
            except Exception as e:
                print(f"[ERROR] Error sending Kommuno session end for {to_phone_number}: {e}")
        
        # Ensure WebSocket is closed if not already
        if websocket.client_state != WebSocketDisconnect:
            try:
                print(f"[WEBSOCKET] Closing WebSocket connection for {to_phone_number}")
                await websocket.close()
                print(f"[WEBSOCKET] WebSocket closed for {to_phone_number}")
            except RuntimeError as e:
                print(f"[WEBSOCKET] WebSocket already closed for {to_phone_number}: {e}")
        
        print(f"[CLEANUP] Complete cleanup finished for {to_phone_number}, internal_id: {internal_id}")



