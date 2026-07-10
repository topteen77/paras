"""Provider connectivity checks and credit/usage summaries."""
from __future__ import annotations

import json
from typing import Any, Optional

import requests

from common.config import (
    ELEVENLABS_API_KEY,
    ELEVEN_LABS_COLD_CALLING_AGENT_ID,
    GEMINI_API_KEY,
    GEMINI_LIVE_MODEL,
    NGROK_URL,
    PLIVO_AUTH_ID,
    PLIVO_AUTH_TOKEN,
    PLIVO_PHONE_NUMBER,
    PROJECT_ID,
    SARVAM_API_KEY,
    SARVAM_CHAT_MODEL,
    TELER_API_KEY,
    TELER_PHONE_NUMBER,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    WEB_SERVER_URL,
)
from common.dashboard import load_all_reports
from common.runtime_stack import get_active_stack, get_telephony_provider, get_voice_ai_provider, list_stack_presets


def _status_result(
    provider_id: str,
    name: str,
    category: str,
    configured: bool,
    working: Optional[bool] = None,
    message: str = "",
    credits: Optional[dict[str, Any]] = None,
    dashboard_url: str = "",
    active: bool = False,
) -> dict[str, Any]:
    if not configured:
        connectivity = "not_configured"
    elif working is True:
        connectivity = "working"
    elif working is False:
        connectivity = "not_working"
    else:
        connectivity = "unknown"

    return {
        "id": provider_id,
        "name": name,
        "category": category,
        "configured": configured,
        "working": working,
        "connectivity": connectivity,
        "message": message,
        "credits": credits or {},
        "dashboard_url": dashboard_url,
        "active": active,
    }


def _credit_block(
    total: Optional[float] = None,
    used: Optional[float] = None,
    balance: Optional[float] = None,
    unit: str = "",
    label: str = "Credits",
    note: str = "",
) -> dict[str, Any]:
    return {
        "label": label,
        "total": total,
        "used": used,
        "balance": balance,
        "unit": unit,
        "note": note,
    }


def _sum_plivo_usage_from_reports() -> float:
    total = 0.0
    for report in load_all_reports():
        hangup = report.get("hangup") or {}
        cost = hangup.get("TotalCost")
        if cost is not None:
            try:
                total += float(cost)
            except (TypeError, ValueError):
                pass
    return round(total, 4)


def check_plivo() -> dict[str, Any]:
    configured = bool(PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN)
    active = get_telephony_provider() == "plivo"
    if not configured:
        return _status_result("plivo", "Plivo", "telephony", False, dashboard_url="https://console.plivo.com", active=active)

    try:
        response = requests.get(
            f"https://api.plivo.com/v1/Account/{PLIVO_AUTH_ID}/",
            auth=(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN),
            timeout=12,
        )
        if response.status_code != 200:
            return _status_result(
                "plivo",
                "Plivo",
                "telephony",
                True,
                False,
                f"API error {response.status_code}",
                dashboard_url="https://console.plivo.com",
                active=active,
            )

        data = response.json()
        balance = float(data.get("cash_credits") or 0)
        used_local = _sum_plivo_usage_from_reports()
        return _status_result(
            "plivo",
            "Plivo",
            "telephony",
            True,
            True,
            f"Account: {data.get('name', 'OK')} · {PLIVO_PHONE_NUMBER or 'no number set'}",
            credits=_credit_block(
                total=round(balance + used_local, 4) if used_local else None,
                used=used_local if used_local else None,
                balance=balance,
                unit="USD",
                label="Account balance",
                note="Used is summed from local call reports; total is estimated when usage exists.",
            ),
            dashboard_url="https://console.plivo.com",
            active=active,
        )
    except Exception as exc:
        return _status_result(
            "plivo", "Plivo", "telephony", True, False, str(exc), dashboard_url="https://console.plivo.com", active=active
        )


def check_twilio() -> dict[str, Any]:
    configured = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)
    active = get_telephony_provider() == "twilio"
    if not configured:
        return _status_result("twilio", "Twilio", "telephony", False, dashboard_url="https://console.twilio.com", active=active)

    try:
        response = requests.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Balance.json",
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            timeout=12,
        )
        if response.status_code != 200:
            return _status_result(
                "twilio",
                "Twilio",
                "telephony",
                True,
                False,
                f"API error {response.status_code}",
                dashboard_url="https://console.twilio.com",
                active=active,
            )

        data = response.json()
        balance = float(data.get("balance", 0))
        currency = data.get("currency", "USD")
        return _status_result(
            "twilio",
            "Twilio",
            "telephony",
            True,
            True,
            f"Balance available · {TWILIO_PHONE_NUMBER or 'no number set'}",
            credits=_credit_block(balance=balance, unit=currency.upper(), label="Account balance"),
            dashboard_url="https://console.twilio.com",
            active=active,
        )
    except Exception as exc:
        return _status_result(
            "twilio", "Twilio", "telephony", True, False, str(exc), dashboard_url="https://console.twilio.com", active=active
        )


def check_frejun() -> dict[str, Any]:
    configured = bool(TELER_API_KEY and TELER_PHONE_NUMBER)
    active = get_telephony_provider() == "frejun"
    if not configured:
        return _status_result(
            "frejun",
            "FreJun Teler",
            "telephony",
            False,
            dashboard_url="https://frejun.ai",
            active=active,
        )

    try:
        response = requests.get(
            "https://api.frejun.ai/api/v1/",
            headers={"Authorization": f"Bearer {TELER_API_KEY}"},
            timeout=12,
        )
        working = response.status_code in (200, 404, 405)
        return _status_result(
            "frejun",
            "FreJun Teler",
            "telephony",
            True,
            working,
            f"API reachable · number {TELER_PHONE_NUMBER}",
            credits=_credit_block(
                label="Usage",
                note="Per-minute PSTN — confirm quote at frejun.ai",
            ),
            dashboard_url="https://frejun.ai",
            active=active,
        )
    except Exception as exc:
        return _status_result(
            "frejun",
            "FreJun Teler",
            "telephony",
            True,
            False,
            str(exc)[:200],
            dashboard_url="https://frejun.ai",
            active=active,
        )


def check_elevenlabs() -> dict[str, Any]:
    configured = bool(ELEVENLABS_API_KEY)
    active = get_voice_ai_provider() == "elevenlabs"
    if not configured:
        return _status_result(
            "elevenlabs", "ElevenLabs", "voice_ai", False, dashboard_url="https://elevenlabs.io/app", active=active
        )

    try:
        response = requests.get(
            "https://api.elevenlabs.io/v1/user/subscription",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            timeout=12,
        )
        if response.status_code != 200:
            return _status_result(
                "elevenlabs",
                "ElevenLabs",
                "voice_ai",
                True,
                False,
                f"API error {response.status_code}",
                dashboard_url="https://elevenlabs.io/app",
                active=active,
            )

        data = response.json()
        used = int(data.get("character_count") or 0)
        total = int(data.get("character_limit") or 0)
        balance = max(total - used, 0)
        tier = data.get("tier", "")
        agent_note = ""
        if active and not ELEVEN_LABS_COLD_CALLING_AGENT_ID:
            agent_note = " · Agent ID not set"

        return _status_result(
            "elevenlabs",
            "ElevenLabs",
            "voice_ai",
            True,
            True,
            f"Plan: {tier}{agent_note}",
            credits=_credit_block(
                total=total,
                used=used,
                balance=balance,
                unit="characters",
                label="Character quota",
            ),
            dashboard_url="https://elevenlabs.io/app/subscription",
            active=active,
        )
    except Exception as exc:
        return _status_result(
            "elevenlabs",
            "ElevenLabs",
            "voice_ai",
            True,
            False,
            str(exc),
            dashboard_url="https://elevenlabs.io/app",
            active=active,
        )


def check_sarvam() -> dict[str, Any]:
    configured = bool(SARVAM_API_KEY)
    active = get_voice_ai_provider() == "sarvam"
    if not configured:
        return _status_result(
            "sarvam", "Sarvam AI", "voice_ai", False, dashboard_url="https://dashboard.sarvam.ai/usage", active=active
        )

    try:
        from sarvamai import SarvamAI

        client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
        client.chat.completions(
            messages=[{"role": "user", "content": "ping"}],
            model=SARVAM_CHAT_MODEL,
            max_tokens=1,
        )
        return _status_result(
            "sarvam",
            "Sarvam AI",
            "voice_ai",
            True,
            True,
            f"API reachable · model {SARVAM_CHAT_MODEL}",
            credits=_credit_block(
                note="Credit balance is not exposed via API — open Sarvam dashboard for total/used/balance.",
            ),
            dashboard_url="https://dashboard.sarvam.ai/usage",
            active=active,
        )
    except Exception as exc:
        return _status_result(
            "sarvam",
            "Sarvam AI",
            "voice_ai",
            True,
            False,
            str(exc),
            dashboard_url="https://dashboard.sarvam.ai/usage",
            active=active,
        )


def check_gemini() -> dict[str, Any]:
    configured = bool(GEMINI_API_KEY)
    active = get_voice_ai_provider() == "gemini"
    if not configured:
        return _status_result(
            "gemini",
            "Gemini Live",
            "voice_ai",
            False,
            dashboard_url="https://aistudio.google.com/apikey",
            active=active,
        )

    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        client.models.get(model=GEMINI_LIVE_MODEL)
        return _status_result(
            "gemini",
            "Gemini Live",
            "voice_ai",
            True,
            True,
            f"API reachable · model {GEMINI_LIVE_MODEL}",
            credits=_credit_block(
                label="Usage",
                note="Token-based billing — see Google AI Studio",
            ),
            dashboard_url="https://aistudio.google.com/apikey",
            active=active,
        )
    except Exception as exc:
        return _status_result(
            "gemini",
            "Gemini Live",
            "voice_ai",
            True,
            False,
            str(exc)[:200],
            dashboard_url="https://aistudio.google.com/apikey",
            active=active,
        )


def check_gcp() -> dict[str, Any]:
    configured = bool(PROJECT_ID and PROJECT_ID not in ("your-gcp-project-id", "CHANGE_ME"))
    if not configured:
        return _status_result(
            "gcp",
            "Google Cloud",
            "infrastructure",
            False,
            dashboard_url="https://console.cloud.google.com",
        )

    try:
        from google.cloud import firestore

        db = firestore.Client()
        list(db.collection("conversation-history").limit(1).stream())
        return _status_result(
            "gcp",
            "Google Cloud",
            "infrastructure",
            True,
            True,
            f"Firestore reachable · project {PROJECT_ID}",
            dashboard_url="https://console.cloud.google.com/firestore",
        )
    except Exception as exc:
        return _status_result(
            "gcp",
            "Google Cloud",
            "infrastructure",
            True,
            False,
            str(exc),
            dashboard_url="https://console.cloud.google.com",
        )


def check_ngrok() -> dict[str, Any]:
    configured = bool(NGROK_URL)
    if not configured:
        return _status_result("ngrok", "ngrok", "infrastructure", False, dashboard_url="https://dashboard.ngrok.com")

    tunnel_ok = False
    public_url = NGROK_URL
    message = WEB_SERVER_URL

    for api_base in ("http://ngrok:4040", "http://localhost:4040", "http://127.0.0.1:4040"):
        try:
            response = requests.get(f"{api_base}/api/tunnels", timeout=4)
            if response.status_code != 200:
                continue
            tunnels = response.json().get("tunnels", [])
            https_tunnels = [t for t in tunnels if t.get("public_url", "").startswith("https://")]
            if https_tunnels:
                tunnel_ok = True
                public_url = https_tunnels[0]["public_url"]
                message = f"Tunnel active → {public_url}"
                break
        except Exception:
            continue

    if not tunnel_ok:
        return _status_result(
            "ngrok",
            "ngrok",
            "infrastructure",
            True,
            False,
            f"Configured URL {NGROK_URL} but tunnel API not reachable",
            dashboard_url="http://localhost:4040",
        )

    return _status_result(
        "ngrok",
        "ngrok",
        "infrastructure",
        True,
        True,
        message,
        dashboard_url="http://localhost:4040",
    )


def check_stack_preset_requirements(preset: dict[str, Any]) -> dict[str, Any]:
    providers = get_all_providers()
    by_id = {p["id"]: p for p in providers}
    telephony = by_id.get(preset["telephony"])
    voice = by_id.get(preset["voice_ai"])
    missing = []
    not_working = []

    for provider in (telephony, voice):
        if not provider:
            continue
        if not provider["configured"]:
            missing.append(provider["name"])
        elif provider["working"] is False:
            not_working.append(provider["name"])

    ready = preset["status"] == "integrated" and not missing and not not_working
    return {
        "ready": ready,
        "missing_credentials": missing,
        "not_working": not_working,
    }


def get_all_providers() -> list[dict[str, Any]]:
    return [
        check_plivo(),
        check_frejun(),
        check_twilio(),
        check_elevenlabs(),
        check_sarvam(),
        check_gemini(),
        check_gcp(),
        check_ngrok(),
    ]


def get_integrations_summary() -> dict[str, Any]:
    providers = get_all_providers()
    active = get_active_stack()
    stacks = []
    for preset in list_stack_presets():
        requirements = check_stack_preset_requirements(preset)
        stacks.append({**preset, **requirements})

    working_count = sum(1 for p in providers if p["connectivity"] == "working")
    configured_count = sum(1 for p in providers if p["configured"])

    return {
        "active_stack": active,
        "providers": providers,
        "stacks": stacks,
        "summary": {
            "providers_configured": configured_count,
            "providers_working": working_count,
            "providers_total": len(providers),
        },
    }
