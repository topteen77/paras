import os
from fastapi import APIRouter, Request
from fastapi import UploadFile
from fastapi.responses import HTMLResponse
from twilio.twiml.voice_response import VoiceResponse, Connect
from pathlib import Path
import pandas as pd
from common.config import (
    STATUS_COMPLETE_TASK_DELAY_IN_SECONDS,
)
from common.functions import add_call_staus_to_pubsub, create_scheduled_call_record, create_task, handle_failed_calls, log_call_to_firestore_status_update, proces_scheduled_calls, write_to_bigquery
router = APIRouter()
@router.post("/make-call")
async def make_call(request: Request):
    data = await request.json()
    to_phone_number = data.get("to")
    internal_id = data.get("internal_id", "")
    print(f"[internal_id={internal_id}] [make_call] Received request to make a call. to_phone_number={to_phone_number}")
    if not to_phone_number:
        print(f"[internal_id={internal_id}] [make_call] Error: Phone number is required.")
        return {"error": "Phone number is required"}
    response = create_scheduled_call_record(
        to_phone_number=to_phone_number, 
        internal_id=internal_id,   
        filename="N/A",
        name=""
    )
    print(f"[internal_id={internal_id}] [make_call] Scheduled call record created.")
    return response

@router.post("/call/status/completed/{to_phone_number}/{internal_id}/{call_sid}")
async def call_status_callback(request: Request, to_phone_number: str, internal_id: str, call_sid: str):
    print(f"[internal_id={internal_id}] [call_status_callback] Received call status completed callback for to_phone_number={to_phone_number}, call_sid={call_sid}")
    form_data = await request.form()
    print(f"[internal_id={internal_id}] [call_status_callback] Form data received: {form_data}")
    add_call_staus_to_pubsub(call_sid, internal_id, to_phone_number, 'completed')
    return {"status": "ok"}

@router.post("/call/status/{to_phone_number}/{internal_id}")
async def call_status_callback(request: Request, to_phone_number: str, internal_id: str):
    print(f"[internal_id={internal_id}] [call_status_callback] Received call status callback for to_phone_number={to_phone_number}, internal_id={internal_id}")
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus")
    print(f"[internal_id={internal_id}] [call_status_callback] Call status update: CallSid={call_sid}, Status={call_status}, Internal ID={internal_id}")
    if call_status != 'completed':
        print(f"[internal_id={internal_id}] [call_status_callback] Adding call status '{call_status}' to pubsub for CallSid={call_sid}, internal_id={internal_id}")
        add_call_staus_to_pubsub(call_sid, internal_id, to_phone_number, call_status)
    else:
        print(f"[internal_id={internal_id}] [call_status_callback] Call status is 'completed'. Creating delayed task for CallSid={call_sid}, internal_id={internal_id}")
        create_task(
            request.url.hostname,
            f"call/status/completed/{to_phone_number}/{internal_id}/{call_sid}",
            data={},
            delay_seconds=STATUS_COMPLETE_TASK_DELAY_IN_SECONDS
        )
    print(f"[internal_id={internal_id}] [call_status_callback] Writing call status to BigQuery for CallSid={call_sid}, internal_id={internal_id}")
    write_to_bigquery(internal_id, call_sid, to_phone_number, call_status)
    print(f"[internal_id={internal_id}] [call_status_callback] Logging call status update to Firestore for CallSid={call_sid}, internal_id={internal_id}")
    can_retry = log_call_to_firestore_status_update(internal_id, to_phone_number, call_status)
    if can_retry:
        print(f"[internal_id={internal_id}] [call_status_callback] Call {call_sid} can be retried. Scheduling retry. internal_id={internal_id}")
        handle_failed_calls(call_status, to_phone_number, internal_id, request.url.hostname)
    else:
        print(f"[internal_id={internal_id}] [call_status_callback] Call {call_sid} cannot be retried. internal_id={internal_id}")
    return {"status": "ok"}

@router.api_route("/outgoing-call/{to_phone_number}/{internal_id}", methods=["GET", "POST"])
async def handle_outgoing_call(request: Request,to_phone_number: str,internal_id: str):
    print(f"Handling outgoing call to: {to_phone_number} with internal ID: {internal_id}")
    """Handle outgoing call and return TwiML response to connect to Media Stream."""
    print(f"[internal_id={internal_id}] [handle_outgoing_call] Handling outgoing call to: {to_phone_number} with internal ID: {internal_id}")
    response = VoiceResponse()
    connect = Connect()
    # Ensure the WebSocket URL is correct based on your NGROK setup and main app's router prefix
    connect.stream(url=f'wss://{request.url.hostname}/ws/media-stream/{to_phone_number}/{internal_id}') # Assuming /ws prefix for websocket router
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@router.post("/twilio/inbound_call")
async def handle_incoming_call(request: Request):
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "Unknown")
    from_number = form_data.get("From", "Unknown")
    internal_id = form_data.get("internal_id", "")
    print(f"[internal_id={internal_id}] [handle_incoming_call] Incoming call: CallSid={call_sid}, From={from_number}")
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f"wss://{request.url.hostname}/ws/media-stream")
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@router.post("/create-scheduled-task")
async def create_scheduled_task(request: Request):
    print(f"[create_scheduled_task] Received request to create scheduled task.")
    hostname = request.url.hostname
    print(f"[create_scheduled_task] Creating task for hostname={hostname}")
    response = create_task(hostname, 'process-scheduled-calls', {}, 20)
    print(f"[create_scheduled_task] Task created: {response.name}")
    return {'task_name': response.name}

@router.post("/process-scheduled-calls")
async def scheduled_calls(request: Request):
    return proces_scheduled_calls(request.url.hostname)
    
@router.post("/schedule-calls")
async def schedule_call(file: UploadFile):
    print(f"[schedule_call] Received file upload: filename={file.filename}")
    file_path = Path("uploads") / file.filename
    allowed_extensions = ['.xlsx', '.xls', '.xlsm']
    file_extension = Path(file.filename).suffix.lower()
    if file_extension not in allowed_extensions:
        print(f"[schedule_call] Invalid file extension: {file_extension} for filename={file.filename}")
        return {"filename": file.filename, "message": "only excel files allowed."}

    os.makedirs(file_path.parent, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(await file.read())
    print(f"[schedule_call] Saved file to {file_path}")

    df = pd.read_excel(file_path)
    print(f"[schedule_call] Read {len(df)} records from Excel file: {file.filename}")

    for _, row in df.iterrows():
        internal_id = row.get('internal_id', '')
        print(f"[internal_id={internal_id}] [schedule_call] Scheduling call for phonenumber={row.get('phonenumber')}, name={row.get('name', 'Unknown')}")
        create_scheduled_call_record(
            to_phone_number=row.get('phonenumber'),
            filename=file.filename,
            internal_id="",
            name=row.get('name', 'Unknown')
        )

    file_path.unlink()
    print(f"[schedule_call] Cleaned up uploaded file: {file_path}")
    return {"filename": file.filename, "message": "Calls scheduled successfully."}
