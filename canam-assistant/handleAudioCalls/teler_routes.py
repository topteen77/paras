"""FreJun Teler call flow and status webhooks."""
from __future__ import annotations

from urllib.parse import quote, unquote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from common.config import WEB_SERVER_URL
from common.post_call import link_call_uuid, register_call, resolve_internal_id, save_hangup_data
from common.telephony import normalize_phone, public_hostname, teler_console_urls

router = APIRouter()


class TelerFlowRequest(BaseModel):
    call_id: str = ""
    account_id: str = ""
    from_number: str = ""
    to_number: str = ""


@router.get("/teler/setup")
async def teler_setup():
    """Show Teler Voice App URLs for dashboard / manual configuration."""
    if not WEB_SERVER_URL or WEB_SERVER_URL.startswith("http://127.0.0.1"):
        return {
            "error": "Set WEB_SERVER_URL and NGROK_URL to your public ngrok HTTPS URL first.",
            "example": "https://your-subdomain.ngrok-free.app",
        }
    return teler_console_urls()


@router.post("/teler/flow/{internal_id}")
async def teler_flow(internal_id: str, payload: TelerFlowRequest):
    """Teler requests call flow when outbound call connects."""
    from teler import CallFlow

    internal_id = unquote(internal_id)
    to_number = normalize_phone(payload.to_number or "")
    if to_number:
        register_call(internal_id, to_number, call_uuid=payload.call_id or "")
    if payload.call_id:
        link_call_uuid(payload.call_id, internal_id)

    phone_enc = quote(to_number, safe="") if to_number else "unknown"

    ws_url = f"wss://{public_hostname()}/ws/media-stream/{phone_enc}/{internal_id}"
    flow = CallFlow.stream(ws_url=ws_url, chunk_size=500, record=True)
    print(
        f"[TELER_FLOW] internal_id={internal_id} call_id={payload.call_id} "
        f"to={to_number} ws={ws_url}"
    )
    return JSONResponse(flow)


@router.post("/teler/status/{internal_id}")
async def teler_status(request: Request, internal_id: str):
    """Teler call lifecycle callbacks (answered, completed, recording)."""
    internal_id = unquote(internal_id)
    try:
        data = await request.json()
    except Exception:
        form = await request.form()
        data = dict(form)

    print(f"[TELER_STATUS] internal_id={internal_id} data={data}")

    call_id = data.get("call_id") or data.get("id") or data.get("callId") or ""
    if call_id:
        link_call_uuid(call_id, internal_id)

    status = (data.get("status") or data.get("call_status") or "").lower()
    if status in ("completed", "finished", "ended", "hangup", "no-answer", "busy", "failed"):
        report = save_hangup_data(internal_id, data)
        return {
            "status": "ok",
            "internal_id": internal_id,
            "report_url": report.get("report_url"),
            "local_json_file": report.get("local_json_file"),
        }
    return {"status": "ok"}


@router.post("/teler/webhook")
async def teler_webhook(request: Request):
    """Generic Teler webhook receiver (fallback when internal_id is in payload)."""
    try:
        data = await request.json()
    except Exception:
        form = await request.form()
        data = dict(form)

    print(f"[TELER_WEBHOOK] data={data}")
    internal_id: Optional[str] = data.get("internal_id")
    if not internal_id:
        internal_id = resolve_internal_id(data)
    if internal_id:
        save_hangup_data(internal_id, data)
    return {"status": "ok"}
