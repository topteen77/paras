import os
from dotenv import load_dotenv

load_dotenv()

ELEVEN_LABS_COLD_CALLING_AGENT_ID = os.getenv("ELEVEN_LABS_COLD_CALLING_AGENT_ID")
ELEVEN_LABS_AFTER_VISIT_FEEDBACK_AGENT_ID = os.getenv("ELEVEN_LABS_AFTER_VISIT_FEEDBACK_AGENT_ID")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
NGROK_URL = os.getenv('NGROK_URL')
PROJECT_ID = os.getenv('PROJECT_ID')
QUEUE_NAME = os.getenv('QUEUE_NAME')
REGION_NAME = os.getenv('REGION_NAME')
MAX_PARRALLEL_REQUESTS_TO_AGENT = int(os.getenv('MAX_PARRALLEL_REQUESTS_TO_AGENT', 20))
DEFAULT_CALL_DURATION_IN_SECONDS = int(os.getenv('DEFAULT_CALL_DURATION_IN_SECONDS', 180))
BIG_QUERY_DATASET_ID = os.getenv('BIG_QUERY_DATASET_ID')
MAX_CALL_RETRY_COUNT = int(os.getenv('MAX_CALL_RETRY_COUNT', 2))
STATUS_COMPLETE_TASK_DELAY_IN_SECONDS = int(os.getenv('STATUS_COMPLETE_TASK_DELAY_IN_SECONDS', 300))

# Audio Provider Configuration
AUDIO_PROVIDER = os.getenv('AUDIO_PROVIDER', 'kommuno').lower()  # Default to 'twilio', can be 'kommuno'

# Kommuno Configuration (if using Kommuno provider)
KOMMUNO_API_KEY = os.getenv('KOMMUNO_API_KEY')
KOMMUNO_AGENT_ID = os.getenv('KOMMUNO_AGENT_ID')
KOMMUNO_WEBSOCKET_URL = os.getenv('KOMMUNO_WEBSOCKET_URL', 'wss://api.kommuno.ai/v1/websocket')
KOMMUNO_AUDIO_FORMAT = os.getenv('KOMMUNO_AUDIO_FORMAT', 'pcm')
KOMMUNO_SAMPLE_RATE = int(os.getenv('KOMMUNO_SAMPLE_RATE', 8000))
KOMMUNO_CHANNELS = int(os.getenv('KOMMUNO_CHANNELS', 1))

PORT = int(os.getenv('PORT', 8080))

print("Configuration loaded:")
print(f"  ELEVEN_LABS_COLD_CALLING_AGENT_ID: {'*' * 5 if ELEVEN_LABS_COLD_CALLING_AGENT_ID else 'Not set'}")
print(f"  ELEVENLABS_API_KEY: {'*' * 5 if ELEVENLABS_API_KEY else 'Not set'}")
print(f"  NGROK_URL: {NGROK_URL if NGROK_URL else 'Not set'}")
print(f"  TWILIO_ACCOUNT_SID: {'*' * 5 if TWILIO_ACCOUNT_SID else 'Not set'}")
print(f"  TWILIO_AUTH_TOKEN: {'*' * 5 if TWILIO_AUTH_TOKEN else 'Not set'}")
print(f"  AUDIO_PROVIDER: {AUDIO_PROVIDER}")
if AUDIO_PROVIDER == 'kommuno':
    print(f"  KOMMUNO_API_KEY: {'*' * 5 if KOMMUNO_API_KEY else 'Not set'}")
    print(f"  KOMMUNO_AGENT_ID: {'*' * 5 if KOMMUNO_AGENT_ID else 'Not set'}")
    print(f"  KOMMUNO_WEBSOCKET_URL: {KOMMUNO_WEBSOCKET_URL}")
    print(f"  KOMMUNO_AUDIO_FORMAT: {KOMMUNO_AUDIO_FORMAT}")
    print(f"  KOMMUNO_SAMPLE_RATE: {KOMMUNO_SAMPLE_RATE}")
    print(f"  KOMMUNO_CHANNELS: {KOMMUNO_CHANNELS}")
