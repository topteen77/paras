#!/usr/bin/env bash
# Switch provider stack branch and copy matching .env template
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
STACK="${1:-}"

usage() {
  echo "Usage: $0 <stack-number|branch-name>"
  echo ""
  echo "Stacks:"
  echo "  1 | ElevenLabs-Twilio     Twilio + ElevenLabs"
  echo "  2 | Plivo-Sarvam          Plivo + Sarvam (custom)"
  echo "  3 | FreJun-Teler          FreJun Teler + Sarvam"
  echo "  4 | Plivo-ElevenLabs      Plivo + ElevenLabs"
  echo "  5 | Smallest-ai-Trikon    India SaaS (stub)"
  echo "  6 | Exotel-Sarvam         Exotel + Sarvam (stub)"
  echo "  7 | Plivo-Gemini          Plivo + Gemini Live"
  exit 1
}

case "${STACK}" in
  1|ElevenLabs-Twilio)     BRANCH="ElevenLabs-Twilio";     ENV="stacks/1-ElevenLabs-Twilio.env.example" ;;
  2|Plivo-Sarvam)         BRANCH="Plivo-Sarvam";         ENV="stacks/2-Plivo-Sarvam.env.example" ;;
  3|FreJun-Teler)         BRANCH="Plivo-Sarvam";         ENV="stacks/3-FreJun-Teler.env.example" ;;
  4|Plivo-ElevenLabs)     BRANCH="Plivo-ElevenLabs";     ENV="stacks/4-Plivo-ElevenLabs.env.example" ;;
  5|Smallest-ai-Trikon)   BRANCH="Smallest-ai-Trikon";   ENV="stacks/5-Smallest-ai-Trikon.env.example" ;;
  6|Exotel-Sarvam)        BRANCH="Exotel-Sarvam";        ENV="stacks/6-Exotel-Sarvam.env.example" ;;
  7|Plivo-Gemini)        BRANCH="Plivo-Sarvam";         ENV="stacks/7-Plivo-Gemini.env.example" ;;
  *) usage ;;
esac

cd "${ROOT}"
git checkout "${BRANCH}"
cp "canam-assistant/${ENV}" "canam-assistant/.env"
echo ""
echo "Switched to branch: ${BRANCH}"
echo "Copied: canam-assistant/${ENV} → canam-assistant/.env"
echo ""
echo "Next steps:"
echo "  1. Edit canam-assistant/.env with your API keys"
echo "  2. Run: ./deploy.sh restart"
echo "  3. Test: curl http://localhost:8080/health"
