"""Runtime stack selection — overrides .env without container restart."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from common.config import STACK_NAME, TELEPHONY_PROVIDER, VOICE_AI_PROVIDER

ACTIVE_STACK_FILE = Path("uploads/active_stack.json")

STACK_PRESETS: list[dict[str, Any]] = [
    {
        "id": "elevenlabs-twilio",
        "name": "ElevenLabs + Twilio",
        "telephony": "twilio",
        "voice_ai": "elevenlabs",
        "status": "integrated",
        "description": "ElevenLabs conversational agent over Twilio PSTN",
    },
    {
        "id": "plivo-sarvam",
        "name": "Plivo + Sarvam",
        "telephony": "plivo",
        "voice_ai": "sarvam",
        "status": "integrated",
        "description": "Sarvam STT/LLM/TTS over Plivo — lower cost for India",
    },
    {
        "id": "plivo-elevenlabs",
        "name": "Plivo + ElevenLabs",
        "telephony": "plivo",
        "voice_ai": "elevenlabs",
        "status": "integrated",
        "description": "ElevenLabs agent with Plivo telephony",
    },
    {
        "id": "frejun-teler",
        "name": "FreJun Teler",
        "telephony": "frejun",
        "voice_ai": "frejun",
        "status": "stub",
        "description": "Full FreJun stack — not implemented yet",
    },
    {
        "id": "smallest-trikon",
        "name": "Smallest.ai + Trikon",
        "telephony": "smallest",
        "voice_ai": "smallest",
        "status": "stub",
        "description": "Smallest.ai voice stack — not implemented yet",
    },
    {
        "id": "exotel-sarvam",
        "name": "Exotel + Sarvam",
        "telephony": "exotel",
        "voice_ai": "sarvam",
        "status": "stub",
        "description": "Exotel telephony with Sarvam voice — not implemented yet",
    },
]

_runtime_override: Optional[dict[str, str]] = None


def _load_persisted_stack() -> Optional[dict[str, str]]:
    if not ACTIVE_STACK_FILE.exists():
        return None
    try:
        data = json.loads(ACTIVE_STACK_FILE.read_text(encoding="utf-8"))
        if data.get("telephony") and data.get("voice_ai"):
            return data
    except Exception:
        return None
    return None


def _ensure_loaded() -> None:
    global _runtime_override
    if _runtime_override is None:
        _runtime_override = _load_persisted_stack()


def get_stack_name() -> str:
    _ensure_loaded()
    if _runtime_override and _runtime_override.get("stack_name"):
        return _runtime_override["stack_name"]
    return STACK_NAME


def get_telephony_provider() -> str:
    _ensure_loaded()
    if _runtime_override and _runtime_override.get("telephony"):
        return _runtime_override["telephony"]
    return TELEPHONY_PROVIDER


def get_voice_ai_provider() -> str:
    _ensure_loaded()
    if _runtime_override and _runtime_override.get("voice_ai"):
        return _runtime_override["voice_ai"]
    return VOICE_AI_PROVIDER


def get_active_stack() -> dict[str, str]:
    telephony = get_telephony_provider()
    voice_ai = get_voice_ai_provider()
    stack_name = get_stack_name()
    preset = find_preset(telephony, voice_ai)
    return {
        "stack_id": preset["id"] if preset else f"{telephony}-{voice_ai}",
        "stack_name": stack_name,
        "telephony": telephony,
        "voice_ai": voice_ai,
        "source": "runtime" if _runtime_override else "env",
    }


def find_preset(telephony: str, voice_ai: str) -> Optional[dict[str, Any]]:
    for preset in STACK_PRESETS:
        if preset["telephony"] == telephony and preset["voice_ai"] == voice_ai:
            return preset
    return None


def find_preset_by_id(stack_id: str) -> Optional[dict[str, Any]]:
    for preset in STACK_PRESETS:
        if preset["id"] == stack_id:
            return preset
    return None


def set_active_stack(stack_id: str) -> dict[str, Any]:
    global _runtime_override
    preset = find_preset_by_id(stack_id)
    if not preset:
        return {"error": f"Unknown stack: {stack_id}"}
    if preset["status"] == "stub":
        return {"error": f"Stack '{preset['name']}' is not implemented yet"}

    payload = {
        "stack_id": preset["id"],
        "stack_name": preset["name"],
        "telephony": preset["telephony"],
        "voice_ai": preset["voice_ai"],
    }
    ACTIVE_STACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_STACK_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _runtime_override = payload
    return {
        "message": f"Switched to {preset['name']}",
        "restart_required": False,
        **payload,
    }


def list_stack_presets() -> list[dict[str, Any]]:
    active = get_active_stack()
    results = []
    for preset in STACK_PRESETS:
        item = dict(preset)
        item["active"] = preset["id"] == active.get("stack_id")
        results.append(item)
    return results
