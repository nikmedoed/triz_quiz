"""Utilities for rendering rich text blocks in templates."""
from __future__ import annotations

import re
from typing import Any, Dict

from markupsafe import Markup, escape

_PARAGRAPH_RE = re.compile(r"(?:\r?\n){2,}")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_LIST_LINE_RE = re.compile(r"^\s*-\s*(.+)$")


def _format_inline(text: str) -> str:
    escaped = escape(text)
    return _BOLD_RE.sub(lambda match: f"<strong>{match.group(1)}</strong>", escaped)


def _render_paragraph(lines: list[str]) -> str:
    combined = "\n".join(lines)
    formatted = _format_inline(combined).replace("\n", "<br>")
    return f"<p>{formatted}</p>"


def _render_list(items: list[str]) -> str:
    items_html = "".join(f"<li>{_format_inline(item)}</li>" for item in items)
    return f"<ul>{items_html}</ul>"


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

        lines = paragraph.split("\n")
        plain_lines: list[str] = []
        list_items: list[str] = []

        def flush_plain() -> None:
            nonlocal plain_lines
            if plain_lines:
                html_parts.append(_render_paragraph(plain_lines))
                plain_lines = []

        def flush_list() -> None:
            nonlocal list_items
            if list_items:
                html_parts.append(_render_list(list_items))
                list_items = []

        for line in lines:
            list_match = _LIST_LINE_RE.match(line)
            if list_match:
                flush_plain()
                list_items.append(list_match.group(1).strip())
            else:
                flush_list()
                plain_lines.append(line)

        flush_plain()
        flush_list()

    html = Markup("".join(html_parts))
    is_multi = len(paragraphs) > 1 or has_manual_breaks
    return {"html": html, "has_text": True, "is_multi": is_multi}
