from __future__ import annotations

import re
from html import escape
from html import unescape

MAX_TELEGRAM_MESSAGE_LENGTH = 4000

FENCED_BLOCK_RE = re.compile(r"^```(?P<lang>[^\n`]*)\n(?P<body>.*?)\n```$", re.DOTALL)
ORDERED_LIST_RE = re.compile(r"^\d+\.\s+")
UNORDERED_LIST_RE = re.compile(r"^[-*+]\s+")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
STRONG_RE = re.compile(r"\*\*(.+?)\*\*")
UNDERLINE_RE = re.compile(r"__(.+?)__")
STRIKE_RE = re.compile(r"~~(.+?)~~")
EMPHASIS_STAR_RE = re.compile(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)")
EMPHASIS_UNDERSCORE_RE = re.compile(r"(?<!_)_(?!\s)(.+?)(?<!\s)_(?!_)")


def render_telegram_html_chunks(markdown_text: str) -> list[str]:
    text = markdown_text.strip()
    if not text:
        return [""]

    blocks = _split_blocks(text)
    chunks: list[str] = []
    current = ""
    for block in blocks:
        rendered_parts = _render_block_to_chunks(block)
        for part in rendered_parts:
            candidate = part if not current else f"{current}\n\n{part}"
            if len(candidate) <= MAX_TELEGRAM_MESSAGE_LENGTH:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = part
    if current:
        chunks.append(current)
    return chunks


def strip_telegram_html(rendered: str) -> str:
    plain = re.sub(r"<br>", "\n", rendered)
    plain = re.sub(r"</?(?:b|i|u|s|code|pre)>", "", plain)
    return unescape(plain)


def _split_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            current.append(line)
            continue
        if not in_fence and not line.strip():
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return blocks


def _render_block_to_chunks(block: str) -> list[str]:
    fenced = FENCED_BLOCK_RE.match(block)
    if fenced:
        return _render_fenced_code_chunks(fenced.group("body"))

    lines = block.splitlines()
    if all(UNORDERED_LIST_RE.match(line) or ORDERED_LIST_RE.match(line) for line in lines if line.strip()):
        return _split_long_block(_render_list(lines))

    if len(lines) == 1 and lines[0].startswith("#"):
        title = lines[0].lstrip("#").strip()
        return _split_long_block(f"<b>{_render_inline(title)}</b>")

    paragraph = "<br>".join(_render_inline(line) for line in lines)
    return _split_long_block(paragraph)


def _render_fenced_code_chunks(code: str) -> list[str]:
    lines = code.splitlines()
    if not lines:
        return ["<pre><code></code></pre>"]

    chunks: list[str] = []
    current: list[str] = []
    wrapper_overhead = len("<pre><code></code></pre>")
    current_len = wrapper_overhead
    for line in lines:
        escaped_line = escape(line)
        line_len = len(escaped_line) + (1 if current else 0)
        if current and current_len + line_len > MAX_TELEGRAM_MESSAGE_LENGTH:
            chunks.append(f"<pre><code>{'\n'.join(current)}</code></pre>")
            current = [escaped_line]
            current_len = wrapper_overhead + len(escaped_line)
            continue
        if current:
            current_len += 1
        current.append(escaped_line)
        current_len += len(escaped_line)
    if current:
        chunks.append(f"<pre><code>{'\n'.join(current)}</code></pre>")
    return chunks


def _render_list(lines: list[str]) -> str:
    rendered_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if ORDERED_LIST_RE.match(stripped):
            marker, _, content = stripped.partition(". ")
            rendered_lines.append(f"{escape(marker)}. {_render_inline(content)}")
            continue
        content = UNORDERED_LIST_RE.sub("", stripped, count=1)
        rendered_lines.append(f"• {_render_inline(content)}")
    return "<br>".join(rendered_lines)


def _split_long_block(rendered: str) -> list[str]:
    if len(rendered) <= MAX_TELEGRAM_MESSAGE_LENGTH:
        return [rendered]

    plain = strip_telegram_html(rendered)
    parts: list[str] = []
    remaining = plain.strip()
    while remaining:
        if len(remaining) <= MAX_TELEGRAM_MESSAGE_LENGTH:
            parts.append(escape(remaining).replace("\n", "<br>"))
            break
        split_at = remaining.rfind("\n", 0, MAX_TELEGRAM_MESSAGE_LENGTH)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, MAX_TELEGRAM_MESSAGE_LENGTH)
        if split_at <= 0:
            split_at = MAX_TELEGRAM_MESSAGE_LENGTH
        parts.append(escape(remaining[:split_at].strip()).replace("\n", "<br>"))
        remaining = remaining[split_at:].strip()
    return parts


def _render_inline(text: str) -> str:
    segments = _split_inline_code(text)
    rendered: list[str] = []
    for is_code, segment in segments:
        if is_code:
            rendered.append(f"<code>{escape(segment)}</code>")
            continue
        rendered.append(_render_non_code_inline(segment))
    return "".join(rendered)


def _split_inline_code(text: str) -> list[tuple[bool, str]]:
    segments: list[tuple[bool, str]] = []
    last = 0
    for match in INLINE_CODE_RE.finditer(text):
        if match.start() > last:
            segments.append((False, text[last:match.start()]))
        segments.append((True, match.group(1)))
        last = match.end()
    if last < len(text):
        segments.append((False, text[last:]))
    if not segments:
        segments.append((False, text))
    return segments


def _render_non_code_inline(text: str) -> str:
    escaped = escape(text)
    escaped = STRONG_RE.sub(r"<b>\1</b>", escaped)
    escaped = UNDERLINE_RE.sub(r"<u>\1</u>", escaped)
    escaped = STRIKE_RE.sub(r"<s>\1</s>", escaped)
    escaped = EMPHASIS_STAR_RE.sub(r"<i>\1</i>", escaped)
    escaped = EMPHASIS_UNDERSCORE_RE.sub(r"<i>\1</i>", escaped)
    return escaped
