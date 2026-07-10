"""Monica cold-call flow: intro + 6 questions, tracked to prevent repeats."""
from __future__ import annotations

from typing import Any, Optional

from common.call_script import (
    QUESTION_COUNT,
    SHORT_ACKS,
    TOPIC_IDS,
    build_closing_from_answers,
    get_effective_call_script,
)


class MonicaConversationFlow:
    """Tracks intro + six answers — scripted turns from configurable call script."""

    def __init__(self, script: Optional[dict[str, Any]] = None) -> None:
        s = script or get_effective_call_script()
        self.intro = s["intro"]
        self.questions = list(s["questions"])
        self.topic_labels = list(s.get("topic_labels", []))
        self.closing_template = s.get("closing_template", "")
        self.answers: dict[str, str] = {}
        self.turn_index = 0

    def reset(self) -> None:
        self.answers = {}
        self.turn_index = 0

    def record_user_answer(self, text: str) -> None:
        text = (text or "").strip()
        if not text or self.turn_index >= QUESTION_COUNT:
            return
        key = TOPIC_IDS[self.turn_index]
        self.answers[key] = text
        self.turn_index += 1

    def all_collected(self) -> bool:
        return self.turn_index >= QUESTION_COUNT

    def build_greeting(self, custom_greeting: Optional[str] = None) -> str:
        if custom_greeting and custom_greeting.strip():
            return custom_greeting.strip()
        q0 = self.questions[0] if self.questions else ""
        return f"{self.intro.strip()} {q0}".strip()

    def build_reply_after_answer(self) -> str:
        if self.all_collected():
            return self.build_closing_summary()
        ack = SHORT_ACKS[(self.turn_index - 1) % len(SHORT_ACKS)]
        return f"{ack} {self.questions[self.turn_index]}"

    def build_closing_summary(self) -> str:
        script = {
            "intro": self.intro,
            "questions": self.questions,
            "topic_labels": self.topic_labels,
            "closing_template": self.closing_template,
        }
        return build_closing_from_answers(self.answers, script)

    def llm_context(self) -> str:
        lines = ["CALL PROGRESS (internal — never read aloud):"]
        for i in range(QUESTION_COUNT):
            key = TOPIC_IDS[i]
            label = self.topic_labels[i] if i < len(self.topic_labels) else key
            if key in self.answers:
                lines.append(f"- {label}: ✓ collected")
            elif i == self.turn_index:
                lines.append(f"- {label}: waiting for caller")
            else:
                lines.append(f"- {label}: pending")
        if self.all_collected():
            lines.append("All six answers collected — closing summary only.")
        return "\n".join(lines)

    def state_snapshot(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "total_questions": QUESTION_COUNT,
            "answers": dict(self.answers),
            "all_collected": self.all_collected(),
            "next_question": self.questions[self.turn_index] if not self.all_collected() else None,
        }
