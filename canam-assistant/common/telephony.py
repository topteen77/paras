"""Telephony provider abstraction (Twilio / Plivo)."""
from urllib.parse import quote

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
    return quote(str(phone), safe="")


def create_outbound_call(to_number: str, internal_id: str) -> dict:
    """Initiate an outbound call. Returns {call_sid, internal_id} or {error}."""
    phone_enc = _encode_phone(to_number)
    answer_url = f"{WEB_SERVER_URL}/outgoing-call/{phone_enc}/{internal_id}"
    status_url = f"{WEB_SERVER_URL}/call/status/{phone_enc}/{internal_id}"

    if TELEPHONY_PROVIDER == "plivo":
        import plivo

        if not PLIVO_AUTH_ID or not PLIVO_AUTH_TOKEN or not PLIVO_PHONE_NUMBER:
            return {"error": "Plivo credentials not configured."}
        client = plivo.RestClient(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)
        response = client.calls.create(
            from_=PLIVO_PHONE_NUMBER,
            to_=to_number,
            answer_url=answer_url,
            answer_method="POST",
            hangup_url=status_url,
            hangup_method="POST",
        )
        return {"call_sid": response[1].request_uuid, "internal_id": internal_id}

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
