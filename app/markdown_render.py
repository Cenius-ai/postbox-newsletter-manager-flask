"""A deliberately small Markdown renderer for campaign bodies.

Everything is HTML-escaped *before* any markup is produced, so the only tags in
the output are the ones this module writes itself. Raw markup typed into a
campaign body therefore renders as visible text instead of becoming live HTML,
which is what makes the result safe to drop into the composer preview.

Supported: fenced code, ATX headings, blockquotes, unordered/ordered lists,
horizontal rules, paragraphs (single newlines become ``<br>``), inline code,
bold, italic and links with a scheme allowlist.

A campaign body's ``#`` maps to ``<h2>`` so the preview continues the page's
heading order instead of skipping a level.
"""

from __future__ import annotations

import html
import re

from markupsafe import Markup

FENCE = re.compile(r"^```([\w+-]*)\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
ORDERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
RULE = re.compile(r"^\s*(?:---+|\*\*\*+|___+)\s*$")
INLINE_CODE = re.compile(r"`([^`\n]+)`")
LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)")
SAFE_SCHEME = re.compile(r"^(?:https?://|mailto:|/|#)", re.IGNORECASE)

PLACEHOLDER = "\x00{}\x00"


def _inline(raw: str) -> str:
    """Render one line of inline Markdown, escaping first."""
    text = html.escape(raw, quote=True)
    stash: dict[str, str] = {}

    def keep(markup: str) -> str:
        key = PLACEHOLDER.format(len(stash))
        stash[key] = markup
        return key

    text = INLINE_CODE.sub(lambda m: keep(f"<code>{m.group(1)}</code>"), text)

    def link(match: re.Match[str]) -> str:
        label, target = match.group(1), html.unescape(match.group(2))
        if not SAFE_SCHEME.match(target):
            return label
        href = html.escape(target, quote=True)
        return keep(f'<a href="{href}" rel="noopener noreferrer nofollow">{label}</a>')

    text = LINK.sub(link, text)
    text = BOLD.sub(r"<strong>\1</strong>", text)
    text = ITALIC.sub(r"<em>\1</em>", text)

    for key, markup in stash.items():
        text = text.replace(key, markup)
    return text


def render_markdown(body: str | None) -> Markup:
    """Render a campaign body to sanitised HTML."""
    lines = (body or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            joined = "<br>".join(_inline(line) for line in paragraph)
            blocks.append(f"<p>{joined}</p>")
            paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if FENCE.match(stripped):
            flush_paragraph()
            language = FENCE.match(stripped).group(1)
            index += 1
            code: list[str] = []
            while index < len(lines) and not FENCE.match(lines[index].strip()):
                code.append(lines[index])
                index += 1
            index += 1  # closing fence
            body_html = html.escape("\n".join(code), quote=False)
            class_attr = f' class="language-{html.escape(language)}"' if language else ""
            blocks.append(f"<pre><code{class_attr}>{body_html}</code></pre>")
            continue

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        heading = HEADING.match(stripped)
        if heading:
            flush_paragraph()
            level = min(6, 1 + len(heading.group(1)))
            blocks.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if RULE.match(stripped):
            flush_paragraph()
            blocks.append("<hr>")
            index += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quoted: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quoted.append(lines[index].strip().lstrip(">").strip())
                index += 1
            inner = "<br>".join(_inline(part) for part in quoted)
            blocks.append(f"<blockquote><p>{inner}</p></blockquote>")
            continue

        if BULLET.match(line):
            flush_paragraph()
            items: list[str] = []
            while index < len(lines) and BULLET.match(lines[index]):
                items.append(BULLET.match(lines[index]).group(1))
                index += 1
            blocks.append("<ul>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + "</ul>")
            continue

        if ORDERED.match(line):
            flush_paragraph()
            items = []
            while index < len(lines) and ORDERED.match(lines[index]):
                items.append(ORDERED.match(lines[index]).group(1))
                index += 1
            blocks.append("<ol>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + "</ol>")
            continue

        paragraph.append(line)
        index += 1

    flush_paragraph()

    if not blocks:
        blocks.append('<p class="preview__empty">Nothing written yet.</p>')
    return Markup("\n".join(blocks))
