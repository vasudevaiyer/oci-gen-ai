from __future__ import annotations

import re
import unicodedata

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
ARABIC_RANGE_RE = re.compile(r"[\u0600-\u06FF]")


def contains_arabic(text: str) -> bool:
    return bool(ARABIC_RANGE_RE.search(text or ""))


def normalize_arabic_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u200f", "").replace("\u200e", "")
    text = text.translate(ARABIC_DIGITS)
    text = _normalize_bidi_numbers(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([،؛:.])", r"\1", text)
    text = re.sub(r"([(:])\s+", r"\1", text)
    text = re.sub(r"\s+([)])", r"\1", text)
    return text.strip()


def _normalize_bidi_numbers(text: str) -> str:
    def normalize_digits(digits: str) -> str:
        if len(digits) > 1 and digits.endswith("0"):
            return digits
        return digits[::-1]

    text = re.sub(
        r"(?m)(^|[ \t]*[-(]?[ \t]*)\.([0-9]{1,3})(?=\s|$)",
        lambda match: f"{match.group(1)}{normalize_digits(match.group(2))}.",
        text,
    )
    text = re.sub(
        r"(?<=\s)\.([0-9]{1,3})(?=[\u0600-\u06FF(]|$)",
        lambda match: f" {normalize_digits(match.group(1))} ",
        text,
    )
    text = re.sub(
        r"(?<=[\u0600-\u06FF])\.([0-9]{1,3})(?=[\u0600-\u06FF(]|$)",
        lambda match: f" {normalize_digits(match.group(1))} ",
        text,
    )
    text = re.sub(
        r"٪([0-9]{1,3})",
        lambda match: f"{normalize_digits(match.group(1))}٪",
        text,
    )
    return text
