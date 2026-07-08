import os
from urllib.parse import unquote

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse
from pathlib import Path
import pandas as pd
from twilio.twiml.voice_response import VoiceResponse, Connect

from common.config import STATUS_COMPLETE_TASK_DELAY_IN_SECONDS, TELEPHONY_PROVIDER
from common.functions import (
    add_call_staus_to_pubsub,
    create_scheduled_call_record,
    create_task,
    handle_failed_calls,
    log_call_to_firestore_status_update,
    proces_scheduled_calls,
    write_to_bigquery,
)
from common.telephony import create_outbound_call, get_call_sid_from_callback, get_call_status_from_callback

router = APIRouter()


def _stream_url(hostname: str, to_phone_number: str, internal_id: str) -> str:
    return f"wss://{hostname}/ws/media-stream/{to_phone_number}/{internal_id}"


def _build_answer_xml(hostname: str, to_phone_number: str, internal_id: str) -> str:
    stream_url = _stream_url(hostname, to_phone_number, internal_id)
    if TELEPHONY_PROVIDER == "plivo":
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000">{stream_url}</Stream>
</Response>"""
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=stream_url)
    response.append(connect)
    return str(response)


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
    result = create_outbound_call(to_phone_number, internal_id)
    return result


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
    to_phone_number = unquote(to_phone_number)
    xml = _build_answer_xml(request.url.hostname, to_phone_number, internal_id)
    return HTMLResponse(content=xml, media_type="application/xml")


@router.post("/twilio/inbound_call")
async def handle_incoming_call(request: Request):
    import uuid
    form_data = await request.form()
    from_number = form_data.get("From", "Unknown")
    internal_id = str(uuid.uuid4())
    xml = _build_answer_xml(request.url.hostname, from_number, internal_id)
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
