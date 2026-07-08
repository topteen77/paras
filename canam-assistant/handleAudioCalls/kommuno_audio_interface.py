import asyncio
import base64
import json
from fastapi import WebSocket
from elevenlabs.conversational_ai.conversation import AudioInterface
from starlette.websockets import WebSocketDisconnect, WebSocketState
from common.config import (
    KOMMUNO_AUDIO_FORMAT,
    KOMMUNO_SAMPLE_RATE,
    KOMMUNO_CHANNELS
)


class KommunoAudioInterface(AudioInterface):
    """
    Audio interface for Kommuno AI Integration
    
    This class handles the audio streaming between Kommuno and ElevenLabs
    """
    
    def __init__(self, websocket: WebSocket):
        print(f"[KOMMUNO_INTERFACE] Initializing Kommuno audio interface")
        self.websocket = websocket
        self.input_callback = None
        self.uuid = None  # Changed from session_id to uuid
        self.loop = asyncio.get_event_loop()
        self.is_connected = False
        print(f"[KOMMUNO_INTERFACE] Kommuno audio interface initialized successfully")

    def start(self, input_callback):
        """Start the audio interface with the given input callback"""
        print(f"[KOMMUNO_INTERFACE] Starting audio interface with input callback (uuid: {self.uuid})")
        self.input_callback = input_callback
        self.is_connected = True
        print(f"[KOMMUNO_INTERFACE] Audio interface started, is_connected: {self.is_connected} (uuid: {self.uuid})")

    def stop(self):
        """Stop the audio interface"""
        print(f"[KOMMUNO_INTERFACE] Stopping audio interface (uuid: {self.uuid})")
        self.input_callback = None
        self.uuid = None
        self.is_connected = False
        print(f"[KOMMUNO_INTERFACE] Audio interface stopped")

    def output(self, audio: bytes):
        """
        Send audio data to Kommuno
        This method should return quickly and not block the calling thread.
        """
        if self.is_connected:
            print(f"[KOMMUNO_INTERFACE] Scheduling audio output to Kommuno (audio length: {len(audio)} bytes, uuid: {self.uuid})")
            asyncio.run_coroutine_threadsafe(self.send_audio_to_kommuno(audio), self.loop)
        else:
            print(f"[KOMMUNO_INTERFACE] Warning: Attempted to send audio while not connected (uuid: {self.uuid})")

    def interrupt(self):
        """Send interrupt signal to Kommuno"""
        if self.is_connected:
            print(f"[KOMMUNO_INTERFACE] Scheduling interrupt signal to Kommuno (uuid: {self.uuid})")
            asyncio.run_coroutine_threadsafe(self.send_interrupt_to_kommuno(), self.loop)
        else:
            print(f"[KOMMUNO_INTERFACE] Warning: Attempted to send interrupt while not connected (uuid: {self.uuid})")

    async def send_audio_to_kommuno(self, audio: bytes):
        """Send audio data to Kommuno via WebSocket using Audio_Byte_To_Play event format"""
        print(f"[KOMMUNO_INTERFACE] Sending audio to Kommuno (uuid: {self.uuid}, is_connected: {self.is_connected})")
        
        # Generate UUID if not present (for ElevenLabs integration)
        if not self.uuid:
            import uuid
            temp_uuid = str(uuid.uuid4())
            self.uuid = temp_uuid
            print(f"[KOMMUNO_INTERFACE] Generated UUID for audio transmission: {temp_uuid}")
        
        if self.is_connected:
            try:
                # Convert audio bytes to the format expected by Kommuno
                # Based on documentation: "audio_bytes_to_play": "b'RIFFX\\x15\\x01\\x00WAVEfmt..."
                # The documentation shows the audio_bytes_to_play as a string representation of bytes
                audio_bytes_string = repr(audio)  # This creates the b'...' string format
                
                # Create Kommuno Audio_Byte_To_Play message format
                audio_message = {
                    "data": {
                        "session_id": self.uuid,  # Note: Kommuno uses session_id in data payload
                        "count": 1,  # Increment counter if needed
                        "audio_bytes_to_play": audio_bytes_string,
                        "sample_rate": KOMMUNO_SAMPLE_RATE,
                        "channels": KOMMUNO_CHANNELS,
                        "sample_width": 2  # Based on documentation example
                    }
                }
                
                print(f"[KOMMUNO_INTERFACE] Prepared Audio_Byte_To_Play message with sample_rate: {KOMMUNO_SAMPLE_RATE}, channels: {KOMMUNO_CHANNELS} (uuid: {self.uuid})")
                
                if self.websocket.application_state == WebSocketState.CONNECTED:
                    await self.websocket.send_text(json.dumps(audio_message))
                    print(f"[KOMMUNO_INTERFACE] Audio_Byte_To_Play message sent successfully to Kommuno (uuid: {self.uuid})")
                else:
                    print(f"[KOMMUNO_INTERFACE] Warning: WebSocket not connected, audio message not sent (uuid: {self.uuid})")
                    
            except (WebSocketDisconnect, RuntimeError) as e:
                print(f"[KOMMUNO_INTERFACE] Error sending audio to Kommuno: {e} (uuid: {self.uuid})")
                self.is_connected = False
        else:
            print(f"[KOMMUNO_INTERFACE] Warning: Cannot send audio - not connected (uuid: {self.uuid})")

    async def send_interrupt_to_kommuno(self):
        """Send hangup message to Kommuno"""
        print(f"[KOMMUNO_INTERFACE] Sending hangup to Kommuno (uuid: {self.uuid})")
        
        # Generate UUID if not present
        if not self.uuid:
            import uuid
            temp_uuid = str(uuid.uuid4())
            self.uuid = temp_uuid
            print(f"[KOMMUNO_INTERFACE] Generated UUID for hangup: {temp_uuid}")
        
        if self.is_connected:
            try:
                # Create Kommuno Hangup event message format
                hangup_message = {
                    "data": {
                        "response": "OK",
                        "session_id": self.uuid,
                        "hangup": "true"
                    }
                }
                
                print(f"[KOMMUNO_INTERFACE] Prepared hangup message (uuid: {self.uuid})")
                
                if self.websocket.application_state == WebSocketState.CONNECTED:
                    await self.websocket.send_text(json.dumps(hangup_message))
                    print(f"[KOMMUNO_INTERFACE] Hangup message sent successfully to Kommuno (uuid: {self.uuid})")
                else:
                    print(f"[KOMMUNO_INTERFACE] Warning: WebSocket not connected, hangup message not sent (uuid: {self.uuid})")
                    
            except (WebSocketDisconnect, RuntimeError) as e:
                print(f"[KOMMUNO_INTERFACE] Error sending hangup to Kommuno: {e} (uuid: {self.uuid})")
                self.is_connected = False
        else:
            print(f"[KOMMUNO_INTERFACE] Warning: Cannot send hangup - not connected (uuid: {self.uuid})")

    async def handle_kommuno_message(self, data):
        """Handle incoming messages from Kommuno"""
        print(f"[KOMMUNO_INTERFACE] Handling Kommuno message (uuid: {self.uuid})")
        
        try:
            # Check for different Kommuno event types
            if "event" in data:
                # Handle Start Event
                event_type = data.get("event")
                print(f"[KOMMUNO_INTERFACE] Event type: {event_type} (uuid: {self.uuid})")
                
                if event_type == "start":
                    # Extract uuid from Start Event
                    kommuno_uuid = data.get("uuid")
                    if kommuno_uuid:
                        old_uuid = self.uuid
                        self.uuid = kommuno_uuid
                        print(f"[KOMMUNO_INTERFACE] Session UUID updated by Kommuno: {kommuno_uuid} (previous: {old_uuid})")
                        
                        # Log additional start event details
                        source = data.get("Source", "Unknown")
                        destination = data.get("Destination", "Unknown")
                        forward_num = data.get("forward_num", "Unknown")
                        print(f"[KOMMUNO_INTERFACE] Start event details - Source: {source}, Destination: {destination}, Forward: {forward_num} (uuid: {self.uuid})")
                    else:
                        print(f"[KOMMUNO_INTERFACE] Start event received but no UUID provided, keeping existing uuid: {self.uuid}")
                        
            elif "played" in data:
                # Handle Played Event
                played_status = data.get("played")
                event_uuid = data.get("uuid")
                print(f"[KOMMUNO_INTERFACE] Played event - Status: {played_status}, UUID: {event_uuid} (uuid: {self.uuid})")
                
            elif "data" in data:
                # Handle data-based messages (hangup, etc.)
                data_content = data.get("data", {})
                
                if "hangup" in data_content:
                    # Handle Hangup Event
                    hangup_status = data_content.get("hangup")
                    session_id = data_content.get("session_id")
                    print(f"[KOMMUNO_INTERFACE] Hangup event - Status: {hangup_status}, Session ID: {session_id} (uuid: {self.uuid})")
                    if hangup_status == "true":
                        self.uuid = None
                        self.is_connected = False
                        print(f"[KOMMUNO_INTERFACE] Session ended due to hangup")
                        
                elif "audio_bytes_to_play" in data_content:
                    # Handle incoming audio data (if Kommuno sends audio back)
                    print(f"[KOMMUNO_INTERFACE] Received audio data from Kommuno (uuid: {self.uuid})")
                    if self.input_callback:
                        try:
                            # Extract audio bytes from the data
                            audio_bytes_str = data_content.get("audio_bytes_to_play")
                            self.input_callback(audio_bytes_str)  # Assuming input_callback expects bytes
                            # Convert string representation back to bytes if needed
                            # This depends on how Kommuno formats the audio data
                            print(f"[KOMMUNO_INTERFACE] Processing incoming audio data (uuid: {self.uuid})")
                            # Note: You may need to adjust this based on actual Kommuno audio format
                        except Exception as e:
                            print(f"[KOMMUNO_INTERFACE] Error processing audio data: {e} (uuid: {self.uuid})")
                            
            else:
                print(f"[KOMMUNO_INTERFACE] Unknown message format from Kommuno: {data} (uuid: {self.uuid})")
                
        except Exception as e:
            print(f"[KOMMUNO_INTERFACE] Error handling Kommuno message: {e} (uuid: {self.uuid})")

    async def send_session_start(self):
        """Generate temporary UUID for ElevenLabs integration and wait for Kommuno Start Event"""
        print(f"[KOMMUNO_INTERFACE] Initializing session for ElevenLabs integration (uuid: {self.uuid})")
        
        # Generate temporary UUID so ElevenLabs can start sending audio immediately
        if not self.uuid:
            import uuid
            temp_uuid = str(uuid.uuid4())
            self.uuid = temp_uuid
            print(f"[KOMMUNO_INTERFACE] Generated temporary UUID for ElevenLabs: {temp_uuid}")
        
        print(f"[KOMMUNO_INTERFACE] Session ready for ElevenLabs audio streaming (uuid: {self.uuid})")
        print(f"[KOMMUNO_INTERFACE] Waiting for Kommuno Start Event to update UUID if needed")

    async def send_session_end(self):
        """Send hangup message to Kommuno to end the session"""
        print(f"[KOMMUNO_INTERFACE] Sending session end hangup to Kommuno (uuid: {self.uuid})")
        
        try:
            # Use the same hangup format as interrupt
            end_message = {
                "data": {
                    "response": "OK",
                    "session_id": self.uuid,
                    "hangup": "true"
                }
            }
            
            print(f"[KOMMUNO_INTERFACE] Prepared session end hangup message (uuid: {self.uuid})")
            
            if self.websocket.application_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(json.dumps(end_message))
                print(f"[KOMMUNO_INTERFACE] Session end hangup message sent successfully (uuid: {self.uuid})")
                
        except (WebSocketDisconnect, RuntimeError) as e:
            print(f"[KOMMUNO_INTERFACE] Error sending session end to Kommuno: {e} (uuid: {self.uuid})")
        finally:
            self.is_connected = False
            print(f"[KOMMUNO_INTERFACE] Session end cleanup completed (uuid: {self.uuid})")
