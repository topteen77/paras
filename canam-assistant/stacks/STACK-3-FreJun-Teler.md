# Stack 3: FreJun Teler — Implementation Scaffold

**Status:** Not yet implemented.

## Planned architecture

FreJun Teler outbound call → WebSocket media stream → FreJun native voice AI agent.

## To implement

1. `handleAudioCalls/frejun_audio_interface.py`
2. FreJun provider in `common/telephony.py`
3. `VOICE_AI_PROVIDER=frejun` in `websocket_routes.py`
