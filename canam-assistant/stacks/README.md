# Provider Stack Branches

Deploy and test each voice stack **one by one** in the order below. Start local with Docker; move to GCP only after a stack passes direct-call and post-call checks.

---

## Preferred deploy stages (all stacks)

| Stage | What you deploy | GCP needed? | Typical cost |
|-------|-----------------|-------------|--------------|
| **1 — Local API** | `./deploy.sh` (Docker + ngrok on port 8080) | No | Free (Docker/ngrok free tier) |
| **2 — Direct call test** | `POST /make-call-direct` to your mobile | No | Stack telephony + voice AI per minute |
| **3 — Post-call export** | Q&A + transcript + MP3 → `call-recordings/` | No | Same as Stage 2 |
| **4 — Batch scheduling** | `/make-call` + `/create-scheduled-task` | Yes (Firestore, Pub/Sub, Tasks) | GCP usage + call minutes |
| **5 — Production** | Cloud Run + `assistantFunctions-main` | Yes | Cloud Run + Functions + call minutes |

**Recommended path:** complete Stages 1–3 on each stack locally before moving to the next stack number. Only enable Stage 4–5 for the stack you choose for production.

### Commands per stage

```bash
# Stage 1 — from repo root
./switch-stack.sh <N>          # e.g. ./switch-stack.sh 2
nano canam-assistant/.env        # add API keys
./deploy.sh
curl http://localhost:8080/health

# Stage 2 — direct outbound (bypasses scheduler)
curl -X POST http://localhost:8080/make-call-direct \
  -H 'Content-Type: application/json' \
  -d '{"to": "+91XXXXXXXXXX"}'

# Stage 3 — verify post-call report
ls call-recordings/
curl http://localhost:8080/call/reports

# Stage 4 — batch (requires GCP service account)
curl -X POST http://localhost:8080/make-call \
  -H 'Content-Type: application/json' \
  -d '{"to": "+91XXXXXXXXXX"}'
curl -X POST http://localhost:8080/create-scheduled-task

# Stage 5 — production (see canam-assistant/instructions.txt)
gcloud run deploy canam-assistant --source canam-assistant/
```

---

## Stack test sequence (your preference)

Test in this order. **Stack 2 is the active local stack** (Plivo + Sarvam, lower India cost).

| Order | Branch | Telephony | Voice AI | Status | Stage reached |
|-------|--------|-----------|----------|--------|---------------|
| 1 | `ElevenLabs-Twilio` | Twilio | ElevenLabs Agents | Integrated (baseline) | Stage 1 |
| 2 | `Plivo-Sarvam` | Plivo | Sarvam STT+LLM+TTS | **Active — testing now** | Stage 1–3 |
| 3 | `FreJun-Teler-full-stack` | FreJun Teler | Sarvam STT+LLM+TTS | **Integrated** | Stage 1–3 |
| 4 | `Plivo-ElevenLabs` | Plivo | ElevenLabs Agents | Config ready | — |
| 5 | `Smallest-ai-Trikon` | Trikon/Smallest | Smallest.ai | Scaffold | — |
| 6 | `Exotel-Sarvam` | Exotel | Sarvam STT+LLM+TTS | Scaffold | — |
| 7 | `Plivo-Gemini` | Plivo | Gemini Live | **Integrated** | Stage 1–3 |

```bash
./switch-stack.sh 1   # ElevenLabs-Twilio
./switch-stack.sh 2   # Plivo-Sarvam  ← current
./switch-stack.sh 3   # FreJun-Teler-full-stack
./switch-stack.sh 7   # Plivo-Gemini
# … and so on
```

---

## Cost comparison (India outbound, per minute)

Indicative rates for a **3-minute cold call**. Actual billing depends on volume, routing, and vendor quotes.

### Per-minute breakdown

| Stack | Telephony | Voice AI | Est. total/min | vs Stack 1 |
|-------|-----------|----------|----------------|------------|
| **1** ElevenLabs-Twilio | ₹1.0–1.5 | ₹11–13 | **₹12–15** | baseline |
| **2** Plivo-Sarvam | ₹0.60 | ₹1–3 | **₹2–4** | **~75% cheaper** |
| **3** FreJun-Teler | ₹0.30–0.50 | bundled | **₹0.50–2** | **~85–95% cheaper** |
| **4** Plivo-ElevenLabs | ₹0.60 | ₹11–13 | **₹12–14** | ~same voice cost, cheaper PSTN |
| **5** Smallest-ai-Trikon | bundled | bundled | **₹6–12** | ~20–50% cheaper |
| **6** Exotel-Sarvam | ₹0.80–1.50 | ₹1–3 | **₹2–5** | **~70–80% cheaper** |
| **7** Plivo-Gemini | ₹0.60 | ₹0.50–1.50 | **₹1.5–2.5** | **~80–85% cheaper** |

### Monthly estimate (10,000 call minutes)

| Stack | Est. monthly (calls only) | Notes |
|-------|---------------------------|-------|
| 1 ElevenLabs-Twilio | **₹1.2–1.5 lakh** | Best dev experience; highest cost |
| 2 Plivo-Sarvam | **₹20,000–40,000** | **Preferred for India dev/test** |
| 3 FreJun-Teler | **₹5,000–20,000** | Lowest PSTN; platform quote required |
| 4 Plivo-ElevenLabs | **₹1.2–1.4 lakh** | Cheaper telephony, same ElevenLabs voice bill |
| 5 Smallest-ai-Trikon | **₹60,000–1.2 lakh** | All-in-one SaaS; fastest to prod |
| 6 Exotel-Sarvam | **₹20,000–50,000** | Strong India compliance + Hindi/Hinglish |
| 7 Plivo-Gemini | **₹15,000–25,000** | Same Plivo PSTN; Gemini Flash Live token billing |

**Infrastructure (Stages 4–5, all stacks):** GCP Firestore, Pub/Sub, Cloud Tasks, BigQuery, Cloud Run — typically **₹2,000–15,000/month** at low volume (often within free tier during testing).

### Why Stack 2 first after baseline

- Stack 1 proves the original pipeline (Twilio + ElevenLabs).
- Stack 2 keeps the same FastAPI architecture but swaps to **India-native, lower-cost** providers.
- You already get Stage 3 locally: transcript, Q&A pairs, and Plivo MP3 in `call-recordings/`.
- Move to Stacks 3–6 only after Stack 2 call quality and cost are acceptable.

---

## Quick start (any stack)

```bash
git checkout <branch-name>
cp stacks/<N>-<name>.env.example .env
# Edit .env with your API keys
./deploy.sh          # from repo root (Paras/deploy.sh)
```

---

## Stack 2: Plivo + Sarvam (active)

```bash
./switch-stack.sh 2
# or: git checkout Plivo-Sarvam && cp stacks/2-Plivo-Sarvam.env.example .env
```

### Required credentials

| Key | Source |
|-----|--------|
| `PLIVO_AUTH_ID` / `PLIVO_AUTH_TOKEN` | [Plivo Console](https://console.plivo.com) |
| `PLIVO_PHONE_NUMBER` | Plivo India DID |
| `SARVAM_API_KEY` | [Sarvam Dashboard](https://dashboard.sarvam.ai) |
| `NGROK_AUTHTOKEN` | [ngrok](https://dashboard.ngrok.com) |
| GCP service account | Firestore / Pub/Sub / Tasks (Stage 4+ only) |

Recommended Sarvam settings:

```
SARVAM_CHAT_MODEL=sarvam-30b
SARVAM_STT_MODEL=saaras:v3
SARVAM_TTS_MODEL=bulbul:v2
SARVAM_TTS_SPEAKER=anushka
SARVAM_SYSTEM_PROMPT_PATH=prompts/monica_cold_call.txt
```

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
| Local files | `call-recordings/{phone}_{timestamp}.json` + `.mp3` |
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

### Test a direct outbound call (Stage 2)

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
  → On hangup: transcript + Q&A + recording → call-recordings/
```

### assistantFunctions (Stage 5)

Update `assistantFunctions-main/main.py` `process_initiated_call` to use Plivo when on this stack.
See `stacks/assistantFunctions-plivo-patch.md`.

### Stack 2 cost summary

| Component | Rate |
|-----------|------|
| Plivo telephony | ~₹0.60/min |
| Sarvam STT + LLM + TTS | ~₹1–3/min |
| **Total** | **~₹2–4/min** (vs ~₹12–15/min for Stack 1) |

---

## Stack 3: FreJun Teler + Sarvam

Lowest India PSTN cost — FreJun **Teler** replaces Plivo; same **Sarvam** voice agent as Stack 2.

```bash
./switch-stack.sh 3
# Edit .env — TELER_API_KEY, TELER_PHONE_NUMBER, SARVAM_API_KEY
./deploy.sh restart
```

Full guide: **`stacks/STACK-3-FreJun-Teler.md`**

### Required credentials

| Key | Source |
|-----|--------|
| `TELER_API_KEY` / `TELER_PHONE_NUMBER` | [frejun.ai](https://frejun.ai) |
| `SARVAM_API_KEY` | [Sarvam Dashboard](https://dashboard.sarvam.ai) |
| `NGROK_AUTHTOKEN` | [ngrok](https://dashboard.ngrok.com) |

### Teler setup URL

```bash
curl http://localhost:8080/teler/setup
```

### Architecture

```
Teler calls.create → POST /teler/flow → WebSocket stream
  → TelerAudioInterface (PCM 8 kHz)
  → SarvamVoiceAgent
  → /teler/status on hangup → call-recordings/
```

### Test

```bash
curl -X POST http://localhost:8080/make-call-direct \
  -H 'Content-Type: application/json' \
  -d '{"to": "+91XXXXXXXXXX"}'
```

---

## Stack 7: Plivo + Gemini Live

Same Plivo telephony as Stack 2; swaps Sarvam for **Gemini Live** native audio (speech-to-speech, token billing).

```bash
./switch-stack.sh 7
# Edit canam-assistant/.env — add GEMINI_API_KEY + existing Plivo keys
./deploy.sh restart
```

### Required credentials

| Key | Source |
|-----|--------|
| `PLIVO_AUTH_ID` / `PLIVO_AUTH_TOKEN` / `PLIVO_PHONE_NUMBER` | [Plivo Console](https://console.plivo.com) |
| `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | [Google AI Studio](https://aistudio.google.com/apikey) |
| `NGROK_AUTHTOKEN` | [ngrok](https://dashboard.ngrok.com) |

Recommended settings:

```
VOICE_AI_PROVIDER=gemini
GEMINI_LIVE_MODEL=gemini-2.0-flash-live-001
GEMINI_LANGUAGE_CODE=en-IN
SARVAM_SYSTEM_PROMPT_PATH=prompts/monica_cold_call.txt
```

Plivo callback URLs are identical to Stack 2 — use `/plivo/setup` and `/make-call-direct`.

### Architecture

```
Plivo outbound call
  → POST /outgoing-call → Plivo XML <Stream>
  → WebSocket /ws/media-stream
  → PlivoAudioInterface (mulaw ↔ PCM, unchanged)
  → GeminiVoiceAgent
       ├── Gemini Live API (native audio in/out)
       ├── 8kHz mulaw → 16kHz PCM → Gemini
       └── 24kHz PCM → 8kHz mulaw → Plivo
  → On hangup: transcript + Q&A + recording → call-recordings/
```

### Test

```bash
curl -X POST http://localhost:8080/make-call-direct \
  -H 'Content-Type: application/json' \
  -d '{"to": "+91XXXXXXXXXX"}'
```

Logs should show `[INIT] stack telephony=plivo voice=gemini` and `[GEMINI_LIVE] connected`.

---

## Stack reference (env templates)

| Stack | Env file |
|-------|----------|
| 1 | `stacks/1-ElevenLabs-Twilio.env.example` |
| 2 | `stacks/2-Plivo-Sarvam.env.example` |
| 3 | `stacks/3-FreJun-Teler.env.example` |
| 4 | `stacks/4-Plivo-ElevenLabs.env.example` |
| 5 | `stacks/5-Smallest-ai-Trikon.env.example` |
| 6 | `stacks/6-Exotel-Sarvam.env.example` |
| 7 | `stacks/7-Plivo-Gemini.env.example` |
