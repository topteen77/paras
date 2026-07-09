"""System configuration snapshot for the dashboard."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import requests

from common.config import (
    BIG_QUERY_DATASET_ID,
    CALL_RECORDINGS_DIR,
    DEFAULT_CALL_DURATION_IN_SECONDS,
    ELEVEN_LABS_AFTER_VISIT_FEEDBACK_AGENT_ID,
    ELEVEN_LABS_COLD_CALLING_AGENT_ID,
    MAX_CALL_RETRY_COUNT,
    MAX_PARRALLEL_REQUESTS_TO_AGENT,
    NGROK_URL,
    PLIVO_AUTH_ID,
    PLIVO_AUTH_TOKEN,
    PLIVO_PHONE_NUMBER,
    POST_CALL_WEBHOOK_URL,
    PROJECT_ID,
    QUEUE_NAME,
    REGION_NAME,
    SARVAM_CHAT_MODEL,
    SARVAM_LANGUAGE_CODE,
    SARVAM_STT_MODEL,
    SARVAM_SYSTEM_PROMPT_PATH,
    SARVAM_TTS_MODEL,
    SARVAM_TTS_SPEAKER,
    STATUS_COMPLETE_TASK_DELAY_IN_SECONDS,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    WEB_SERVER_URL,
)
from common.post_call import recording_callback_url
from common.runtime_stack import get_active_stack, get_telephony_provider, get_voice_ai_provider
from common.prompt_manager import get_prompt_state
from common.telephony import build_call_webhooks, plivo_console_urls, public_hostname


def _normalize_number(value: Optional[str]) -> str:
    if not value:
        return ""
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits


def _numbers_match(a: Optional[str], b: Optional[str]) -> bool:
    return _normalize_number(a) == _normalize_number(b) and bool(_normalize_number(a))


def _mask_secret(value: Optional[str], visible: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}...{value[-visible:]}"


def _prompt_exists(path_value: str) -> bool:
    return Path(path_value).exists()


def _fetch_plivo_numbers() -> list[dict[str, Any]]:
    if not PLIVO_AUTH_ID or not PLIVO_AUTH_TOKEN:
        return []
    try:
        response = requests.get(
            f"https://api.plivo.com/v1/Account/{PLIVO_AUTH_ID}/Number/",
            auth=(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN),
            params={"limit": 20},
            timeout=12,
        )
        if response.status_code != 200:
            return []
        objects = response.json().get("objects", [])
        numbers = []
        for item in objects:
            numbers.append(
                {
                    "number": item.get("number"),
                    "alias": item.get("alias"),
                    "region": item.get("region"),
                    "voice_enabled": item.get("voice_enabled"),
                    "sms_enabled": item.get("sms_enabled"),
                    "application": item.get("application"),
                    "sub_account": item.get("sub_account"),
                    "configured_outbound": _numbers_match(item.get("number"), PLIVO_PHONE_NUMBER),
                }
            )
        return numbers
    except Exception:
        return []


def _fetch_twilio_numbers() -> list[dict[str, Any]]:
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        return []
    try:
        response = requests.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/IncomingPhoneNumbers.json",
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            params={"PageSize": 20},
            timeout=12,
        )
        if response.status_code != 200:
            return []
        numbers = []
        for item in response.json().get("incoming_phone_numbers", []):
            numbers.append(
                {
                    "number": item.get("phone_number"),
                    "friendly_name": item.get("friendly_name"),
                    "voice_url": item.get("voice_url"),
                    "status_callback": item.get("status_callback"),
                    "configured_outbound": _numbers_match(item.get("phone_number"), TWILIO_PHONE_NUMBER),
                }
            )
        return numbers
    except Exception:
        return []


def _callback_groups() -> dict[str, Any]:
    base = WEB_SERVER_URL.rstrip("/")
    host = public_hostname()
    sample_phone = "+919876543210"
    sample_internal_id = "sample-internal-id"
    sample_webhooks = build_call_webhooks(sample_phone, sample_internal_id)
    public_ok = bool(base and not base.startswith("http://127.0.0.1"))

    return {
        "public_base_url": base,
        "websocket_host": host,
        "public_url_ok": public_ok,
        "inbound_plivo_console": {
            "title": "Plivo Console → XML Application (inbound calls)",
            "urls": plivo_console_urls(),
        },
        "outbound_per_call": {
            "title": "Outbound call webhooks (set automatically per call)",
            "note": "Replace {to} and {internal_id} with real values.",
            "urls": {
                "answer_url": f"{base}/outgoing-call/{{to}}/{{internal_id}}",
                "hangup_url": f"{base}/call/status/{{to}}/{{internal_id}}",
                "ring_url": f"{base}/call/ring/{{to}}/{{internal_id}}",
                "fallback_url": f"{base}/outgoing-call/{{to}}/{{internal_id}}",
                "websocket_url": f"wss://{host}/ws/media-stream/{{to}}/{{internal_id}}",
                "stream_status_url": f"{base}/stream/status/{{to}}/{{internal_id}}",
                "recording_callback": f"{base}/recording/ready/{{internal_id}}",
            },
        },
        "example_outbound": {
            "title": "Example outbound URLs (sample call)",
            "note": f"Sample: {sample_phone} / {sample_internal_id}",
            "urls": {
                **sample_webhooks,
                "recording_callback": recording_callback_url(sample_internal_id),
            },
        },
        "scheduler_and_reports": {
            "title": "Scheduler, status, and post-call APIs",
            "urls": {
                "make_call": f"{base}/make-call",
                "make_call_direct": f"{base}/make-call-direct",
                "schedule_calls": f"{base}/schedule-calls",
                "process_scheduled_calls": f"{base}/process-scheduled-calls",
                "create_scheduled_task": f"{base}/create-scheduled-task",
                "list_reports": f"{base}/call/reports",
                "single_report": f"{base}/call/report/{{internal_id}}",
                "health": f"{base}/health",
                "dashboard": f"{base}/",
            },
        },
    }


def get_system_configuration() -> dict[str, Any]:
    telephony = get_telephony_provider()
    voice_ai = get_voice_ai_provider()
    active = get_active_stack()

    models: dict[str, Any] = {
        "voice_ai_provider": voice_ai,
        "telephony_provider": telephony,
    }

    if voice_ai == "sarvam":
        models["sarvam"] = {
            "chat_model": SARVAM_CHAT_MODEL,
            "stt_model": SARVAM_STT_MODEL,
            "tts_model": SARVAM_TTS_MODEL,
            "tts_speaker": SARVAM_TTS_SPEAKER,
            "language_code": SARVAM_LANGUAGE_CODE,
            "system_prompt_path": SARVAM_SYSTEM_PROMPT_PATH,
            "system_prompt_exists": _prompt_exists(SARVAM_SYSTEM_PROMPT_PATH),
        }
    if voice_ai == "elevenlabs":
        models["elevenlabs"] = {
            "cold_calling_agent_id": ELEVEN_LABS_COLD_CALLING_AGENT_ID or None,
            "after_visit_feedback_agent_id": ELEVEN_LABS_AFTER_VISIT_FEEDBACK_AGENT_ID or None,
        }

    plivo_numbers = _fetch_plivo_numbers()
    twilio_numbers = _fetch_twilio_numbers()

    phone_section: dict[str, Any] = {
        "active_telephony": telephony,
        "configured_outbound": {
            "plivo": PLIVO_PHONE_NUMBER or None,
            "twilio": TWILIO_PHONE_NUMBER or None,
        },
        "active_outbound_number": PLIVO_PHONE_NUMBER if telephony == "plivo" else TWILIO_PHONE_NUMBER,
        "plivo_account_numbers": plivo_numbers,
        "twilio_account_numbers": twilio_numbers,
        "outbound_configured": bool(
            (telephony == "plivo" and PLIVO_PHONE_NUMBER)
            or (telephony == "twilio" and TWILIO_PHONE_NUMBER)
        ),
    }

    if telephony == "plivo" and PLIVO_PHONE_NUMBER and plivo_numbers:
        matched = [n for n in plivo_numbers if _numbers_match(n.get("number"), PLIVO_PHONE_NUMBER)]
        phone_section["active_number_details"] = matched[0] if matched else None
        phone_section["active_number_on_account"] = bool(matched)

    credentials: dict[str, Any] = {
        "plivo_auth_id": _mask_secret(PLIVO_AUTH_ID) if PLIVO_AUTH_ID else None,
        "twilio_account_sid": _mask_secret(TWILIO_ACCOUNT_SID) if TWILIO_ACCOUNT_SID else None,
    }

    return {
        "active_stack": active,
        "models": models,
        "phone_numbers": phone_section,
        "credentials": credentials,
        "callbacks": _callback_groups(),
        "tuning": {
            "max_parallel_requests_to_agent": MAX_PARRALLEL_REQUESTS_TO_AGENT,
            "default_call_duration_seconds": DEFAULT_CALL_DURATION_IN_SECONDS,
            "max_call_retry_count": MAX_CALL_RETRY_COUNT,
            "status_complete_task_delay_seconds": STATUS_COMPLETE_TASK_DELAY_IN_SECONDS,
        },
        "infrastructure": {
            "web_server_url": WEB_SERVER_URL,
            "ngrok_url": NGROK_URL or None,
            "call_recordings_dir": CALL_RECORDINGS_DIR,
            "project_id": PROJECT_ID if PROJECT_ID not in ("your-gcp-project-id", "CHANGE_ME") else None,
            "region": REGION_NAME if REGION_NAME else None,
            "queue_name": QUEUE_NAME if QUEUE_NAME and QUEUE_NAME != "your-cloud-tasks-queue" else None,
            "bigquery_dataset": BIG_QUERY_DATASET_ID if BIG_QUERY_DATASET_ID else None,
        },
        "webhooks": {
            "post_call_webhook_url": POST_CALL_WEBHOOK_URL,
            "post_call_configured": bool(POST_CALL_WEBHOOK_URL),
        },
        "prompts": get_prompt_state(),
    }
