# Paras — Canam AI Voice Calling Platform

Study-abroad lead-generation platform with AI voice agents, outbound calling, and post-call Q&A/recording export. Runs locally via Docker with optional GCP integration for scheduling and analytics.

## What's included

| Component | Purpose |
|-----------|---------|
| `canam-assistant/` | FastAPI server — telephony webhooks, WebSocket audio, AI voice agent |
| `assistantFunctions-main/` | GCP Cloud Functions for batch scheduling and post-call processing (deploy separately) |
| `call-recordings/` | Local post-call JSON + MP3 exports (created by `deploy.sh`) |
| `deploy.sh` | One-command local Docker + ngrok setup |
| `switch-stack.sh` | Switch git branch and copy matching `.env` template |

## Provider stacks (branches)

| # | Branch | Telephony | Voice AI | Status |
|---|--------|-----------|----------|--------|
| 1 | `ElevenLabs-Twilio` | Twilio | ElevenLabs Agents | Integrated |
| 2 | `Plivo-Sarvam` | Plivo | Sarvam STT + LLM + TTS | **Integrated — active local stack** |
| 3 | `FreJun-Teler` | FreJun Teler | FreJun (bundled) | Scaffold |
| 4 | `Plivo-ElevenLabs` | Plivo | ElevenLabs Agents | Config ready |
| 5 | `Smallest-ai-Trikon` | Trikon | Smallest.ai | Scaffold |
| 6 | `Exotel-Sarvam` | Exotel | Sarvam STT + LLM + TTS | Scaffold |

Stack-specific env templates live in `canam-assistant/stacks/`. See `canam-assistant/stacks/README.md` for Plivo console URLs and architecture details.

---

## Prerequisites

- **Docker** and **Docker Compose v2**
- **Git**
- API keys for your chosen stack (see below)
- **ngrok** account (`NGROK_AUTHTOKEN` in `.env`) — required for Plivo/Twilio webhooks on localhost

---

## First-time setup (new repo clone)

```bash
git clone <your-repo-url> Paras
cd Paras

# Switch to the stack you want (example: Plivo + Sarvam)
./switch-stack.sh 2
# or: git checkout Plivo-Sarvam && cp canam-assistant/stacks/2-Plivo-Sarvam.env.example canam-assistant/.env

# Edit credentials
nano canam-assistant/.env

# Optional: replace placeholder GCP key for Firestore / Pub/Sub features
cp canam-assistant/service_account_key.json.example canam-assistant/service_account_key.json
# Download a real key from GCP Console → IAM → Service Accounts → Keys

# Build and start
./deploy.sh
```

`deploy.sh` will:

1. Create `canam-assistant/uploads/` and `call-recordings/` if missing
2. Build and start `canam-assistant` + `canam-ngrok` containers
3. Detect the ngrok HTTPS URL and write `NGROK_URL` / `WEB_SERVER_URL` into `.env`
4. Print local URLs and test commands

### Verify

```bash
curl http://localhost:8080/health
curl http://localhost:8080/plivo/setup   # Plivo stack — shows callback URLs
./deploy.sh logs                         # tail live logs
```

| URL | Description |
|-----|-------------|
| http://localhost:8080/docs | Swagger API |
| http://localhost:8080/health | Health check |
| http://localhost:4040 | ngrok request inspector |

---

## Stack 2: Plivo + Sarvam (current local setup)

Lower-cost India stack: Plivo telephony + Sarvam `saaras:v3` STT, `sarvam-30b` LLM, `bulbul:v2` TTS.

### Required `.env` values

| Variable | Source |
|----------|--------|
| `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN` | [Plivo Console](https://console.plivo.com) |
| `PLIVO_PHONE_NUMBER` | Your Plivo India DID (e.g. `+912269986889`) |
| `SARVAM_API_KEY` | [Sarvam Dashboard](https://dashboard.sarvam.ai) |
| `NGROK_AUTHTOKEN` | [ngrok Dashboard](https://dashboard.ngrok.com) |
| `SARVAM_TTS_SPEAKER` | Use `anushka` for `bulbul:v2` (not `meera`/`ritu`) |

Recommended Sarvam settings (already in `stacks/2-Plivo-Sarvam.env.example`):

```
SARVAM_CHAT_MODEL=sarvam-30b
SARVAM_STT_MODEL=saaras:v3
SARVAM_TTS_MODEL=bulbul:v2
SARVAM_TTS_SPEAKER=anushka
SARVAM_SYSTEM_PROMPT_PATH=prompts/monica_cold_call.txt
```

### Plivo Console (inbound calls)

Create an XML Application and link it to your Plivo number. Use the URLs from `GET /plivo/setup` (or substitute your ngrok domain):

| Field | URL |
|-------|-----|
| Answer URL | `https://YOUR-NGROK/plivo/inbound` (POST) |
| Hangup URL | `https://YOUR-NGROK/plivo/hangup` (POST) |
| Fallback Answer URL | `https://YOUR-NGROK/plivo/inbound` (POST) |

**Important:** ngrok must tunnel **port 8080** (the API), not port 80. `deploy.sh` handles this via the `canam-ngrok` container.

For **outbound** test calls (`/make-call-direct`), callback URLs are set automatically in the API — no Plivo Application answer URL needed.

### Architecture

```
Plivo call
  → POST /outgoing-call or /plivo/inbound  (XML: Record + Stream)
  → WebSocket /ws/media-stream/{phone}/{internal_id}
  → PlivoAudioInterface (mulaw ↔ PCM)
  → SarvamVoiceAgent
       ├── STT streaming (saaras:v3, base64 PCM via SDK)
       ├── Chat API (sarvam-30b)
       └── TTS REST (bulbul:v2)
  → On hangup: transcript + Q&A + recording saved locally
```

### Test an outbound call

```bash
curl -X POST http://localhost:8080/make-call-direct \
  -H 'Content-Type: application/json' \
  -d '{"to": "+91XXXXXXXXXX"}'
```

Answer the phone and speak after Monica's greeting. Logs should show:

```
[INIT] stack telephony=plivo voice=sarvam ...
[SARVAM_STT] connected (saaras v3 streaming)
[USER] +91...: Canada
[AGENT] +91...: Got it. Canada is a great choice! ...
```

### Scheduled / batch calls

```bash
# Queue a call (writes to Firestore)
curl -X POST http://localhost:8080/make-call \
  -H 'Content-Type: application/json' \
  -d '{"to": "+91XXXXXXXXXX"}'

# Process the queue
curl -X POST http://localhost:8080/create-scheduled-task
```

Requires a valid GCP service account for Firestore/Pub/Sub.

---

## Post-call data

Each completed call exports a report to `call-recordings/{phone}_{timestamp}.json` (and downloads the Plivo MP3 when available).

```json
{
  "qa_pairs": [
    {"user_question": "Canada", "agent_answer": "Got it. Canada is a great choice! ..."}
  ],
  "transcript": [{"role": "user", "text": "..."}, {"role": "assistant", "text": "..."}],
  "recording": {"url": "https://...", "local_file": "call-recordings/..."}
}
```

| Endpoint | Description |
|----------|-------------|
| `GET /call/report/{internal_id}` | Single call report |
| `GET /call/reports` | List recent reports |
| `POST /recording/ready/{internal_id}` | Plivo recording callback (automatic) |

Optional: set `POST_CALL_WEBHOOK_URL` in `.env` to push reports to your server when a call ends.

---

## Deploy commands

```bash
./deploy.sh          # build + start
./deploy.sh restart  # rebuild and restart (after code changes)
./deploy.sh logs     # follow container logs
./deploy.sh stop     # stop containers
```

## Switching stacks

```bash
./switch-stack.sh 2              # Plivo + Sarvam
./switch-stack.sh Plivo-ElevenLabs # by branch name
```

Then edit `canam-assistant/.env` and run `./deploy.sh restart`.

---

## Project structure

```
Paras/
├── canam-assistant/
│   ├── main.py                    # FastAPI entrypoint
│   ├── handleAudioCalls/          # Webhooks, WebSocket, voice agents
│   │   ├── call_routes.py         # Plivo/Twilio routes, make-call, reports
│   │   ├── websocket_routes.py    # Media stream sessions
│   │   ├── sarvam_voice_agent.py  # Sarvam STT/LLM/TTS pipeline
│   │   └── plivo_audio_interface.py
│   ├── common/                    # Config, telephony, post-call export
│   ├── prompts/monica_cold_call.txt
│   ├── stacks/                    # Per-branch .env.example files
│   ├── docker-compose.yml
│   └── .env                       # Your local credentials (not committed)
├── assistantFunctions-main/       # GCP Cloud Functions (separate deploy)
├── call-recordings/               # Post-call JSON + MP3 (gitignored)
├── deploy.sh
├── switch-stack.sh
└── analysis.md                    # Detailed architecture notes
```

---

## Key API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/plivo/setup` | Plivo callback URL helper |
| POST | `/make-call-direct` | Place one outbound call immediately |
| POST | `/make-call` | Queue a call (Firestore) |
| POST | `/create-scheduled-task` | Run batch call processor |
| GET | `/call/report/{internal_id}` | Post-call Q&A + recording |
| GET | `/call/reports` | List recent call reports |
| WS | `/ws/media-stream/{phone}/{internal_id}` | Bidirectional audio stream |

Full list: http://localhost:8080/docs

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Call connects but no voice | Ensure ngrok tunnels **8080**; check `./deploy.sh logs` for `[INIT]` |
| Greeting plays, no follow-up | Sarvam STT must use SDK `transcribe()` (fixed in `sarvam_voice_agent.py`); restart with `./deploy.sh restart` |
| Agent says "asterisk asterisk" | LLM was outputting markdown slot labels; replies are now sanitized before TTS |
| `WEB_SERVER_URL` empty / invalid answer URL | Run `./deploy.sh restart` so ngrok URL is written to `.env` |
| Firestore / BigQuery errors in logs | Replace placeholder `service_account_key.json` or ignore if only testing direct calls |
| `POST_CALL_WEBHOOK_URL` 404 | Optional — leave blank or implement `/call-webhook` |
| TTS fails on speaker name | Use `SARVAM_TTS_SPEAKER=anushka` for `bulbul:v2` |

---

## GCP (optional)

`assistantFunctions-main/` handles cloud-side batch processing and analytics. Deploy separately to GCP Cloud Functions. For Plivo stack changes, see `canam-assistant/stacks/assistantFunctions-plivo-patch.md`.

Local direct calls (`/make-call-direct`) and post-call export to `call-recordings/` work without GCP.

---

## Related repos

Upstream references (original projects):

- https://github.com/philajay/canam-assistant
- https://github.com/philajay/assistantFunctions

---

## Estimated cost (Stack 2, India)

| Component | Approx. |
|-----------|---------|
| Plivo telephony | ~₹0.60/min |
| Sarvam STT + LLM + TTS | ~₹1–3/min |
| **Total** | **~₹2–4/min** (vs ~₹12–15/min for Twilio + ElevenLabs) |
