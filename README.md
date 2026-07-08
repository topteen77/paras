# Paras — Canam AI Voice Calling Platform

Study-abroad lead-generation platform with AI voice agents, outbound calling, and post-call processing.

## Provider stacks (branches)

| Branch | Telephony | Voice AI | Status |
|--------|-----------|----------|--------|
| `main` / `ElevenLabs-Twilio` | Twilio | ElevenLabs | Integrated |
| `Plivo-Sarvam` | Plivo | Sarvam AI (custom) | Integrated |
| `Plivo-ElevenLabs` | Plivo | ElevenLabs | Config ready |
| `FreJun-Teler-full-stack` | FreJun Teler | Bundled | Scaffold |
| `Smallest-ai-Trikon` | Trikon | Smallest.ai | Scaffold |
| `Exotel-Sarvam` | Exotel | Sarvam AI | Scaffold |

## Quick start (Stack 1 — ElevenLabs + Twilio)

```bash
cp canam-assistant/.env.example canam-assistant/.env
# Edit .env with your credentials
./deploy.sh
```

API: http://localhost:8080/docs

## Project structure

```
Paras/
├── canam-assistant/          # FastAPI voice call server (Cloud Run / Docker)
├── assistantFunctions-main/  # GCP Cloud Functions (post-call processing)
├── deploy.sh                 # Local Docker setup
└── analysis.md               # Architecture documentation
```

## Switching stacks

```bash
git checkout Plivo-Sarvam
cp canam-assistant/.env.example canam-assistant/.env
./deploy.sh
```

See `canam-assistant/.env.example` on each branch for required credentials.
