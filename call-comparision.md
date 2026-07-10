# Call Stack Comparison — India Outbound Cold Calls

Indicative comparison for **Monica cold-call** workflow (Canam Consultants).  
Assumes **~3-minute answered call**, **India mobile outbound**, **Stages 1–3** (local Docker + ngrok + post-call export).

**Last updated:** July 2026 · Rates are estimates — confirm with vendor dashboards before budgeting.

---

## Stacks compared

| # | Stack | Telephony | Voice AI | Repo status |
|---|--------|-----------|----------|-------------|
| **2** | Plivo + Sarvam | Plivo PSTN | Sarvam STT + LLM + TTS | **Integrated** |
| **3** | FreJun Teler + Sarvam | FreJun Teler | Sarvam STT + LLM + TTS | **Integrated** |
| **7** | Plivo + Gemini | Plivo PSTN | Gemini Live (`gemini-2.0-flash-live-001`) | **Integrated** |

Switch in dashboard (**Integrations** → Switch stack) or:

```bash
./switch-stack.sh 2   # Plivo-Sarvam
./switch-stack.sh 3   # FreJun-Teler (not runnable yet)
./switch-stack.sh 7   # Plivo-Gemini
```

---

## Per-minute cost (India outbound)

| Stack | Telephony / min | Voice AI / min | **Total / min** | vs ElevenLabs+Twilio |
|-------|-----------------|----------------|-----------------|----------------------|
| **2 Plivo-Sarvam** | ₹0.40–0.60 | ₹1–3 | **₹2–4** | ~75% cheaper |
| **3 FreJun-Teler** | ₹0.30–0.50 | ₹0.50–1.50* | **₹0.80–2** | ~85–95% cheaper |
| **7 Plivo-Gemini** | ₹0.40–0.60 | ₹0.50–1.50** | **₹1.5–2.5** | ~80–85% cheaper |
| *(baseline)* ElevenLabs+Twilio | ₹1.0–1.5 | ₹11–13 | **₹12–15** | — |

\* Stack 3 voice cost depends on which AI you attach (Sarvam ~₹1–3/min, Gemini Live ~₹0.50–1.50/min effective).  
\** Gemini Live bills by **tokens + turn count**, not flat per-minute — see per-call table below.

**Plivo billing:** 60/60 increment (2 min 20 sec → billed as 3 min).  
**FreJun Teler:** Per-minute PSTN; get a formal quote at [frejun.ai](https://frejun.ai).

---

## Per-call cost (~3 min Monica cold call)

Typical call: greeting → country → study level → timeline → location → callback → goodbye (~15–20 turns).

| Stack | Plivo / Teler | Voice AI | **Total / call** | Notes |
|-------|---------------|----------|------------------|-------|
| **2 Plivo-Sarvam** | ₹1.20–1.80 | ₹3–9 | **₹6–12** | Most predictable billing |
| **3 FreJun + Sarvam** | ₹0.90–1.50 | ₹3–9 | **₹4–11** | Lowest PSTN if quote holds |
| **3 FreJun + Gemini** | ₹0.90–1.50 | ₹35–70 | **₹36–72** | Teler cheap; Gemini token compounding |
| **7 Plivo-Gemini** | ₹1.20–1.80 | ₹35–70 | **₹45–65** | Same voice cost as FreJun+Gemini |

### Example: 1,000 calls / month (3 min avg = 3,000 minutes)

| Stack | Call charges only | With GCP infra (Stages 4–5) |
|-------|-------------------|-----------------------------|
| **2 Plivo-Sarvam** | **₹20,000–40,000** | +₹2,000–15,000 |
| **3 FreJun-Teler** | **₹5,000–20,000** | +₹2,000–15,000 |
| **7 Plivo-Gemini** | **₹15,000–25,000*** | +₹2,000–15,000 |

\* Monthly Gemini line assumes moderate token use; heavy turn counts can push higher.

---

## Feature comparison

| Criteria | 2 Plivo-Sarvam | 3 FreJun-Teler | 7 Plivo-Gemini |
|----------|----------------|----------------|----------------|
| **Implementation** | Done | Scaffold only | Done |
| **Dashboard stack switch** | Yes | Yes (when built) | Yes |
| **Post-call Q&A + MP3** | Yes | Planned | Yes |
| **`/make-call-direct` test** | Yes | Not yet | Yes |
| **Hindi / Hinglish** | Strong (Sarvam India models) | Depends on voice AI | Good (en-IN) |
| **Voice naturalness** | Good (bulbul TTS) | Depends on voice AI | Very good (native audio) |
| **Latency** | Moderate (STT→LLM→TTS pipeline) | Low (Teler sub-50ms transport) | Low (single Live session) |
| **Barge-in / interrupt** | Yes | Yes (WebSocket) | Yes (Gemini VAD) |
| **Cost predictability** | High | Medium (quote + AI choice) | Low–medium (token + turns) |
| **India PSTN cost** | Medium | **Lowest** | Medium |
| **Vendor lock-in** | Low (swap STT/LLM/TTS) | Low (model-agnostic) | Medium (Google) |
| **Recording** | Plivo (free) | Teler `record=True` | Plivo (free) |

---

## Architecture

### Stack 2 — Plivo + Sarvam (current default)

```
Plivo outbound → XML <Stream> → WebSocket
  → PlivoAudioInterface (mulaw 8 kHz)
  → SarvamVoiceAgent
       ├── STT WebSocket (saaras:v3)
       ├── Chat API (sarvam-30b)
       └── TTS REST (bulbul:v2)
  → Hangup → call-recordings/ (JSON + MP3)
```

**Env:** `TELEPHONY_PROVIDER=plivo` · `VOICE_AI_PROVIDER=sarvam`

### Stack 7 — Plivo + Gemini Live

```
Plivo outbound → XML <Stream> → WebSocket
  → PlivoAudioInterface (unchanged)
  → GeminiVoiceAgent
       └── Gemini Live API (native audio in/out)
            8 kHz mulaw ↔ 16/24 kHz PCM conversion
  → Hangup → call-recordings/ (JSON + MP3)
```

**Env:** `TELEPHONY_PROVIDER=plivo` · `VOICE_AI_PROVIDER=gemini` · `GEMINI_API_KEY`

### Stack 3 — FreJun Teler (planned)

FreJun Teler is **telephony + real-time audio transport only** — not a bundled LLM. Recommended build: **Teler + Sarvam** (cheapest) or **Teler + Gemini**.

```
Teler outbound → POST /teler/flow → CallFlow.stream(WebSocket)
  → Teler media (L16 PCM 8 kHz)
  → [Your voice agent — Sarvam or Gemini]
  → Status webhook + recording → call-recordings/
```

**Planned files:** `frejun_audio_interface.py`, `teler_routes.py`, `common/telephony.py` FreJun branch  
**Docs:** [frejun.ai](https://frejun.ai) · [teler PyPI](https://pypi.org/project/teler/) · `canam-assistant/stacks/STACK-3-FreJun-Teler.md` (on branch)

---

## Credentials required

| Key | Stack 2 | Stack 3 | Stack 7 |
|-----|---------|---------|---------|
| `PLIVO_AUTH_ID` / `TOKEN` / `NUMBER` | Required | — | Required |
| `SARVAM_API_KEY` | Required | If using Sarvam voice | — |
| `GEMINI_API_KEY` | — | If using Gemini voice | Required |
| `TELER_API_KEY` + India number | — | Required | — |
| `NGROK_AUTHTOKEN` + public URL | Required | Required | Required |

---

## When to choose which stack

| Choose | If you need… |
|--------|----------------|
| **2 Plivo-Sarvam** | **Best balance today** — integrated, predictable ₹6–12/call, strong India voice, already in production testing |
| **7 Plivo-Gemini** | More natural conversational audio; OK with token-based billing; already have `GEMINI_API_KEY`; same Plivo setup as Stack 2 |
| **3 FreJun-Teler** | **Lowest telephony cost** at scale; willing to implement scaffold; model-agnostic; sub-50ms India WebSocket — pair with Sarvam for cheapest full stack |

### Recommended test order

1. **Stack 2** — validate call quality, Q&A export, cost baseline  
2. **Stack 7** — A/B voice quality vs Sarvam on same Plivo number  
3. **Stack 3** — after Stack 2 is stable; implement Teler telephony, reuse Sarvam or Gemini agent  

---

## Quick test commands (Stacks 2 & 7)

```bash
./deploy.sh restart
curl http://localhost:8080/health

# Direct outbound (bypasses scheduler)
curl -X POST http://localhost:8080/make-call-direct \
  -H 'Content-Type: application/json' \
  -d '{"to": "+91XXXXXXXXXX"}'

# Post-call report
ls call-recordings/
curl http://localhost:8080/call/reports
```

**Switch via UI:** Dashboard → **Integrations** → **Plivo + Sarvam** or **Plivo + Gemini** → updates `VOICE_AI_PROVIDER` and `STACK_NAME` immediately.

---

## Summary matrix

| | Stack 2 | Stack 3 | Stack 7 |
|---|---------|---------|---------|
| **Cost rank (cheapest first)** | 2nd | **1st** (potential) | 3rd |
| **Ready to call today** | Yes | **Yes** | Yes |
| **Voice quality** | Good | TBD | Very good |
| **Best for** | India dev + prod pilot | High-volume cost optimization | Natural AI voice experiments |
| **Est. 3 min call** | **₹6–12** | **₹4–11** (w/ Sarvam) | **₹45–65** |
| **Est. 10k min/month** | **₹20–40K** | **₹5–20K** | **₹15–25K** |

---

## References

- Stack guides: `canam-assistant/stacks/README.md`
- Env templates: `canam-assistant/stacks/2-Plivo-Sarvam.env.example`, `3-FreJun-Teler.env.example`, `7-Plivo-Gemini.env.example`
- Plivo India pricing: https://www.plivo.com/voice/pricing/in/
- Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing
- FreJun Teler: https://frejun.ai
