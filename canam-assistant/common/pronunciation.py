"""TTS-only pronunciation fixes — transcript keeps original spelling."""
from __future__ import annotations

import re

# Applied before Sarvam TTS; tuned for Indian English telephony (bulbul:v2).
PRONUNCIATION_MAP: list[tuple[str, str]] = [
    (r"\bCanam Consultants\b", "Kay-nam Consultants"),
    (r"\bCanam\b", "Kay-nam"),
    (r"\bCanada\b", "Kanada"),
    (r"\bUK\b", "United Kingdom"),
    (r"\bUSA\b", "United States"),
    (r"\bUS\b", "United States"),
    (r"\bNew Zealand\b", "New Zee-land"),
    (r"\bAustralia\b", "Ostralia"),
    (r"\bGermany\b", "Jermany"),
    (r"\bIELTS\b", "I E L T S"),
    (r"\bTOEFL\b", "T O E F L"),
    (r"\bPTE\b", "P T E"),
    (r"\bGPA\b", "G P A"),
    (r"\bCGPA\b", "C G P A"),
    (r"\bMaster's\b", "Masters"),
    (r"\bMasters'\b", "Masters"),
    (r"\bBachelor's\b", "Bachelors"),
    (r"\bBachelors'\b", "Bachelors"),
    (r"\bcounsellors\b", "counsellors"),
    (r"\bcounsellor\b", "counsellor"),
]


def apply_pronunciation(text: str) -> str:
    if not text:
        return text
    out = text
    for pattern, replacement in PRONUNCIATION_MAP:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return out
