"""Utilities for rendering rich text blocks in templates."""
from __future__ import annotations

import re
from typing import Any, Dict

from markupsafe import Markup, escape

_PARAGRAPH_RE = re.compile(r"(?:\r?\n){2,}")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def format_rich_text(value: str | None) -> Dict[str, Any]:
    """Return HTML markup and metadata for a description block."""
    if not value:
        empty = Markup("")
        return {"html": empty, "has_text": False, "is_multi": False}

    stripped = value.strip()
    if not stripped:
        empty = Markup("")
        return {"html": empty, "has_text": False, "is_multi": False}

    paragraphs = [part.strip() for part in _PARAGRAPH_RE.split(stripped) if part.strip()]
    if not paragraphs:
        empty = Markup("")
        return {"html": empty, "has_text": False, "is_multi": False}

    html_parts: list[str] = []
    has_manual_breaks = False
    for paragraph in paragraphs:
        if "\n" in paragraph:
            has_manual_breaks = True
        escaped = escape(paragraph)
        bolded = _BOLD_RE.sub(lambda match: f"<strong>{match.group(1)}</strong>", escaped)
        with_breaks = bolded.replace("\n", "<br>")
        html_parts.append(f"<p>{with_breaks}</p>")

    html = Markup("".join(html_parts))
    is_multi = len(paragraphs) > 1 or has_manual_breaks
    return {"html": html, "has_text": True, "is_multi": is_multi}
