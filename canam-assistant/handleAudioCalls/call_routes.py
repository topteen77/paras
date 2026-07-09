import os
from urllib.parse import quote, unquote

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse
from pathlib import Path
import pandas as pd
from twilio.twiml.voice_response import VoiceResponse, Connect

from common.runtime_stack import get_telephony_provider
from common.config import STATUS_COMPLETE_TASK_DELAY_IN_SECONDS, WEB_SERVER_URL
from common.functions import (
    add_call_staus_to_pubsub,
    create_scheduled_call_record,
    create_task,
    handle_failed_calls,
    log_call_to_firestore_initiated,
    log_call_to_firestore_status_update,
    proces_scheduled_calls,
    write_to_bigquery,
)
from common.post_call import (
    internal_id_for_call_uuid,
    link_call_uuid,
    list_reports,
    load_report,
    recording_callback_url,
    register_call,
    resolve_internal_id,
    save_hangup_data,
    save_recording_data,
)
from common.telephony import (
    build_call_webhooks,
    create_outbound_call,
    get_call_sid_from_callback,
    get_call_status_from_callback,
    normalize_phone,
    plivo_console_urls,
    public_hostname,
)

router = APIRouter()


def _build_answer_xml(to_phone_number: str, internal_id: str) -> str:
    webhooks = build_call_webhooks(to_phone_number, internal_id)
    stream_url = webhooks["websocket_url"]
    stream_status_url = webhooks["stream_status_url"]
    recording_url = recording_callback_url(internal_id)
    if get_telephony_provider() == "plivo":
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Record recordSession="true" callbackUrl="{recording_url}" callbackMethod="POST" />
  <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000" statusCallbackUrl="{stream_status_url}" statusCallbackMethod="POST">{stream_url}</Stream>
</Response>"""
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=stream_url)
    response.append(connect)
    return str(response)


@router.get("/plivo/setup")
async def plivo_setup():
    """Show exact URLs to paste in Plivo Console."""
    if not WEB_SERVER_URL or WEB_SERVER_URL.startswith("http://127.0.0.1"):
        return {
            "error": "Set WEB_SERVER_URL and NGROK_URL to your public ngrok HTTPS URL first.",
            "example": "https://your-subdomain.ngrok-free.app",
        }
    return {
        "web_server_url": WEB_SERVER_URL,
        "plivo_console_xml_application": plivo_console_urls(),
        "outbound_call_webhooks": {
            "note": "Set automatically per call by /make-call-direct",
            "answer_url": f"{WEB_SERVER_URL.rstrip('/')}/outgoing-call/{{to}}/{{internal_id}}",
            "hangup_url": f"{WEB_SERVER_URL.rstrip('/')}/call/status/{{to}}/{{internal_id}}",
            "websocket_url": f"wss://{public_hostname()}/ws/media-stream/{{to}}/{{internal_id}}",
            "recording_callback": f"{WEB_SERVER_URL.rstrip('/')}/recording/ready/{{internal_id}}",
        },
        "post_call_report": {
            "fetch_report": f"{WEB_SERVER_URL.rstrip('/')}/call/report/{{internal_id}}",
            "list_reports": f"{WEB_SERVER_URL.rstrip('/')}/call/reports",
            "local_folder": "call-recordings/",
            "local_filename_format": "{{phone}}_{{timestamp}}.json",
            "webhook_env": "POST_CALL_WEBHOOK_URL (optional — POST JSON to your server on call end)",
        },
    }


@router.post("/make-call")
async def make_call(request: Request):
    data = await request.json()
    to_phone_number = data.get("to")
    internal_id = data.get("internal_id", "")
    if not to_phone_number:
        return {"error": "Phone number is required"}
    return create_scheduled_call_record(
        to_phone_number=to_phone_number,
        internal_id=internal_id,
        filename="N/A",
        name=data.get("name", ""),
    )


@router.post("/make-call-direct")
async def make_call_direct(request: Request):
    """Initiate outbound call immediately (local Plivo/Twilio testing)."""
    data = await request.json()
    to_phone_number = data.get("to")
    internal_id = data.get("internal_id", "")
    if not to_phone_number:
        return {"error": "Phone number is required"}
    if not internal_id:
        from uuid import uuid4
        internal_id = str(uuid4())
    register_call(internal_id, to_phone_number)
    result = create_outbound_call(to_phone_number, internal_id)
    if result.get("call_sid"):
        link_call_uuid(result["call_sid"], internal_id)
        log_call_to_firestore_initiated(result["call_sid"], to_phone_number, internal_id)
        result["report_url"] = f"{WEB_SERVER_URL.rstrip('/')}/call/report/{internal_id}"
        result["local_recordings_dir"] = "call-recordings"
    return result


@router.post("/call/ring/{to_phone_number}/{internal_id}")
async def call_ring_callback(request: Request, to_phone_number: str, internal_id: str):
    to_phone_number = unquote(to_phone_number)
    form_data = await request.form()
    print(f"[PLIVO_RING] to={to_phone_number} internal_id={internal_id} data={dict(form_data)}")
    return {"status": "ok"}


@router.post("/stream/status/{to_phone_number}/{internal_id}")
async def stream_status_callback(request: Request, to_phone_number: str, internal_id: str):
    to_phone_number = unquote(to_phone_number)
    form_data = await request.form()
    print(f"[PLIVO_STREAM] to={to_phone_number} internal_id={internal_id} event={dict(form_data)}")
    return {"status": "ok"}


@router.api_route("/plivo/inbound", methods=["GET", "POST"])
async def plivo_inbound(request: Request):
    """Plivo Console Answer URL — connects inbound callers to Sarvam via WebSocket."""
    from uuid import uuid4

    if request.method == "POST":
        form_data = await request.form()
        from_number = normalize_phone(form_data.get("From") or form_data.get("from") or "unknown")
    else:
        from_number = normalize_phone(request.query_params.get("From", "unknown"))
    internal_id = str(uuid4())
    register_call(internal_id, from_number)
    print(f"[PLIVO_INBOUND] from={from_number} internal_id={internal_id}")
    xml = _build_answer_xml(from_number, internal_id)
    return HTMLResponse(content=xml, media_type="application/xml")


@router.api_route("/plivo/hangup", methods=["GET", "POST"])
async def plivo_hangup(request: Request):
    """Plivo Console Hangup URL — saves call metadata and triggers post-call report."""
    form_dict = {}
    if request.method == "POST":
        form_data = await request.form()
        form_dict = dict(form_data)
        print(f"[PLIVO_HANGUP] data={form_dict}")
    call_uuid = form_dict.get("CallUUID") or form_dict.get("call_uuid") or ""
    internal_id = resolve_internal_id(form_dict) if call_uuid or form_dict else None
    if internal_id:
        report = save_hangup_data(internal_id, form_dict)
        return {
            "status": "ok",
            "internal_id": internal_id,
            "report_url": report.get("report_url"),
            "local_json_file": report.get("local_json_file"),
        }
    return {"status": "ok", "note": "call not linked to internal_id yet"}


@router.post("/recording/ready/{internal_id}")
async def recording_ready(request: Request, internal_id: str):
    """Plivo posts recording URL here when the call recording is ready."""
    internal_id = unquote(internal_id)
    form_data = await request.form()
    form_dict = dict(form_data)
    print(f"[PLIVO_RECORDING] internal_id={internal_id} data={form_dict}")
    report = save_recording_data(internal_id, form_dict)
    return {"status": "ok", "recording_url": (report.get("recording") or {}).get("url")}


@router.get("/call/report/{internal_id}")
async def get_call_report(internal_id: str):
    report = load_report(internal_id)
    if not report:
        return {"error": "Report not found", "internal_id": internal_id}
    return report


@router.get("/call/reports")
async def get_call_reports(limit: int = 20):
    return {"reports": list_reports(limit=limit)}


@router.post("/call/status/completed/{to_phone_number}/{internal_id}/{call_sid}")
async def call_status_completed(request: Request, to_phone_number: str, internal_id: str, call_sid: str):
    to_phone_number = unquote(to_phone_number)
    add_call_staus_to_pubsub(call_sid, internal_id, to_phone_number, "completed")
    return {"status": "ok"}


@router.post("/call/status/{to_phone_number}/{internal_id}")
async def call_status_callback(request: Request, to_phone_number: str, internal_id: str):
    to_phone_number = unquote(to_phone_number)
    form_data = await request.form()
    form_dict = dict(form_data)
    call_sid = get_call_sid_from_callback(form_dict)
    call_status = get_call_status_from_callback(form_dict)

    save_hangup_data(internal_id, form_dict)

    if call_status != "completed":
        add_call_staus_to_pubsub(call_sid, internal_id, to_phone_number, call_status)
    else:
        create_task(
            request.url.hostname,
            f"call/status/completed/{to_phone_number}/{internal_id}/{call_sid}",
            data={},
            delay_seconds=STATUS_COMPLETE_TASK_DELAY_IN_SECONDS,
        )

    write_to_bigquery(internal_id, call_sid, to_phone_number, call_status)
    can_retry = log_call_to_firestore_status_update(internal_id, to_phone_number, call_status)
    if can_retry:
        handle_failed_calls(call_status, to_phone_number, internal_id, request.url.hostname)
    return {"status": "ok"}


@router.api_route("/outgoing-call/{to_phone_number}/{internal_id}", methods=["GET", "POST"])
async def handle_outgoing_call(request: Request, to_phone_number: str, internal_id: str):
    to_phone_number = normalize_phone(unquote(to_phone_number))
    webhooks = build_call_webhooks(to_phone_number, internal_id)
    register_call(internal_id, to_phone_number)
    print(f"[PLIVO_ANSWER] to={to_phone_number} internal_id={internal_id}")
    print(f"[PLIVO_ANSWER] websocket={webhooks['websocket_url']}")
    xml = _build_answer_xml(to_phone_number, internal_id)
    return HTMLResponse(content=xml, media_type="application/xml")


@router.post("/twilio/inbound_call")
async def handle_incoming_call(request: Request):
    import uuid
    form_data = await request.form()
    from_number = form_data.get("From", "Unknown")
    internal_id = str(uuid.uuid4())
    xml = _build_answer_xml(from_number, internal_id)
    return HTMLResponse(content=xml, media_type="application/xml")


@router.post("/create-scheduled-task")
async def create_scheduled_task(request: Request):
    response = create_task(request.url.hostname, "process-scheduled-calls", {}, 20)
    if response is None:
        return {"error": "Failed to create task"}
    return {"task_name": response.name}


@router.post("/process-scheduled-calls")
async def scheduled_calls(request: Request):
    return proces_scheduled_calls(request.url.hostname)


@router.post("/schedule-calls")
async def schedule_call(file: UploadFile):
    file_path = Path("uploads") / file.filename
    allowed_extensions = [".xlsx", ".xls", ".xlsm"]
    if Path(file.filename).suffix.lower() not in allowed_extensions:
        return {"filename": file.filename, "message": "only excel files allowed."}

    os.makedirs(file_path.parent, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    df = pd.read_excel(file_path)
    for _, row in df.iterrows():
        create_scheduled_call_record(
            to_phone_number=row.get("phonenumber"),
            filename=file.filename,
            internal_id=str(row.get("internal_id") or ""),
            name=row.get("name", "Unknown"),
        )

    file_path.unlink()
    return {"filename": file.filename, "message": "Calls scheduled successfully."}
