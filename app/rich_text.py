"""Utilities for rendering rich text blocks in templates."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Dict

from markupsafe import Markup, escape

_PARAGRAPH_RE = re.compile(r"(?:\r?\n){2,}")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_LIST_LINE_RE = re.compile(r"^\s*-\s*(.+)$")
_HTML_TAG_RE = re.compile(r"<[a-zA-Z][^>]*>")
_BLOCK_TAGS = {
    "article",
    "div",
    "figure",
    "figcaption",
    "footer",
    "header",
    "li",
    "ol",
    "p",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}

_HTML_MULTI_MARKERS_RE = re.compile(
    r"</?(?:%s)" % "|".join(sorted(_BLOCK_TAGS | {"br"})),
    re.IGNORECASE,
)
_IMG_TAG_RE = re.compile(r"<img[^>]*>", re.IGNORECASE)

_ALLOWED_TAGS = _BLOCK_TAGS | {
    "a",
    "b",
    "br",
    "code",
    "col",
    "colgroup",
    "em",
    "i",
    "img",
    "picture",
    "pre",
    "source",
    "span",
    "strong",
    "u",
    "blockquote",
}
_SELF_CLOSING_TAGS = {"br", "img"}
_SKIP_CONTENT_TAGS = {"script", "style"}
_GLOBAL_ATTRS = {"class", "style", "id"}
_ALLOWED_ATTRS = {
    "a": {"href", "title", "target", "rel"},
    "img": {"src", "alt", "title", "width", "height", "loading", "style", "decoding", "referrerpolicy"},
    "div": set(),
    "span": set(),
    "figure": set(),
    "figcaption": set(),
    "code": set(),
    "pre": set(),
    "p": set(),
    "table": {"border", "cellpadding", "cellspacing", "width", "height", "align"},
    "tr": {"align", "valign"},
    "td": {"colspan", "rowspan", "width", "height", "align", "valign"},
    "th": {"colspan", "rowspan", "width", "height", "align", "valign"},
    "col": {"span", "width"},
    "colgroup": {"span"},
    "picture": set(),
    "source": {"srcset", "type", "media", "sizes"},
}

_BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "header",
    "footer",
    "ul",
    "ol",
    "li",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "td",
    "th",
    "figure",
    "figcaption",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}


def _is_safe_url(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered.startswith(("javascript:", "vbscript:", "data:text/html")):
        return False
    if lowered.startswith(("http://", "https://", "mailto:", "/", "#")):
        return True
    if lowered.startswith("data:image"):
        return True
    return False


class _HTMLSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_level = 0

    def _clean_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> list[tuple[str, str]]:
        allowed_for_tag = _ALLOWED_ATTRS.get(tag, set()) | _GLOBAL_ATTRS
        cleaned: list[tuple[str, str]] = []
        rel_present = False
        target_blank = False

        for name, value in attrs:
            if name not in allowed_for_tag or value is None:
                continue
            if name in {"href", "src"} and not _is_safe_url(value):
                continue
            if name == "target" and value == "_blank":
                target_blank = True
            if name == "rel":
                rel_present = True

            cleaned.append((name, escape(value)))

        if tag == "a" and target_blank and not rel_present:
            cleaned.append(("rel", "noopener noreferrer"))

        return cleaned

    def _push_tag(self, tag: str, attrs: list[tuple[str, str]], self_closing: bool = False) -> None:
        attrs_html = "".join(f' {name}="{val}"' for name, val in attrs)
        if self_closing or tag in _SELF_CLOSING_TAGS:
            self._parts.append(f"<{tag}{attrs_html}>")
        else:
            self._parts.append(f"<{tag}{attrs_html}>")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_CONTENT_TAGS:
            self._skip_level += 1
            return

        if self._skip_level > 0:
            return

        if tag not in _ALLOWED_TAGS:
            return

        self._push_tag(tag, self._clean_attrs(tag, attrs))

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_CONTENT_TAGS:
            if self._skip_level > 0:
                self._skip_level -= 1
            return

        if self._skip_level > 0:
            return

        if tag in _ALLOWED_TAGS and tag not in _SELF_CLOSING_TAGS:
            self._parts.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_CONTENT_TAGS or self._skip_level > 0 or tag not in _ALLOWED_TAGS:
            return

        self._push_tag(tag, self._clean_attrs(tag, attrs), self_closing=True)

    def handle_data(self, data: str) -> None:
        if self._skip_level > 0:
            return
        self._parts.append(escape(data))

    def get_html(self) -> str:
        return "".join(self._parts)


def _sanitize_html(raw: str) -> str:
    sanitizer = _HTMLSanitizer()
    sanitizer.feed(raw)
    return sanitizer.get_html()


class _PlainTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def _append_newline(self) -> None:
        if not self._parts:
            self._parts.append("\n")
            return
        if self._parts[-1].endswith("\n"):
            return
        self._parts.append("\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower == "br":
            self._parts.append("\n")
            return
        if lower in _BLOCK_TAGS:
            self._append_newline()
        if lower == "li":
            self._append_newline()
            self._parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in _BLOCK_TAGS and lower != "li":
            self._append_newline()
        if lower == "li":
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data)
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        joined = "".join(self._parts)
        cleaned = re.sub(r"[ \t]+\n", "\n", joined)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        return cleaned.strip()


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
        return {
            "html": empty,
            "has_text": False,
            "is_multi": False,
            "has_image": False,
            "is_html": False,
        }

    stripped = value.strip()
    if not stripped:
        empty = Markup("")
        return {
            "html": empty,
            "has_text": False,
            "is_multi": False,
            "has_image": False,
            "is_html": False,
        }

    if _HTML_TAG_RE.search(stripped):
        sanitized = _sanitize_html(stripped)
        has_text = bool(sanitized.strip())
        is_multi = bool(_HTML_MULTI_MARKERS_RE.search(sanitized) or "\n" in stripped)
        has_image = bool(_IMG_TAG_RE.search(sanitized))
        return {
            "html": Markup(sanitized),
            "has_text": has_text,
            "is_multi": is_multi,
            "has_image": has_image,
            "is_html": True,
        }

    paragraphs = [part.strip() for part in _PARAGRAPH_RE.split(stripped) if part.strip()]
    if not paragraphs:
        empty = Markup("")
        return {
            "html": empty,
            "has_text": False,
            "is_multi": False,
            "has_image": False,
            "is_html": False,
        }

    html, is_multi = _render_plain_blocks(paragraphs)
    return {
        "html": html,
        "has_text": True,
        "is_multi": is_multi,
        "has_image": False,
        "is_html": False,
    }


def _render_plain_blocks(paragraphs: list[str]) -> tuple[Markup, bool]:
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
    return html, is_multi


def render_plain_text(value: str | None) -> str:
    """Convert stored description to readable plain text."""
    if not value:
        return ""
    stripped = value.strip()
    if not stripped:
        return ""
    if _HTML_TAG_RE.search(stripped):
        sanitized = _sanitize_html(stripped)
        extractor = _PlainTextExtractor()
        extractor.feed(sanitized)
        return extractor.get_text()
    paragraphs = [part.strip() for part in _PARAGRAPH_RE.split(stripped) if part.strip()]
    if not paragraphs:
        return ""
    lines: list[str] = []
    for idx, paragraph in enumerate(paragraphs):
        if idx > 0:
            lines.append("")
        for line in paragraph.split("\n"):
            line = line.strip()
            if not line:
                continue
            lines.append(line)
    return "\n".join(lines)


def extract_media_sources(value: str | None) -> list[str]:
    """Return list of media paths referenced in HTML (img/src, picture/srcset)."""
    if not value:
        return []
    stripped = value.strip()
    if not stripped or not _HTML_TAG_RE.search(stripped):
        return []

    sanitized = _sanitize_html(stripped)

    class _SrcParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.sources: list[str] = []
            self.seen: set[str] = set()

        def _add(self, url: str | None) -> None:
            if not url:
                return
            src = url.strip().split()[0]
            if src.startswith("//"):
                return
            if src.startswith(("http://", "https://")):
                return
            normalized = _normalize_media_path(src)
            if normalized and normalized not in self.seen:
                self.seen.add(normalized)
                self.sources.append(normalized)

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            lower = tag.lower()
            attr_map = {k: v for k, v in attrs}
            if lower == "img":
                self._add(attr_map.get("src"))
            elif lower == "source":
                srcset = attr_map.get("srcset")
                if srcset:
                    first = srcset.split(",")[0]
                    self._add(first)

    def _normalize_media_path(raw: str) -> str | None:
        cleaned = raw.lstrip("/")
        if not cleaned.startswith("media/"):
            return None
        safe = re.sub(r"[\\/]+", "/", cleaned)
        parts = [p for p in safe.split("/") if p and p not in {".", ".."}]
        if not parts or parts[0] != "media":
            return None
        return "/".join(parts)

    parser = _SrcParser()
    parser.feed(sanitized)
    return parser.sources
