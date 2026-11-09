"""The in-repo Markdown renderer."""

from __future__ import annotations

from app.markdown_render import render_markdown


def test_renders_headings_bold_italic_lists_and_links():
    html = str(
        render_markdown(
            "# Title\n\n"
            "Some **bold** and *italic* and [a link](https://example.com).\n\n"
            "- one\n- two\n\n"
            "1. first\n2. second"
        )
    )
    assert "<h2>Title</h2>" in html
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html
    assert '<a href="https://example.com" rel="noopener noreferrer nofollow">a link</a>' in html
    assert "<ul><li>one</li><li>two</li></ul>" in html
    assert "<ol><li>first</li><li>second</li></ol>" in html


def test_heading_levels_stay_inside_the_page_order():
    html = str(render_markdown("## Section\n\n### Subsection"))
    assert "<h3>Section</h3>" in html
    assert "<h4>Subsection</h4>" in html


def test_raw_markup_is_escaped_and_never_runs():
    html = str(render_markdown("<script>alert(1)</script>"))
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_single_newlines_are_preserved_inside_a_paragraph():
    html = str(render_markdown("line one\nline two"))
    assert "<p>line one<br>line two</p>" in html


def test_fenced_code_and_blockquotes_render():
    html = str(render_markdown("```\nx = 1\n```\n\n> quoted line"))
    assert "<pre><code>x = 1</code></pre>" in html
    assert "<blockquote><p>quoted line</p></blockquote>" in html


def test_unsafe_link_schemes_are_dropped():
    html = str(render_markdown("[click](javascript:alert(1))"))
    assert "javascript:" not in html
    assert "click" in html


def test_empty_body_renders_a_placeholder():
    assert "Nothing written yet." in str(render_markdown(""))
