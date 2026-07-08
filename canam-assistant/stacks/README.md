# Provider Stack Branches

Test each voice stack by checking out its branch and copying the matching `.env.example`.

| # | Branch | Telephony | Voice AI | Status |
|---|--------|-----------|----------|--------|
| 1 | `ElevenLabs-Twilio` | Twilio | ElevenLabs Agents | Integrated |
| 2 | `Plivo-Sarvam` | Plivo | Sarvam STT+LLM+TTS | **Ready to test** |
| 3 | `FreJun-Teler` | FreJun Teler | FreJun (full stack) | Stub |
| 4 | `Plivo-ElevenLabs` | Plivo | ElevenLabs Agents | Configured |
| 5 | `Smallest-ai-Trikon` | Trikon/Smallest | Smallest.ai | Stub |
| 6 | `Exotel-Sarvam` | Exotel | Sarvam STT+LLM+TTS | Stub |

## Quick start (any stack)

```bash
git checkout <branch-name>
cp stacks/<N>-<name>.env.example .env
# Edit .env with your API keys
./deploy.sh          # from repo root (Paras/deploy.sh)
```

## Stack 2: Plivo + Sarvam

```bash
git checkout Plivo-Sarvam
cp stacks/2-Plivo-Sarvam.env.example .env
```

### Required credentials

| Key | Source |
|-----|--------|
| `PLIVO_AUTH_ID` / `PLIVO_AUTH_TOKEN` | [Plivo Console](https://console.plivo.com) |
| `PLIVO_PHONE_NUMBER` | Plivo India DID |
| `SARVAM_API_KEY` | [Sarvam Dashboard](https://dashboard.sarvam.ai) |
| `NGROK_AUTHTOKEN` | [ngrok](https://dashboard.ngrok.com) |
| GCP service account | Firestore / Pub/Sub / Tasks |

### Test a direct outbound call (bypasses scheduler)

```bash
curl -X POST http://localhost:8080/make-call-direct \
  -H 'Content-Type: application/json' \
  -d '{"to": "+91XXXXXXXXXX"}'
```

### Architecture

```
Plivo outbound call
  → POST /outgoing-call → Plivo XML <Stream>
  → WebSocket /ws/media-stream
  → PlivoAudioInterface (mulaw ↔ PCM)
  → SarvamVoiceAgent
       ├── STT WebSocket (saaras:v3)
       ├── Chat API (sarvam-30b)
       └── TTS REST (bulbul:v2)
```

### assistantFunctions (GCP)

Update `assistantFunctions-main/main.py` `process_initiated_call` to use Plivo when on this stack.
See `stacks/assistantFunctions-plivo-patch.md`.

### Estimated cost (India)

- Plivo telephony: ~₹0.60/min
- Sarvam STT+TTS+LLM: ~₹1–3/min
- **Total: ~₹2–4/min** vs ~₹12–15/min for Twilio+ElevenLabs
