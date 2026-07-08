# import os
# import json
# import traceback
# from dotenv import load_dotenv
# from fastapi import FastAPI, Request, WebSocket
# from fastapi.responses import HTMLResponse
# from twilio.twiml.voice_response import VoiceResponse, Connect
# from elevenlabs import ElevenLabs
# from elevenlabs.conversational_ai.conversation import Conversation
# from twilio_audio_interface import TwilioAudioInterface
# from starlette.websockets import WebSocketDisconnect
# from twilio.rest import Client

# load_dotenv()

# ELEVEN_LABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID")
# ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
# TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
# TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
# TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
# NGROK_URL = os.getenv('NGROK_URL')
# PORT = int(os.getenv('PORT', 5050))


# app = FastAPI()

# print("ELEVEN_LABS_AGENT_ID:", ELEVEN_LABS_AGENT_ID)
# print("ELEVENLABS_API_KEY:", ELEVENLABS_API_KEY)
# print("NGROK_URL:", NGROK_URL)

# @app.get("/")
# async def root():
#     return {"message": "Twilio-ElevenLabs Integration Server"}


# @app.post("/make-call")
# async def make_call(request: Request):
#     """Make an outgoing call to the specified phone number."""
#     data = await request.json()
#     to_phone_number = data.get("to")
#     if not to_phone_number:
#         return {"error": "Phone number is required"}

#     client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
#     call = client.calls.create(
#         url=f"{NGROK_URL}/outgoing-call",
#         to=to_phone_number,
#         from_=TWILIO_PHONE_NUMBER
#     )
#     return {"call_sid": call.sid}

# @app.api_route("/outgoing-call", methods=["GET", "POST"])
# async def handle_outgoing_call(request: Request):
#     """Handle outgoing call and return TwiML response to connect to Media Stream."""
#     response = VoiceResponse()
#     # response.say("Please wait while we connect your call to the AI voice assistant...")
#     # response.pause(length=1)
#     # response.say("O.K. you can start talking!")
#     connect = Connect()
#     connect.stream(url=f'wss://{request.url.hostname}/media-stream')
#     response.append(connect)
#     return HTMLResponse(content=str(response), media_type="application/xml")



# @app.post("/twilio/inbound_call")
# async def handle_incoming_call(request: Request):
#     form_data = await request.form()
#     call_sid = form_data.get("CallSid", "Unknown")
#     from_number = form_data.get("From", "Unknown")
#     print(f"Incoming call: CallSid={call_sid}, From={from_number}")

#     response = VoiceResponse()
#     connect = Connect()
#     connect.stream(url=f"wss://{request.url.hostname}/media-stream")
#     response.append(connect)
#     return HTMLResponse(content=str(response), media_type="application/xml")


# @app.websocket("/media-stream")
# async def handle_media_stream(websocket: WebSocket):
#     await websocket.accept()
#     print("WebSocket connection opened")

#     audio_interface = TwilioAudioInterface(websocket)
#     eleven_labs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

#     try:
#         conversation = Conversation(
#             client=eleven_labs_client,
#             agent_id=ELEVEN_LABS_AGENT_ID,
#             requires_auth=False, # Security > Enable authentication
#             audio_interface=audio_interface,
#             callback_agent_response=lambda text: print(f"Agent: {text}"),
#             callback_user_transcript=lambda text: print(f"User: {text}"),
#         )

#         conversation.start_session()
#         print("Conversation started")

#         async for message in websocket.iter_text():
#             if not message:
#                 continue
#             await audio_interface.handle_twilio_message(json.loads(message))

#     except WebSocketDisconnect:
#         print("WebSocket disconnected")
#     except Exception:
#         print("Error occurred in WebSocket handler:")
#         traceback.print_exc()
#     finally:
#         try:
#             conversation.end_session()
#             conversation.wait_for_session_end()
#             print("Conversation ended")
#         except Exception:
#             print("Error ending conversation session:")
#             traceback.print_exc()


# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=PORT)

from fastapi import FastAPI
from common.config import PORT  # Import PORT from the new config file
import call_routes, websocket_routes # Import your new routers

app = FastAPI()

app.include_router(call_routes.router, tags=["Call Handling"])
app.include_router(websocket_routes.router, prefix="/ws", tags=["WebSocket Media Stream"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)