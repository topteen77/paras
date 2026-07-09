"""System prompt: default file + optional user override."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from common.config import SARVAM_SYSTEM_PROMPT_PATH

USER_PROMPT_PATH = Path("uploads/custom_system_prompt.txt")
BUILTIN_FALLBACK = (
    "You are Monica, study abroad assistant for Canam Consultants. "
    "Collect country, study level, timeline, location, callback time. "
    "Keep replies under 2 sentences. "
    "End closing messages with Goodbye or अलविदा — the call hangs up automatically."
)


def _read_text(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _file_meta(path: Path, content: str) -> dict[str, Any]:
    exists = path.is_file()
    modified_at = None
    if exists:
        try:
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        except Exception:
            pass
    return {
        "path": str(path),
        "exists": exists,
        "modified_at": modified_at,
        "char_count": len(content),
        "line_count": content.count("\n") + (1 if content and not content.endswith("\n") else 0),
    }


def get_default_prompt() -> str:
    content = _read_text(Path(SARVAM_SYSTEM_PROMPT_PATH))
    return content if content is not None else BUILTIN_FALLBACK


def get_user_prompt() -> Optional[str]:
    content = _read_text(USER_PROMPT_PATH)
    if content is None:
        return None
    stripped = content.strip()
    return stripped if stripped else None


def get_effective_prompt(executive_summary: str = "") -> str:
    user_prompt = get_user_prompt()
    base = user_prompt if user_prompt else get_default_prompt()
    if executive_summary and executive_summary != "No executive summary available":
        return f"{base}\n\nPrior context:\n{executive_summary}"
    return base


def get_prompt_state() -> dict[str, Any]:
    default_text = get_default_prompt()
    user_text = get_user_prompt()
    using = "user" if user_text else "default"
    effective = user_text if user_text else default_text

    return {
        "using": using,
        "default": {
            "content": default_text,
            **_file_meta(Path(SARVAM_SYSTEM_PROMPT_PATH), default_text),
            "label": "Default prompt",
            "description": "Shipped with the app. Update the file in the repo to change the baseline.",
        },
        "user": {
            "content": user_text or "",
            "has_override": bool(user_text),
            **_file_meta(USER_PROMPT_PATH, user_text or ""),
            "label": "Your custom prompt",
            "description": "Saved in uploads — overrides the default for all new Sarvam calls.",
        },
        "effective_preview": effective,
        "effective_char_count": len(effective),
    }


def save_user_prompt(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        return {"error": "Prompt cannot be empty. Use reset to clear your override."}

    USER_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_PROMPT_PATH.write_text(text + "\n", encoding="utf-8")
    return {
        "message": "Custom prompt saved",
        "using": "user",
        **get_prompt_state(),
    }


def clear_user_prompt() -> dict[str, Any]:
    if USER_PROMPT_PATH.exists():
        USER_PROMPT_PATH.unlink()
    return {
        "message": "Reverted to default prompt",
        "using": "default",
        **get_prompt_state(),
    }
