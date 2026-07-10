# Stack 3: FreJun Teler + Sarvam

FreJun **Teler** provides India PSTN telephony and real-time WebSocket audio transport.  
**Sarvam** provides STT, LLM, and TTS (same voice pipeline as Stack 2).

> Teler is **not** a voice AI provider — it replaces Plivo for telephony only.

---

## Prerequisites

| Item | Source |
|------|--------|
| Teler API key | [frejun.ai](https://frejun.ai) → developer dashboard |
| India virtual number | FreJun Teler console |
| Sarvam API key | [dashboard.sarvam.ai](https://dashboard.sarvam.ai) |
| ngrok public URL | [dashboard.ngrok.com](https://dashboard.ngrok.com) |

---

## Quick start

```bash
./switch-stack.sh 3
# Edit canam-assistant/.env — TELER_API_KEY, TELER_PHONE_NUMBER, SARVAM_API_KEY
./deploy.sh restart
curl http://localhost:8080/health
curl http://localhost:8080/teler/setup
```

Or switch in dashboard: **Integrations** → **FreJun Teler + Sarvam**.

---

## Environment variables

```bash
TELEPHONY_PROVIDER=frejun
VOICE_AI_PROVIDER=sarvam
TELER_API_KEY=...
TELER_PHONE_NUMBER=+91...
SARVAM_API_KEY=...
WEB_SERVER_URL=https://your-ngrok-subdomain.ngrok-free.app
```

Aliases: `FREJUN_API_KEY`, `FREJUN_PHONE_NUMBER`.

---

## Teler dashboard setup

Open `GET /teler/setup` after ngrok is running. You will see:

| Endpoint | Purpose |
|----------|---------|
| `POST /teler/flow/{internal_id}` | Returns `CallFlow.stream` JSON when call connects |
| `POST /teler/status/{internal_id}` | Call lifecycle + hangup metadata |
| `POST /teler/webhook` | Generic fallback receiver |
| `WebSocket /ws/media-stream/{to}/{internal_id}` | Bidirectional L16 PCM 8 kHz audio |

**Outbound** (`/make-call-direct`): `flow_url` and `status_callback_url` are set automatically in the Teler API call — no manual dashboard config needed for testing.

**Inbound** (optional): In Teler Voice App settings, point the flow URL to your ngrok base + `/teler/flow/{internal_id}`.

---

## Architecture

```
Teler API calls.create(flow_url, record=True)
  → PSTN outbound to customer
  → POST /teler/flow/{internal_id}
  → Returns { action: stream, ws_url: wss://.../ws/media-stream/... }
  → WebSocket audio (PCM16 8 kHz)
  → TelerAudioInterface
  → SarvamVoiceAgent (STT → LLM → TTS)
  → POST /teler/status/{internal_id} on hangup
  → call-recordings/ JSON + transcript + Q&A
```

### Audio format

| Direction | Format |
|-----------|--------|
| Teler → app | JSON `{"type":"audio","data":{"audio_b64":"..."}}` — PCM16 mono 8 kHz |
| App → Teler | JSON `{"type":"audio","audio_b64":"...","chunk_id":N}` |
| Barge-in | `{"type":"clear"}` |

Plivo uses mulaw; Teler uses raw PCM — handled automatically by `TelerAudioInterface` and `use_mulaw=False`.

---

## Test outbound call (Stage 2)

```bash
curl -X POST http://localhost:8080/make-call-direct \
  -H 'Content-Type: application/json' \
  -d '{"to": "+91XXXXXXXXXX"}'
```

**Expected logs:**

```
[TELER_CALL] flow_url=https://your-ngrok/teler/flow/...
[TELER_FLOW] internal_id=... call_id=...
[INIT] stack telephony=frejun voice=sarvam ...
[TELER_STREAM] start stream_id=...
[SARVAM_STT] connected ...
```

---

## Post-call export (Stage 3)

```bash
ls ../call-recordings/
curl http://localhost:8080/call/reports
curl http://localhost:8080/call/report/{internal_id}
```

---

## Python SDK reference

This stack uses the official [`teler`](https://pypi.org/project/teler/) package:

```python
from teler import Client, CallFlow

client = Client(api_key=TELER_API_KEY)
call = client.calls.create(
    from_number=TELER_PHONE_NUMBER,
    to_number="+91...",
    flow_url="https://your-ngrok/teler/flow/{internal_id}",
    status_callback_url="https://your-ngrok/teler/status/{internal_id}",
    record=True,
)

# Flow handler returns:
CallFlow.stream(ws_url="wss://your-ngrok/ws/media-stream/...", record=True)
```

---

## Switching voice AI

Default Stack 3 uses **Sarvam**. To experiment with Gemini on Teler telephony, use dashboard stack presets or set:

- `VOICE_AI_PROVIDER=gemini` + `GEMINI_API_KEY` (requires `TELEPHONY_PROVIDER=frejun`)

For production, prefer the dedicated presets in **Integrations**.

---

## Cost (indicative)

| Component | Rate |
|-----------|------|
| Teler PSTN | ₹0.30–0.50/min |
| Sarvam STT+LLM+TTS | ₹1–3/min |
| **Total** | **~₹1.5–3.5/min** |

See root `call-comparision.md` for Stack 2 vs 3 vs 7 comparison.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Teler call failed` | Verify `TELER_API_KEY` and India number on account |
| No audio / greeting | Check ngrok on port 8080; confirm `[TELER_STREAM] start` in logs |
| `WEB_SERVER_URL must be public` | Set `WEB_SERVER_URL` to ngrok HTTPS URL |
| WebSocket closes immediately | Ensure Sarvam key is set when `voice_ai=sarvam` |

---

## Related docs

- [FreJun Teler platform](https://frejun.ai)
- [Teler Python SDK](https://github.com/frejun-tech/teler-py)
- [Voice API India guide](https://frejun.com/voice-api-india/)
- `canam-assistant/stacks/README.md`
- `/call-comparision.md`
