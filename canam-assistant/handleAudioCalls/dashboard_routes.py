from pathlib import Path

from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from starlette.requests import Request

from common.dashboard import (
    dashboard_stats,
    get_dashboard_call,
    list_dashboard_calls,
    list_scheduled_tasks,
    resolve_recording_path,
)
from common.functions import create_scheduled_call_record, create_task
from common.provider_status import get_integrations_summary
from common.runtime_stack import get_active_stack, set_active_stack
from common.system_config import get_system_configuration
from common.prompt_manager import clear_user_prompt, get_prompt_state, save_user_prompt
from common.call_script import get_call_script_state, reset_call_script, save_call_script
from common.voice_settings import (
    get_voice_settings_state,
    reset_voice_settings,
    save_voice_settings,
    synthesize_tts_bytes,
)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

_simulate_sessions: dict[str, dict] = {}


def _require_sarvam():
    from common.runtime_stack import get_voice_ai_provider
    from common.config import SARVAM_API_KEY

    if get_voice_ai_provider() != "sarvam":
        return {"error": "Practice simulate requires Sarvam voice stack"}
    if not SARVAM_API_KEY:
        return {"error": "SARVAM_API_KEY not configured"}
    return None


class _TextSimulateInterface:
    """Minimal audio stub for text-only practice sessions."""

    use_mulaw = False

    def send_audio_threadsafe(self, audio: bytes):
        pass

    def clear_audio_threadsafe(self):
        pass


@router.post("/simulate/start")
async def simulate_text_start():
    from uuid import uuid4

    from handleAudioCalls.sarvam_voice_agent import SarvamVoiceAgent

    err = _require_sarvam()
    if err:
        return err

    session_id = str(uuid4())
    agent = SarvamVoiceAgent(_TextSimulateInterface(), "", simulate_mode=True)
    greeting = await agent.start_text_session()
    _simulate_sessions[session_id] = {"agent": agent}
    return {
        "session_id": session_id,
        "greeting": greeting,
        "flow": agent.flow_state(),
    }


@router.post("/simulate/turn")
async def simulate_text_turn(request: Request):
    data = await request.json()
    session_id = data.get("session_id")
    message = (data.get("message") or "").strip()
    if not session_id or not message:
        return {"error": "session_id and message are required"}
    entry = _simulate_sessions.get(session_id)
    if not entry:
        return {"error": "Session not found — start a new practice session"}
    agent = entry["agent"]
    await agent._handle_user_utterance(message, speak=False)
    reply = ""
    for msg in reversed(agent.messages):
        if msg.get("role") == "assistant":
            reply = msg.get("content", "")
            break
    ended = agent.should_end_session()
    if ended:
        _simulate_sessions.pop(session_id, None)
    return {
        "reply": reply,
        "ended": ended,
        "flow": agent.flow_state(),
        "transcript": [
            {"role": m["role"], "text": m["content"]}
            for m in agent.messages
            if m.get("role") != "system" and m.get("content")
        ],
    }


@router.delete("/simulate/{session_id}")
async def simulate_text_end(session_id: str):
    _simulate_sessions.pop(session_id, None)
    return {"message": "Session ended"}


@router.get("/call-script")
async def get_call_script():
    return get_call_script_state()


@router.put("/call-script")
async def update_call_script(request: Request):
    data = await request.json()
    result = save_call_script(data)
    if result.get("error"):
        return result
    return result


@router.delete("/call-script")
async def reset_call_script_route():
    return reset_call_script()


@router.get("/prompts")
async def get_prompts():
    return get_prompt_state()


@router.put("/prompts")
async def update_prompt(request: Request):
    data = await request.json()
    content = data.get("content", "")
    result = save_user_prompt(content)
    if result.get("error"):
        return result
    return result


@router.delete("/prompts")
async def reset_prompt():
    return clear_user_prompt()


@router.get("/voice-settings")
async def get_voice_settings():
    return get_voice_settings_state()


@router.put("/voice-settings")
async def update_voice_settings(request: Request):
    data = await request.json()
    result = save_voice_settings(data)
    if result.get("error"):
        return result
    return result


@router.delete("/voice-settings")
async def reset_voice_settings_route():
    return reset_voice_settings()


@router.post("/voice-settings/preview")
async def preview_voice(request: Request):
    data = await request.json()
    text = (data.get("text") or "").strip()
    if not text:
        from common.voice_settings import PREVIEW_SAMPLE

        text = PREVIEW_SAMPLE
    try:
        wav = synthesize_tts_bytes(
            text,
            speaker=data.get("speaker"),
            language_code=data.get("language_code"),
            model=data.get("tts_model"),
            pace=data.get("pace"),
            pitch=data.get("pitch"),
            loudness=data.get("loudness"),
            enable_preprocessing=data.get("enable_preprocessing"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TTS preview failed: {exc}")
    if not wav:
        raise HTTPException(status_code=502, detail="No audio returned from Sarvam TTS")
    return Response(content=wav, media_type="audio/wav")


@router.get("/configuration")
async def get_configuration():
    return get_system_configuration()


@router.get("/integrations")
async def get_integrations():
    return get_integrations_summary()


@router.get("/stack")
async def get_stack():
    return get_active_stack()


@router.post("/stack")
async def switch_stack(request: Request):
    data = await request.json()
    stack_id = data.get("stack_id")
    if not stack_id:
        return {"error": "stack_id is required"}
    return set_active_stack(stack_id)


@router.get("/stats")
async def get_stats():
    return dashboard_stats()


@router.get("/calls")
async def get_calls(
    limit: int = 50,
    status: Optional[str] = None,
    lead: Optional[str] = None,
    search: Optional[str] = None,
):
    return {"calls": list_dashboard_calls(limit=limit, status=status, lead=lead, search=search)}


@router.get("/calls/{internal_id}")
async def get_call_detail(internal_id: str):
    detail = get_dashboard_call(internal_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Call not found")
    return detail


@router.get("/tasks")
async def get_tasks(limit: int = 50, status: Optional[str] = None):
    return {"tasks": list_scheduled_tasks(limit=limit, status=status)}


@router.get("/recordings/{filename}")
async def get_recording(filename: str):
    path = resolve_recording_path(filename)
    if not path:
        raise HTTPException(status_code=404, detail="Recording not found")
    return FileResponse(path, media_type="audio/mpeg", filename=path.name)


@router.post("/schedule-call")
async def schedule_single_call(request: Request):
    data = await request.json()
    to_phone_number = data.get("to")
    if not to_phone_number:
        return {"error": "Phone number is required"}
    result = create_scheduled_call_record(
        to_phone_number=to_phone_number,
        internal_id=data.get("internal_id", ""),
        filename="dashboard",
        name=data.get("name", ""),
    )
    if result.get("error"):
        return result
    task = create_task(request.url.hostname, "process-scheduled-calls", {}, 20)
    return {
        **result,
        "message": "Call scheduled",
        "task_created": task is not None,
    }


@router.post("/run-direct-call")
async def run_direct_call(request: Request):
    from uuid import uuid4

    from common.functions import log_call_to_firestore_initiated
    from common.post_call import link_call_uuid, register_call
    from common.telephony import create_outbound_call
    from common.config import WEB_SERVER_URL

    data = await request.json()
    to_phone_number = data.get("to")
    if not to_phone_number:
        return {"error": "Phone number is required"}
    internal_id = data.get("internal_id") or str(uuid4())
    register_call(internal_id, to_phone_number)
    result = create_outbound_call(to_phone_number, internal_id)
    if result.get("call_sid"):
        link_call_uuid(result["call_sid"], internal_id)
        log_call_to_firestore_initiated(result["call_sid"], to_phone_number, internal_id)
        result["report_url"] = f"{WEB_SERVER_URL.rstrip('/')}/call/report/{internal_id}"
    result["internal_id"] = internal_id
    return result


@router.post("/schedule-batch")
async def schedule_batch(request: Request, file: UploadFile):
    import os

    import pandas as pd

    file_path = Path("uploads") / file.filename
    allowed_extensions = [".xlsx", ".xls", ".xlsm"]
    if Path(file.filename).suffix.lower() not in allowed_extensions:
        return {"filename": file.filename, "message": "Only Excel files allowed."}

    os.makedirs(file_path.parent, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    df = pd.read_excel(file_path)
    scheduled = 0
    for _, row in df.iterrows():
        create_scheduled_call_record(
            to_phone_number=row.get("phonenumber"),
            filename=file.filename,
            internal_id=str(row.get("internal_id") or ""),
            name=row.get("name", "Unknown"),
        )
        scheduled += 1

    file_path.unlink()
    task = create_task(request.url.hostname, "process-scheduled-calls", {}, 20)
    return {
        "filename": file.filename,
        "scheduled": scheduled,
        "message": f"Scheduled {scheduled} calls",
        "task_created": task is not None,
    }


@router.post("/run-batch")
async def run_batch(request: Request):
    task = create_task(request.url.hostname, "process-scheduled-calls", {}, 5)
    if task is None:
        return {"error": "Failed to create processing task"}
    return {"message": "Batch processing started", "task_name": task.name}
