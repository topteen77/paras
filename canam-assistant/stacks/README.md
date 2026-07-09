# Provider Stack Branches

Test each voice stack by checking out its branch and copying the matching `.env.example`.

| # | Branch | Telephony | Voice AI | Status |
|---|--------|-----------|----------|--------|
| 1 | `ElevenLabs-Twilio` | Twilio | ElevenLabs Agents | Integrated |
| 2 | `Plivo-Sarvam` | Plivo | Sarvam STT+LLM+TTS | **Ready to test** |
| 3 | `FreJun-Teler` | FreJun Teler | FreJun (full stack) | Stub |
| 4 | `Plivo-ElevenLabs` | Plivo | ElevenLabs Agents | Stub |
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

### Plivo Console — set callback URLs

Open **http://localhost:8080/plivo/setup** (or `/health`) to see your exact URLs.

For **inbound** calls (someone dials your Plivo number), create an XML Application in [Plivo Console](https://console.plivo.com):

| Field | URL |
|-------|-----|
| **Answer URL** | `https://YOUR-NGROK/plivo/inbound` (POST) |
| **Hangup URL** | `https://YOUR-NGROK/plivo/hangup` (POST) |
| **Fallback Answer URL** | `https://YOUR-NGROK/plivo/inbound` (POST) |

Then link that Application to your Plivo number.

### After call ends — get Q&A and recording

Each call produces a **post-call report** with transcript, Q&A pairs, and Plivo recording URL.

| How to get data | URL |
|-----------------|-----|
| Single call report | `GET /call/report/{internal_id}` |
| List recent calls | `GET /call/reports` |
| Auto-push to your server | Set `POST_CALL_WEBHOOK_URL` in `.env` |

Example report fields:
```json
{
  "event": "call_completed",
  "internal_id": "...",
  "to_phone_number": "+91...",
  "qa_pairs": [{"user_question": "Canada", "agent_answer": "Great choice! ..."}],
  "transcript": [{"role": "user", "text": "..."}, {"role": "assistant", "text": "..."}],
  "recording": {"url": "https://...", "duration_seconds": "120"},
  "report_url": "https://your-ngrok/call/report/..."
}
```

Recording is enabled automatically via Plivo `<Record recordSession="true">` in the answer XML. Plivo posts the recording URL to `/recording/ready/{internal_id}` when ready (usually within 1–2 minutes after hangup).

For **outbound** tests (`/make-call-direct`), callback URLs are sent automatically in the API call — no Plivo Application answer URL needed. You still need ngrok on **port 8080**:

```bash
ngrok http --url=YOUR-SUBDOMAIN.ngrok-free.dev 8080
```

Verify webhooks reach your server — after answering a call, logs should show:
```
[PLIVO_RING] ...
[PLIVO_ANSWER] ...
[INIT] stack telephony=plivo voice=sarvam ...
```

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
