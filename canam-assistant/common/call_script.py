"""Configurable call script: intro, questions, closing — used in prompts and live calls."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

CALL_SCRIPT_PATH = Path("uploads/call_script.json")
QUESTION_COUNT = 6

TOPIC_IDS = [
    "country",
    "other_countries",
    "study_level",
    "timeline",
    "location",
    "callback",
]

DEFAULT_TOPIC_LABELS = [
    "Primary country of interest",
    "Other countries or none",
    "Level of study",
    "Preferred start timeline",
    "Caller city or region",
    "Callback day and time",
]

DEFAULT_INTRO = (
    "Hello, thank you for calling Canam Consultants. "
    "I am Monica, your study abroad advisor."
)

DEFAULT_QUESTIONS = [
    "Which country are you most interested in studying in?",
    "Apart from that, any other countries you would like to explore, or just the one?",
    "What level of study are you planning — Masters, Bachelors, or something else?",
    "When would you like to start — this year or next year?",
    "Which city or region are you calling from?",
    "What day and time works best for a counsellor to call you back?",
]

DEFAULT_CLOSING_TEMPLATE = (
    "Thank you. To confirm: {country}{other_part}, {level} starting {timeline}, "
    "from {location}, callback {callback}. Our counsellor will reach out. Goodbye."
)

SAMPLE_ANSWERS = [
    "Canada",
    "none",
    "Masters",
    "next year",
    "Mumbai",
    "Monday at 4 PM",
]

SHORT_ACKS = ("Certainly.", "Got it.", "Thank you.", "Understood.", "Noted.", "Perfect.")


def _defaults() -> dict[str, Any]:
    return {
        "intro": DEFAULT_INTRO,
        "questions": list(DEFAULT_QUESTIONS),
        "topic_labels": list(DEFAULT_TOPIC_LABELS),
        "closing_template": DEFAULT_CLOSING_TEMPLATE,
    }


def _read_saved() -> dict[str, Any]:
    if not CALL_SCRIPT_PATH.is_file():
        return {}
    try:
        return json.loads(CALL_SCRIPT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _normalize_questions(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return list(DEFAULT_QUESTIONS)
    cleaned = [str(q).strip() for q in raw if str(q).strip()]
    while len(cleaned) < QUESTION_COUNT:
        cleaned.append(DEFAULT_QUESTIONS[len(cleaned)])
    return cleaned[:QUESTION_COUNT]


def get_effective_call_script() -> dict[str, Any]:
    merged = _defaults()
    saved = _read_saved()
    if saved.get("intro"):
        merged["intro"] = str(saved["intro"]).strip()
    if saved.get("questions"):
        merged["questions"] = _normalize_questions(saved["questions"])
    if saved.get("topic_labels"):
        labels = [str(l).strip() for l in saved["topic_labels"] if str(l).strip()]
        while len(labels) < QUESTION_COUNT:
            labels.append(DEFAULT_TOPIC_LABELS[len(labels)])
        merged["topic_labels"] = labels[:QUESTION_COUNT]
    if saved.get("closing_template"):
        merged["closing_template"] = str(saved["closing_template"]).strip()
    return merged


def build_call_preview(script: Optional[dict[str, Any]] = None) -> str:
    """Full call walkthrough with sample answers for the dashboard."""
    s = script or get_effective_call_script()
    intro = s["intro"].strip()
    questions = _normalize_questions(s.get("questions"))
    labels = s.get("topic_labels") or DEFAULT_TOPIC_LABELS
    lines: list[str] = []

    lines.append("--- CALL PREVIEW (sample answers) ---")
    lines.append(f"Monica: {intro} {questions[0]}")
    for i in range(QUESTION_COUNT):
        sample = SAMPLE_ANSWERS[i] if i < len(SAMPLE_ANSWERS) else f"[answer {i + 1}]"
        lines.append(f"You: {sample}")
        if i < QUESTION_COUNT - 1:
            ack = SHORT_ACKS[i % len(SHORT_ACKS)]
            lines.append(f"Monica: {ack} {questions[i + 1]}")
        else:
            lines.append(f"Monica: {build_closing_from_answers(dict(zip(TOPIC_IDS, SAMPLE_ANSWERS)), s)}")
    lines.append("--- END ---")
    return "\n".join(lines)


def build_closing_from_answers(answers: dict[str, str], script: Optional[dict[str, Any]] = None) -> str:
    s = script or get_effective_call_script()
    template = s.get("closing_template") or DEFAULT_CLOSING_TEMPLATE
    country = answers.get("country", "")
    other = answers.get("other_countries", "none")
    level = answers.get("study_level", "")
    timeline = answers.get("timeline", "")
    location = answers.get("location", "")
    callback = answers.get("callback", "")
    other_part = f", also {other}" if other and other.lower() not in ("none", "no", "just one") else ""
    try:
        text = template.format(
            country=country,
            other=other,
            other_part=other_part,
            level=level,
            timeline=timeline,
            location=location,
            callback=callback,
        )
    except (KeyError, ValueError):
        text = DEFAULT_CLOSING_TEMPLATE.format(
            country=country,
            other_part=other_part,
            level=level,
            timeline=timeline,
            location=location,
            callback=callback,
        )
    text = text.strip()
    if "goodbye" not in text.lower() and "अलविदा" not in text:
        text = f"{text.rstrip('.!? ')}. Goodbye."
    return text


def build_prompt_script_block(script: Optional[dict[str, Any]] = None) -> str:
    s = script or get_effective_call_script()
    lines = [
        "# Configured call script (follow exactly — one question per turn):",
        f"INTRO (spoken once at call start): {s['intro'].strip()}",
        "QUESTIONS (in order, never repeat):",
    ]
    labels = s.get("topic_labels") or DEFAULT_TOPIC_LABELS
    for i, q in enumerate(_normalize_questions(s.get("questions")), 1):
        label = labels[i - 1] if i <= len(labels) else f"Question {i}"
        lines.append(f"  {i}. {label}: {q}")
    lines.append(
        "CLOSING: After all answers, one confirmation sentence using collected details, then Goodbye."
    )
    return "\n".join(lines)


def get_call_script_state() -> dict[str, Any]:
    effective = get_effective_call_script()
    return {
        "effective": effective,
        "intro": effective["intro"],
        "questions": effective["questions"],
        "topic_labels": effective["topic_labels"],
        "closing_template": effective["closing_template"],
        "call_preview": build_call_preview(effective),
        "prompt_block": build_prompt_script_block(effective),
        "saved_path": str(CALL_SCRIPT_PATH),
        "has_saved_override": CALL_SCRIPT_PATH.is_file(),
        "question_count": QUESTION_COUNT,
    }


def save_call_script(payload: dict[str, Any]) -> dict[str, Any]:
    intro = (payload.get("intro") or "").strip()
    if not intro:
        return {"error": "Intro text is required."}

    questions = _normalize_questions(payload.get("questions"))
    if not all(questions):
        return {"error": "All six questions must be filled in."}

    labels_raw = payload.get("topic_labels")
    if isinstance(labels_raw, list) and labels_raw:
        topic_labels = [str(l).strip() or DEFAULT_TOPIC_LABELS[i] for i, l in enumerate(labels_raw)]
        while len(topic_labels) < QUESTION_COUNT:
            topic_labels.append(DEFAULT_TOPIC_LABELS[len(topic_labels)])
        topic_labels = topic_labels[:QUESTION_COUNT]
    else:
        topic_labels = list(DEFAULT_TOPIC_LABELS)

    closing = (payload.get("closing_template") or DEFAULT_CLOSING_TEMPLATE).strip()

    saved = {
        "intro": intro,
        "questions": questions,
        "topic_labels": topic_labels,
        "closing_template": closing,
    }
    CALL_SCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALL_SCRIPT_PATH.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
    return {"message": "Call script saved", **get_call_script_state()}


def reset_call_script() -> dict[str, Any]:
    if CALL_SCRIPT_PATH.exists():
        CALL_SCRIPT_PATH.unlink()
    return {"message": "Call script reset to defaults", **get_call_script_state()}
