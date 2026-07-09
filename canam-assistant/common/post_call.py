"""Post-call report: transcript, Q&A, Plivo recording, local JSON export."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import requests

from common.config import (
    CALL_RECORDINGS_DIR,
    PLIVO_AUTH_ID,
    PLIVO_AUTH_TOKEN,
    POST_CALL_WEBHOOK_URL,
    WEB_SERVER_URL,
)

REPORTS_DIR = Path("uploads/call_reports")
INDEX_FILE = REPORTS_DIR / "_index.json"
RECORDINGS_DIR = Path(CALL_RECORDINGS_DIR)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _phone_slug(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    return digits or "unknown"


def _timestamp_slug(iso_time: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
        return dt.strftime("%Y%m%d_%H%M%S")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _local_basename(report: dict) -> str:
    if report.get("local_export_basename"):
        return report["local_export_basename"]
    phone = report.get("to_phone_number") or "unknown"
    started = report.get("started_at") or _utc_now()
    basename = f"{_phone_slug(phone)}_{_timestamp_slug(started)}"
    report["local_export_basename"] = basename
    return basename


def _load_index() -> dict:
    if not INDEX_FILE.exists():
        return {}
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_index(index: dict) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")


def _report_path(internal_id: str) -> Path:
    return REPORTS_DIR / f"{internal_id}.json"


def register_call(internal_id: str, to_phone_number: str, call_uuid: str = "") -> dict:
    """Create an empty report shell when a call is initiated."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "internal_id": internal_id,
        "to_phone_number": to_phone_number,
        "call_uuid": call_uuid,
        "status": "initiated",
        "started_at": _utc_now(),
        "ended_at": None,
        "transcript": [],
        "qa_pairs": [],
        "recording": None,
        "hangup": None,
        "delivered": False,
        "local_export_basename": None,
        "local_json_file": None,
        "local_recording_file": None,
        "report_url": f"{WEB_SERVER_URL.rstrip('/')}/call/report/{internal_id}",
    }
    _report_path(internal_id).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if call_uuid:
        index = _load_index()
        index[call_uuid] = internal_id
        _save_index(index)
    return report


def link_call_uuid(call_uuid: str, internal_id: str) -> None:
    if not call_uuid or not internal_id:
        return
    report = load_report(internal_id)
    if report:
        report["call_uuid"] = call_uuid
        save_report(report)
    index = _load_index()
    index[call_uuid] = internal_id
    _save_index(index)


def internal_id_for_call_uuid(call_uuid: str) -> Optional[str]:
    return _load_index().get(call_uuid)


def resolve_internal_id(hangup_payload: dict) -> Optional[str]:
    """Map Plivo hangup payload to our internal call id."""
    call_uuid = hangup_payload.get("CallUUID") or hangup_payload.get("call_uuid") or ""
    if call_uuid:
        internal_id = internal_id_for_call_uuid(call_uuid)
        if internal_id:
            return internal_id

    candidate_phones = [
        hangup_payload.get("To"),
        hangup_payload.get("From"),
        hangup_payload.get("to"),
        hangup_payload.get("from"),
    ]
    return _latest_open_report_for_phones(candidate_phones)


def _latest_open_report_for_phones(phones: list) -> Optional[str]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    slugs = {_phone_slug(p) for p in phones if p}
    if not slugs:
        return None

    best_id = None
    best_mtime = 0.0
    for path in REPORTS_DIR.glob("*.json"):
        if path.name == "_index.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("status") == "exported" and data.get("local_json_file"):
            continue
        report_slug = _phone_slug(data.get("to_phone_number", ""))
        if report_slug not in slugs:
            continue
        mtime = path.stat().st_mtime
        if mtime > best_mtime:
            best_mtime = mtime
            best_id = data.get("internal_id")
    return best_id


def load_report(internal_id: str) -> Optional[dict]:
    path = _report_path(internal_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_report(report: dict) -> None:
    internal_id = report.get("internal_id")
    if not internal_id:
        return
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _report_path(internal_id).write_text(json.dumps(report, indent=2), encoding="utf-8")


def build_qa_pairs(messages: list) -> list[dict]:
    pairs = []
    pending_user = None
    for msg in messages:
        role = msg.get("role")
        content = (msg.get("content") or msg.get("text") or "").strip()
        if not content or role == "system":
            continue
        if role == "user":
            pending_user = content
        elif role == "assistant":
            pairs.append({
                "user_question": pending_user or "",
                "agent_answer": content,
            })
            pending_user = None
    return pairs


def _build_export_payload(report: dict) -> dict:
    recording = report.get("recording") or {}
    return {
        "phone_number": report.get("to_phone_number"),
        "internal_id": report.get("internal_id"),
        "call_uuid": report.get("call_uuid"),
        "conversation_id": report.get("conversation_id"),
        "status": report.get("status"),
        "started_at": report.get("started_at"),
        "ended_at": report.get("ended_at"),
        "duration_seconds": report.get("duration_seconds"),
        "qa_pairs": report.get("qa_pairs", []),
        "transcript": report.get("transcript", []),
        "recording": {
            "url": recording.get("url"),
            "recording_id": recording.get("recording_id"),
            "duration_seconds": recording.get("duration_seconds"),
            "local_file": report.get("local_recording_file"),
        },
        "hangup": report.get("hangup"),
        "exported_at": _utc_now(),
    }


def _download_recording(recording_url: str, dest_path: Path) -> bool:
    if not recording_url:
        return False
    try:
        auth = None
        if PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN:
            auth = (PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)
        resp = requests.get(recording_url, auth=auth, timeout=60)
        resp.raise_for_status()
        dest_path.write_bytes(resp.content)
        return True
    except Exception as exc:
        print(f"[POST_CALL] recording download failed: {exc}")
        return False


def export_local_recording(report: dict) -> Optional[Path]:
    """Write call-recordings/{phone}_{timestamp}.json (+ optional .mp3)."""
    has_content = (
        report.get("transcript")
        or report.get("qa_pairs")
        or report.get("hangup")
        or (report.get("recording") or {}).get("url")
    )
    if not has_content:
        return None

    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    basename = _local_basename(report)
    json_path = RECORDINGS_DIR / f"{basename}.json"

    recording = report.get("recording") or {}
    recording_url = recording.get("url")
    if recording_url and not report.get("local_recording_file"):
        audio_path = RECORDINGS_DIR / f"{basename}.mp3"
        if _download_recording(recording_url, audio_path):
            report["local_recording_file"] = str(audio_path)
            recording["local_file"] = str(audio_path)

    payload = _build_export_payload(report)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    report["local_json_file"] = str(json_path)
    report["status"] = "exported"
    save_report(report)
    print(f"[POST_CALL] saved local report → {json_path}")
    return json_path


def save_transcript(internal_id: str, conversation: dict) -> dict:
    report = load_report(internal_id) or register_call(internal_id, "", "")
    messages = conversation.get("transcript") or []
    report["transcript"] = messages
    report["qa_pairs"] = conversation.get("qa_pairs") or build_qa_pairs(
        [{"role": m.get("role"), "content": m.get("text") or m.get("content")} for m in messages]
    )
    report["conversation_id"] = conversation.get("conversation_id", "")
    if report.get("status") == "initiated":
        report["status"] = "transcript_saved"
    save_report(report)
    export_local_recording(report)
    try_deliver_report(internal_id)
    return report


def save_hangup_data(internal_id: str, hangup_payload: dict) -> dict:
    report = load_report(internal_id) or register_call(
        internal_id,
        hangup_payload.get("To") or hangup_payload.get("From") or "",
        "",
    )
    if not report.get("to_phone_number"):
        report["to_phone_number"] = (
            hangup_payload.get("To")
            or hangup_payload.get("From")
            or report.get("to_phone_number")
            or ""
        )
    report["hangup"] = hangup_payload
    report["call_uuid"] = (
        hangup_payload.get("CallUUID")
        or hangup_payload.get("call_uuid")
        or report.get("call_uuid")
        or ""
    )
    report["ended_at"] = _utc_now()
    report["status"] = hangup_payload.get("CallStatus") or hangup_payload.get("Status") or "completed"
    duration = hangup_payload.get("Duration") or hangup_payload.get("BillDuration")
    if duration is not None:
        try:
            report["duration_seconds"] = int(duration)
        except (TypeError, ValueError):
            pass
    save_report(report)
    if report["call_uuid"]:
        link_call_uuid(report["call_uuid"], internal_id)
    export_local_recording(report)
    try_deliver_report(internal_id)
    return report


def save_recording_data(internal_id: str, recording_payload: dict) -> dict:
    report = load_report(internal_id) or register_call(internal_id, "", "")
    report["recording"] = {
        "url": recording_payload.get("RecordUrl") or recording_payload.get("record_url"),
        "recording_id": recording_payload.get("RecordingID") or recording_payload.get("recording_id"),
        "duration_seconds": recording_payload.get("RecordingDuration"),
        "received_at": _utc_now(),
    }
    save_report(report)
    export_local_recording(report)
    _send_webhook(report, event="recording_ready")
    return report


def recording_callback_url(internal_id: str) -> str:
    enc_id = quote(str(internal_id), safe="")
    return f"{WEB_SERVER_URL.rstrip('/')}/recording/ready/{enc_id}"


def try_deliver_report(internal_id: str) -> Optional[dict]:
    report = load_report(internal_id)
    if not report or report.get("delivered"):
        return report
    if not report.get("transcript") and not report.get("qa_pairs"):
        return report
    if not report.get("hangup") and report.get("status") not in ("completed", "transcript_saved", "exported"):
        if report.get("status") != "transcript_saved":
            return report
    return _send_webhook(report, event="call_completed")


def _send_webhook(report: dict, event: str = "call_completed") -> Optional[dict]:
    payload = _build_export_payload(report)
    payload["event"] = event

    print(
        f"[POST_CALL] event={event} internal_id={report.get('internal_id')} "
        f"qa_count={len(payload['qa_pairs'])} file={report.get('local_json_file')}"
    )

    if POST_CALL_WEBHOOK_URL:
        try:
            resp = requests.post(POST_CALL_WEBHOOK_URL, json=payload, timeout=15)
            print(f"[POST_CALL] webhook status={resp.status_code}")
            report["webhook_status"] = resp.status_code
        except Exception as exc:
            print(f"[POST_CALL] webhook error: {exc}")
            report["webhook_error"] = str(exc)

    if event == "call_completed":
        report["delivered"] = True
    save_report(report)
    return report


def list_reports(limit: int = 20) -> list[dict]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(REPORTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    results = []
    for path in files:
        if path.name == "_index.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            results.append({
                "internal_id": data.get("internal_id"),
                "to_phone_number": data.get("to_phone_number"),
                "status": data.get("status"),
                "ended_at": data.get("ended_at"),
                "local_json_file": data.get("local_json_file"),
                "local_recording_file": data.get("local_recording_file"),
                "report_url": data.get("report_url"),
                "has_recording": bool((data.get("recording") or {}).get("url")),
            })
        except Exception:
            continue
        if len(results) >= limit:
            break
    return results
