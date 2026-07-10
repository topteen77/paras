"""Runtime Sarvam voice settings — persisted for dashboard + live calls."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from common.config import (
    SARVAM_LANGUAGE_CODE,
    SARVAM_TTS_MODEL,
    SARVAM_TTS_SPEAKER,
)

VOICE_SETTINGS_PATH = Path("uploads/voice_settings.json")

# bulbul:v2 speaker catalog (Sarvam dashboard voices)
BULBUL_V2_SPEAKERS: list[dict[str, str]] = [
    {
        "id": "anushka",
        "name": "Anushka",
        "gender": "female",
        "description": "Warm, friendly Indian English — balanced default for customer support calls.",
    },
    {
        "id": "manisha",
        "name": "Manisha",
        "gender": "female",
        "description": "Soft and natural tone — good for longer conversations and reassurance.",
    },
    {
        "id": "vidya",
        "name": "Vidya",
        "gender": "female",
        "description": "Clear and articulate — strong choice for country names and structured questions.",
    },
    {
        "id": "arya",
        "name": "Arya",
        "gender": "female",
        "description": "Younger, energetic delivery — suitable for upbeat outreach.",
    },
    {
        "id": "abhilash",
        "name": "Abhilash",
        "gender": "male",
        "description": "Professional male voice — formal counselling and B2B tone.",
    },
    {
        "id": "karun",
        "name": "Karun",
        "gender": "male",
        "description": "Calm, steady male voice — patient support style.",
    },
    {
        "id": "hitesh",
        "name": "Hitesh",
        "gender": "male",
        "description": "Confident male voice — direct and efficient call handling.",
    },
]

DEFAULT_GREETING = (
    "Hello, thank you for calling Canam Consultants. "
    "I am Monica, your study abroad advisor. "
    "Which country are you most interested in studying in?"
)

PREVIEW_SAMPLE = (
    "Hello! Kanada is a wonderful choice for your Masters programme. "
    "How may I assist you today?"
)


def _env_float(key: str, default: float) -> float:
    import os

    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _defaults() -> dict[str, Any]:
    return {
        "tts_model": SARVAM_TTS_MODEL,
        "speaker": SARVAM_TTS_SPEAKER,
        "language_code": SARVAM_LANGUAGE_CODE,
        "pace": _env_float("SARVAM_TTS_PACE", 0.95),
        "pitch": _env_float("SARVAM_TTS_PITCH", 0.0),
        "loudness": _env_float("SARVAM_TTS_LOUDNESS", 1.1),
        "enable_preprocessing": True,
        "greeting": DEFAULT_GREETING,
    }


def _read_saved() -> dict[str, Any]:
    if not VOICE_SETTINGS_PATH.is_file():
        return {}
    try:
        return json.loads(VOICE_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_speakers_for_model(model: str) -> list[dict[str, str]]:
    if model.startswith("bulbul:v2") or model == "bulbul:v2":
        return BULBUL_V2_SPEAKERS
    return BULBUL_V2_SPEAKERS


def get_effective_voice_settings() -> dict[str, Any]:
    merged = _defaults()
    saved = _read_saved()
    for key in (
        "tts_model",
        "speaker",
        "language_code",
        "pace",
        "pitch",
        "loudness",
        "enable_preprocessing",
        "greeting",
    ):
        if key in saved and saved[key] is not None:
            merged[key] = saved[key]
    speakers = get_speakers_for_model(str(merged.get("tts_model", "bulbul:v2")))
    valid_ids = {s["id"] for s in speakers}
    if merged.get("speaker") not in valid_ids and speakers:
        merged["speaker"] = speakers[0]["id"]
    return merged


def get_voice_settings_state() -> dict[str, Any]:
    effective = get_effective_voice_settings()
    model = effective.get("tts_model", "bulbul:v2")
    speakers = get_speakers_for_model(model)
    current = effective.get("speaker")
    current_meta = next((s for s in speakers if s["id"] == current), speakers[0] if speakers else None)
    return {
        "effective": effective,
        "speakers": speakers,
        "current_speaker": current_meta,
        "preview_sample": PREVIEW_SAMPLE,
        "saved_path": str(VOICE_SETTINGS_PATH),
        "has_saved_override": VOICE_SETTINGS_PATH.is_file(),
        "supported_models": ["bulbul:v2"],
        "language_options": [
            {"code": "en-IN", "label": "English (India)"},
            {"code": "hi-IN", "label": "Hindi (India)"},
        ],
    }


def save_voice_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = get_effective_voice_settings()
    model = payload.get("tts_model") or current["tts_model"]
    speakers = get_speakers_for_model(model)
    valid_ids = {s["id"] for s in speakers}

    speaker = payload.get("speaker", current["speaker"])
    if speaker not in valid_ids:
        return {"error": f"Invalid speaker '{speaker}' for model {model}"}

    def _clamp(val, lo, hi, default):
        try:
            f = float(val)
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, f))

    updated = {
        "tts_model": model,
        "speaker": speaker,
        "language_code": payload.get("language_code") or current["language_code"],
        "pace": _clamp(payload.get("pace"), 0.3, 3.0, current["pace"]),
        "pitch": _clamp(payload.get("pitch"), -0.75, 0.75, current["pitch"]),
        "loudness": _clamp(payload.get("loudness"), 0.3, 3.0, current["loudness"]),
        "enable_preprocessing": bool(payload.get("enable_preprocessing", current["enable_preprocessing"])),
        "greeting": (payload.get("greeting") or current["greeting"]).strip(),
    }
    if not updated["greeting"]:
        updated["greeting"] = DEFAULT_GREETING

    VOICE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    VOICE_SETTINGS_PATH.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    return {"message": "Voice settings saved", **get_voice_settings_state()}


def reset_voice_settings() -> dict[str, Any]:
    if VOICE_SETTINGS_PATH.exists():
        VOICE_SETTINGS_PATH.unlink()
    return {"message": "Voice settings reset to .env defaults", **get_voice_settings_state()}


def synthesize_tts_bytes(
    text: str,
    *,
    speaker: Optional[str] = None,
    language_code: Optional[str] = None,
    model: Optional[str] = None,
    pace: Optional[float] = None,
    pitch: Optional[float] = None,
    loudness: Optional[float] = None,
    enable_preprocessing: Optional[bool] = None,
) -> bytes:
    """Generate WAV bytes for dashboard preview."""
    from sarvamai import SarvamAI

    from common.config import SARVAM_API_KEY
    from common.pronunciation import apply_pronunciation

    if not SARVAM_API_KEY:
        raise ValueError("SARVAM_API_KEY not configured")

    settings = get_effective_voice_settings()
    tts_text = apply_pronunciation(text)
    client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
    kwargs: dict[str, Any] = {
        "text": tts_text,
        "target_language_code": language_code or settings["language_code"],
        "model": model or settings["tts_model"],
        "speaker": speaker or settings["speaker"],
        "speech_sample_rate": 22050,
        "enable_preprocessing": (
            enable_preprocessing
            if enable_preprocessing is not None
            else settings["enable_preprocessing"]
        ),
    }
    tts_model = kwargs["model"]
    if str(tts_model).startswith("bulbul:v2"):
        kwargs["pace"] = pace if pace is not None else settings["pace"]
        kwargs["pitch"] = pitch if pitch is not None else settings["pitch"]
        kwargs["loudness"] = loudness if loudness is not None else settings["loudness"]

    response = client.text_to_speech.convert(**kwargs)
    audios = getattr(response, "audios", None)
    import base64

    if isinstance(audios, list) and audios:
        return base64.b64decode(audios[0])
    if isinstance(audios, str):
        return base64.b64decode(audios)
    return b""
