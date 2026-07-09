"""Telephony provider abstraction (Twilio / Plivo)."""
import re
from urllib.parse import quote, urlparse

from common.config import (
    PLIVO_AUTH_ID,
    PLIVO_AUTH_TOKEN,
    PLIVO_PHONE_NUMBER,
    TELEPHONY_PROVIDER,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    WEB_SERVER_URL,
)


def _encode_phone(phone: str) -> str:
    return quote(normalize_phone(phone), safe="")


def normalize_phone(phone: str) -> str:
    """E.164 normalize; fixes '+' decoded as space in form-urlencoded payloads."""
    raw = (phone or "").strip()
    if raw.startswith("+"):
        return raw
    digits = re.sub(r"\D", "", raw)
    return f"+{digits}" if digits else raw


def public_hostname() -> str:
    parsed = urlparse(WEB_SERVER_URL)
    return parsed.netloc or "localhost"


def build_call_webhooks(to_number: str, internal_id: str) -> dict:
    """Public callback URLs Plivo must reach for audio + Sarvam pipeline."""
    phone_enc = _encode_phone(to_number)
    base = WEB_SERVER_URL.rstrip("/")
    host = public_hostname()
    return {
        "answer_url": f"{base}/outgoing-call/{phone_enc}/{internal_id}",
        "hangup_url": f"{base}/call/status/{phone_enc}/{internal_id}",
        "ring_url": f"{base}/call/ring/{phone_enc}/{internal_id}",
        "fallback_url": f"{base}/outgoing-call/{phone_enc}/{internal_id}",
        "websocket_url": f"wss://{host}/ws/media-stream/{phone_enc}/{internal_id}",
        "stream_status_url": f"{base}/stream/status/{phone_enc}/{internal_id}",
    }


def plivo_console_urls() -> dict:
    """URLs to paste into Plivo Console → XML Application (inbound calls)."""
    base = WEB_SERVER_URL.rstrip("/")
    return {
        "answer_url": f"{base}/plivo/inbound",
        "hangup_url": f"{base}/plivo/hangup",
        "fallback_answer_url": f"{base}/plivo/inbound",
        "message_url": f"{base}/plivo/inbound",
    }


def create_outbound_call(to_number: str, internal_id: str) -> dict:
    """Initiate an outbound call. Returns {call_sid, internal_id, webhooks} or {error}."""
    webhooks = build_call_webhooks(to_number, internal_id)
    answer_url = webhooks["answer_url"]
    status_url = webhooks["hangup_url"]

    if TELEPHONY_PROVIDER == "plivo":
        import plivo

        if not PLIVO_AUTH_ID or not PLIVO_AUTH_TOKEN or not PLIVO_PHONE_NUMBER:
            return {"error": "Plivo credentials not configured."}
        if not WEB_SERVER_URL or WEB_SERVER_URL.startswith("http://127.0.0.1"):
            return {
                "error": "WEB_SERVER_URL must be your public ngrok HTTPS URL (not localhost).",
                "webhooks": webhooks,
            }
        client = plivo.RestClient(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)
        print(f"[PLIVO_CALL] answer_url={answer_url}")
        print(f"[PLIVO_CALL] hangup_url={status_url}")
        print(f"[PLIVO_CALL] websocket_url={webhooks['websocket_url']}")
        response = client.calls.create(
            from_=PLIVO_PHONE_NUMBER,
            to_=to_number,
            answer_url=answer_url,
            answer_method="POST",
            ring_url=webhooks["ring_url"],
            ring_method="POST",
            hangup_url=status_url,
            hangup_method="POST",
            fallback_url=webhooks["fallback_url"],
            fallback_method="POST",
        )
        call_sid = getattr(response, "request_uuid", None) or response.get("request_uuid")
        return {
            "call_sid": call_sid,
            "internal_id": internal_id,
            "webhooks": webhooks,
        }

    from twilio.rest import Client

    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_NUMBER:
        return {"error": "Twilio credentials not configured."}
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    call = client.calls.create(
        url=answer_url,
        to=to_number,
        from_=TWILIO_PHONE_NUMBER,
        status_callback=status_url,
        status_callback_event=[
            "initiated",
            "ringing",
            "answered",
            "busy",
            "no-answer",
            "failed",
            "canceled",
            "completed",
        ],
    )
    return {"call_sid": call.sid, "internal_id": internal_id}


def end_call(call_sid: str) -> dict:
    """Hang up an active call."""
    if not call_sid:
        return {"status": "error", "message": "Missing call SID"}

    try:
        if TELEPHONY_PROVIDER == "plivo":
            import plivo

            client = plivo.RestClient(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)
            client.calls.hangup(call_sid)
            return {"status": "success", "message": f"Call {call_sid} ended."}

        from twilio.rest import Client

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.calls(call_sid).update(status="completed")
        return {"status": "success", "message": f"Call {call_sid} ended."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def normalize_call_status(provider: str, raw_status: str) -> str:
    """Map provider-specific statuses to internal status names."""
    status = (raw_status or "").lower()
    if provider == "plivo":
        mapping = {
            "in-progress": "answered",
            "completed": "completed",
            "busy": "busy",
            "no-answer": "no-answer",
            "failed": "failed",
            "canceled": "canceled",
            "cancel": "canceled",
            "ringing": "ringing",
        }
        return mapping.get(status, status)
    return status


def get_call_sid_from_callback(form_data: dict) -> str:
    if TELEPHONY_PROVIDER == "plivo":
        return form_data.get("CallUUID") or form_data.get("call_uuid") or ""
    return form_data.get("CallSid") or ""


def get_call_status_from_callback(form_data: dict) -> str:
    if TELEPHONY_PROVIDER == "plivo":
        raw = form_data.get("CallStatus") or form_data.get("Status") or ""
        return normalize_call_status("plivo", raw)
    return form_data.get("CallStatus") or ""
