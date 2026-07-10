import os
from dotenv import load_dotenv

load_dotenv()

# --- Stack selection ---
# Stack 1: telephony=twilio,  voice=elevenlabs
# Stack 2: telephony=plivo,   voice=sarvam
# Stack 4: telephony=plivo,   voice=elevenlabs
# Stack 3: telephony=frejun,   voice=sarvam (or gemini via dashboard)
# Stack 7: telephony=plivo,   voice=gemini
STACK_NAME = os.getenv("STACK_NAME", "ElevenLabs-Twilio")
TELEPHONY_PROVIDER = os.getenv("TELEPHONY_PROVIDER", os.getenv("AUDIO_PROVIDER", "twilio")).lower()
VOICE_AI_PROVIDER = os.getenv("VOICE_AI_PROVIDER", "elevenlabs").lower()

# --- ElevenLabs ---
ELEVEN_LABS_COLD_CALLING_AGENT_ID = os.getenv("ELEVEN_LABS_COLD_CALLING_AGENT_ID")
ELEVEN_LABS_AFTER_VISIT_FEEDBACK_AGENT_ID = os.getenv("ELEVEN_LABS_AFTER_VISIT_FEEDBACK_AGENT_ID")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# --- Twilio ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# --- Plivo ---
PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN")
PLIVO_PHONE_NUMBER = os.getenv("PLIVO_PHONE_NUMBER")

# --- Sarvam AI ---
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_CHAT_MODEL = os.getenv("SARVAM_CHAT_MODEL", "sarvam-30b")
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v2")
SARVAM_TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "anushka")
SARVAM_TTS_PACE = float(os.getenv("SARVAM_TTS_PACE", "0.95"))
SARVAM_TTS_PITCH = float(os.getenv("SARVAM_TTS_PITCH", "0.0"))
SARVAM_TTS_LOUDNESS = float(os.getenv("SARVAM_TTS_LOUDNESS", "1.1"))
SARVAM_LANGUAGE_CODE = os.getenv("SARVAM_LANGUAGE_CODE", "en-IN")
SARVAM_SYSTEM_PROMPT_PATH = os.getenv(
    "SARVAM_SYSTEM_PROMPT_PATH", "prompts/monica_cold_call.txt"
)

# --- Gemini Live ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.0-flash-live-001")
GEMINI_VOICE_NAME = os.getenv("GEMINI_VOICE_NAME", "").strip() or None
GEMINI_LANGUAGE_CODE = os.getenv("GEMINI_LANGUAGE_CODE", "en-IN")

# --- FreJun Teler ---
TELER_API_KEY = os.getenv("TELER_API_KEY") or os.getenv("FREJUN_API_KEY")
TELER_PHONE_NUMBER = os.getenv("TELER_PHONE_NUMBER") or os.getenv("FREJUN_PHONE_NUMBER")

# --- Shared ---
NGROK_URL = os.getenv("NGROK_URL") or ""
WEB_SERVER_URL = (
    os.getenv("WEB_SERVER_URL") or NGROK_URL or "http://127.0.0.1:8080"
)
POST_CALL_WEBHOOK_URL = os.getenv("POST_CALL_WEBHOOK_URL", "").strip() or None
CALL_RECORDINGS_DIR = os.getenv("CALL_RECORDINGS_DIR", "call-recordings")
PROJECT_ID = os.getenv("PROJECT_ID")
QUEUE_NAME = os.getenv("QUEUE_NAME")
REGION_NAME = os.getenv("REGION_NAME")
MAX_PARRALLEL_REQUESTS_TO_AGENT = int(os.getenv("MAX_PARRALLEL_REQUESTS_TO_AGENT", 20))
DEFAULT_CALL_DURATION_IN_SECONDS = int(os.getenv("DEFAULT_CALL_DURATION_IN_SECONDS", 180))
BIG_QUERY_DATASET_ID = os.getenv("BIG_QUERY_DATASET_ID")
MAX_CALL_RETRY_COUNT = int(os.getenv("MAX_CALL_RETRY_COUNT", 2))
STATUS_COMPLETE_TASK_DELAY_IN_SECONDS = int(os.getenv("STATUS_COMPLETE_TASK_DELAY_IN_SECONDS", 300))

# Legacy alias
AUDIO_PROVIDER = TELEPHONY_PROVIDER

# --- Kommuno ---
KOMMUNO_API_KEY = os.getenv("KOMMUNO_API_KEY")
KOMMUNO_AGENT_ID = os.getenv("KOMMUNO_AGENT_ID")
KOMMUNO_WEBSOCKET_URL = os.getenv("KOMMUNO_WEBSOCKET_URL", "wss://api.kommuno.ai/v1/websocket")
KOMMUNO_AUDIO_FORMAT = os.getenv("KOMMUNO_AUDIO_FORMAT", "pcm")
KOMMUNO_SAMPLE_RATE = int(os.getenv("KOMMUNO_SAMPLE_RATE", 8000))
KOMMUNO_CHANNELS = int(os.getenv("KOMMUNO_CHANNELS", 1))

PORT = int(os.getenv("PORT", 8080))

print("Configuration loaded:")
print(f"  STACK_NAME: {STACK_NAME}")
print(f"  TELEPHONY_PROVIDER: {TELEPHONY_PROVIDER}")
print(f"  VOICE_AI_PROVIDER: {VOICE_AI_PROVIDER}")
print(f"  ELEVENLABS_API_KEY: {'*' * 5 if ELEVENLABS_API_KEY else 'Not set'}")
print(f"  SARVAM_API_KEY: {'*' * 5 if SARVAM_API_KEY else 'Not set'}")
print(f"  GEMINI_API_KEY: {'*' * 5 if GEMINI_API_KEY else 'Not set'}")
print(f"  TELER_API_KEY: {'*' * 5 if TELER_API_KEY else 'Not set'}")
print(f"  PLIVO_AUTH_ID: {'*' * 5 if PLIVO_AUTH_ID else 'Not set'}")
print(f"  TWILIO_ACCOUNT_SID: {'*' * 5 if TWILIO_ACCOUNT_SID else 'Not set'}")
print(f"  NGROK_URL: {NGROK_URL if NGROK_URL else 'Not set'}")
