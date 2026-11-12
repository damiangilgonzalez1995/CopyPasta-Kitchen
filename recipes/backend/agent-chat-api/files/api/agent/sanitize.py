"""Text of the question before it reaches the graph. Trim, length, control characters, tags."""

import re

from fastapi import HTTPException, status

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # keeps \n and \t
_HTML_TAGS = re.compile(r"<[^>]+>")


def sanitize_question(question: str, *, max_length: int) -> str:
    """Clean question or 400. Prompt-injection detection, if any, goes here as a log, not a block."""
    question = question.strip()
    if not question:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The question cannot be empty.")
    if len(question) > max_length:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"The question exceeds {max_length} characters.")
    question = _CONTROL_CHARS.sub("", question)
    question = _HTML_TAGS.sub("", question).strip()
    if not question:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The question cannot be empty.")
    return question
