"""Dashboard data aggregation for call logs, lead status, and scheduled tasks."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from common.config import CALL_RECORDINGS_DIR
from common.post_call import REPORTS_DIR, load_report

LEAD_TEMPERATURE_MAP = {
    "Potential Customer": "hot",
    "May be Potential Customer": "warm",
    "Not a Potential Customer": "cold",
    "Random Conversation": "cold",
    "Unknown": "unclassified",
    "unknown": "unclassified",
}


def lead_temperature(conversation_flag: Optional[str]) -> str:
    if not conversation_flag:
        return "unclassified"
    return LEAD_TEMPERATURE_MAP.get(conversation_flag, "unclassified")


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _report_sort_key(report: dict) -> float:
    for field in ("ended_at", "started_at", "exported_at"):
        dt = _parse_iso(report.get(field))
        if dt:
            return dt.timestamp()
    return 0.0


def _load_json_file(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _collect_report_files() -> list[Path]:
    paths: list[Path] = []
    if REPORTS_DIR.exists():
        paths.extend(REPORTS_DIR.glob("*.json"))
    recordings_dir = Path(CALL_RECORDINGS_DIR)
    if recordings_dir.exists():
        paths.extend(recordings_dir.glob("*.json"))
    return paths


def _merge_reports(reports: list[dict]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for report in reports:
        internal_id = report.get("internal_id")
        if not internal_id:
            basename = report.get("local_export_basename")
            if basename:
                internal_id = basename
            else:
                continue
        existing = merged.get(internal_id)
        if not existing or _report_sort_key(report) >= _report_sort_key(existing):
            merged[internal_id] = report
    return merged


def load_all_reports() -> list[dict]:
    reports: list[dict] = []
    for path in _collect_report_files():
        if path.name == "_index.json":
            continue
        data = _load_json_file(path)
        if data:
            reports.append(data)
    merged = _merge_reports(reports)
    return sorted(merged.values(), key=_report_sort_key, reverse=True)


def _firestore_call_metadata(phone: str, internal_id: str) -> dict:
    try:
        from google.cloud import firestore

        db = firestore.Client()
        parent = db.collection("conversation-history").document(phone).get()
        call_doc = (
            db.collection("conversation-history")
            .document(phone)
            .collection("calls")
            .document(internal_id)
            .get()
        )
        result: dict[str, Any] = {}
        if parent.exists:
            parent_data = parent.to_dict() or {}
            result["name"] = parent_data.get("name")
            result["process_status"] = parent_data.get("process_status")
            result["scheduled_at"] = _serialize_timestamp(parent_data.get("scheduled_at"))
            result["executive_summary"] = parent_data.get("executive_summary")
        if call_doc.exists:
            call_data = call_doc.to_dict() or {}
            result["conversation_flag"] = call_data.get("conversation_flag")
            result["conversation_summary"] = call_data.get("conversation_summary")
            result["executive_summary"] = call_data.get("executive_summary") or result.get("executive_summary")
            result["dangerous_content"] = call_data.get("dangerous_content")
            result["telephony_status"] = call_data.get("status")
            result["retry_count"] = call_data.get("retry_count", 0)
        return result
    except Exception as exc:
        print(f"[dashboard] Firestore enrichment skipped: {exc}")
        return {}


def _serialize_timestamp(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _summarize_call(report: dict, firestore_meta: Optional[dict] = None) -> dict:
    hangup = report.get("hangup") or {}
    recording = report.get("recording") or {}
    phone = report.get("to_phone_number") or report.get("phone_number") or ""
    internal_id = report.get("internal_id") or ""
    meta = firestore_meta or _firestore_call_metadata(phone, internal_id)
    conversation_flag = meta.get("conversation_flag") or report.get("conversation_flag")
    local_recording = recording.get("local_file") or report.get("local_recording_file")
    recording_filename = Path(local_recording).name if local_recording else None

    return {
        "internal_id": internal_id,
        "name": meta.get("name"),
        "to_phone_number": phone,
        "from_phone_number": hangup.get("From"),
        "started_at": report.get("started_at"),
        "ended_at": report.get("ended_at"),
        "duration_seconds": report.get("duration_seconds"),
        "status": report.get("status") or hangup.get("CallStatus"),
        "telephony_status": meta.get("telephony_status") or hangup.get("CallStatus"),
        "direction": hangup.get("Direction", "outbound"),
        "hangup_cause": hangup.get("HangupCauseName") or hangup.get("HangupCause"),
        "hangup_source": hangup.get("HangupSource"),
        "cost": hangup.get("TotalCost"),
        "conversation_flag": conversation_flag,
        "lead_temperature": lead_temperature(conversation_flag),
        "conversation_summary": meta.get("conversation_summary") or report.get("conversation_summary"),
        "executive_summary": meta.get("executive_summary") or report.get("executive_summary"),
        "dangerous_content": meta.get("dangerous_content"),
        "retry_count": meta.get("retry_count", 0),
        "process_status": meta.get("process_status"),
        "has_recording": bool(recording.get("url") or recording_filename),
        "recording_url": recording.get("url"),
        "recording_filename": recording_filename,
        "local_json_file": report.get("local_json_file"),
        "qa_count": len(report.get("qa_pairs") or []),
        "transcript_count": len(report.get("transcript") or []),
    }


def list_dashboard_calls(
    limit: int = 50,
    status: Optional[str] = None,
    lead: Optional[str] = None,
    search: Optional[str] = None,
) -> list[dict]:
    results = []
    for report in load_all_reports():
        phone = report.get("to_phone_number") or report.get("phone_number") or ""
        internal_id = report.get("internal_id") or ""
        summary = _summarize_call(report)
        if status and summary.get("status") != status and summary.get("telephony_status") != status:
            continue
        if lead and summary.get("lead_temperature") != lead:
            continue
        if search:
            haystack = " ".join(
                filter(
                    None,
                    [
                        phone,
                        internal_id,
                        summary.get("name") or "",
                        summary.get("hangup_cause") or "",
                        summary.get("conversation_flag") or "",
                    ],
                )
            ).lower()
            if search.lower() not in haystack:
                continue
        results.append(summary)
        if len(results) >= limit:
            break
    return results


def get_dashboard_call(internal_id: str) -> Optional[dict]:
    report = load_report(internal_id)
    if not report:
        for path in _collect_report_files():
            if path.name == "_index.json":
                continue
            data = _load_json_file(path)
            if data and data.get("internal_id") == internal_id:
                report = data
                break
    if not report:
        return None
    phone = report.get("to_phone_number") or report.get("phone_number") or ""
    meta = _firestore_call_metadata(phone, internal_id)
    summary = _summarize_call(report, meta)
    return {
        **summary,
        "transcript": report.get("transcript") or [],
        "qa_pairs": report.get("qa_pairs") or [],
        "hangup": report.get("hangup"),
        "recording": report.get("recording"),
        "conversation_id": report.get("conversation_id"),
        "call_uuid": report.get("call_uuid"),
    }


def dashboard_stats() -> dict:
    calls = list_dashboard_calls(limit=500)
    lead_counts = {"hot": 0, "warm": 0, "cold": 0, "unclassified": 0}
    status_counts: dict[str, int] = {}
    for call in calls:
        lead_counts[call.get("lead_temperature", "unclassified")] = (
            lead_counts.get(call.get("lead_temperature", "unclassified"), 0) + 1
        )
        status = call.get("telephony_status") or call.get("status") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    tasks = list_scheduled_tasks(limit=200)
    scheduled_count = sum(1 for t in tasks if t.get("process_status") == "scheduled")
    initiated_count = sum(1 for t in tasks if t.get("process_status") == "initiated")
    return {
        "total_calls": len(calls),
        "with_recording": sum(1 for c in calls if c.get("has_recording")),
        "lead_counts": lead_counts,
        "status_counts": status_counts,
        "scheduled_tasks": scheduled_count,
        "initiated_tasks": initiated_count,
    }


def list_scheduled_tasks(limit: int = 50, status: Optional[str] = None) -> list[dict]:
    try:
        from google.cloud import firestore

        db = firestore.Client()
        query = db.collection("conversation-history")
        if status:
            query = query.where("process_status", "==", status)
        docs = query.limit(limit).stream()
        tasks = []
        for doc in docs:
            data = doc.to_dict() or {}
            tasks.append(
                {
                    "phone_number": doc.id,
                    "name": data.get("name"),
                    "to_phone_number": data.get("to_phone_number") or doc.id,
                    "process_status": data.get("process_status"),
                    "scheduled_at": _serialize_timestamp(data.get("scheduled_at")),
                    "initiated_at": _serialize_timestamp(data.get("initiated_at")),
                    "last_internal_id": data.get("last_internal_id"),
                    "retry_count": data.get("retry_count", 0),
                    "filename": data.get("filename"),
                    "executive_summary": data.get("executive_summary"),
                }
            )
        tasks.sort(key=lambda t: t.get("scheduled_at") or "", reverse=True)
        return tasks
    except Exception as exc:
        print(f"[dashboard] Firestore task list skipped: {exc}")
        return []


def resolve_recording_path(filename: str) -> Optional[Path]:
    safe_name = Path(filename).name
    if safe_name != filename:
        return None
    recordings_dir = Path(CALL_RECORDINGS_DIR)
    candidate = recordings_dir / safe_name
    if candidate.exists() and candidate.is_file():
        return candidate
    return None
