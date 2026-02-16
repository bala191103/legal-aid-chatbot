"""
Language Utilities - Detect input language and translate responses
Supports English and Tamil (Unicode) only.
"""

from __future__ import annotations

import re
from typing import Optional


TAMIL_UNICODE_RE = re.compile(r"[\u0B80-\u0BFF]")


def detect_language(text: str) -> str:
    """
    Detect the user's input language.
    Returns: "en" or "ta". Defaults to English when uncertain.
    """
    if TAMIL_UNICODE_RE.search(text):
        return "ta"
    return "en"


def translate_response(text: str, target_language: str, llm_handler: Optional[object]) -> str:
    """
    Translate a response into Tamil using the existing LLM handler.
    Translation happens only at the final response stage when requested.
    """
    if target_language != "ta":
        return text
    if llm_handler is None:
        return text

    try:
        return llm_handler.translate_text(text, target_language)
    except Exception:
        return text
