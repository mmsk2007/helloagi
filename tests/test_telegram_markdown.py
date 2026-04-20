"""Verify the markdown→Telegram-HTML conversion used by TelegramChannel."""

from agi_runtime.channels.telegram import _markdownish_to_html


def test_bold_becomes_b_tag():
    assert _markdownish_to_html("hello **world**") == "hello <b>world</b>"


def test_inline_code_becomes_code_tag():
    assert _markdownish_to_html("use `web_fetch` here") == "use <code>web_fetch</code> here"


def test_triple_backtick_block_becomes_pre():
    out = _markdownish_to_html("```\nprint('hi')\n```")
    assert out.startswith("<pre>") and out.endswith("</pre>")
    assert "print(&#x27;hi&#x27;)" in out or "print('hi')" in out


def test_underscores_in_identifiers_are_left_alone():
    # web_fetch / file_path must NOT become italics — they collide with *italic*.
    assert _markdownish_to_html("use web_fetch and file_path") == "use web_fetch and file_path"


def test_html_special_chars_are_escaped_first():
    out = _markdownish_to_html("if x < 1 && y > 2")
    assert "&lt;" in out and "&gt;" in out and "&amp;" in out


def test_empty_input_is_safe():
    assert _markdownish_to_html("") == ""


def test_mixed_inline_formatting():
    out = _markdownish_to_html("**bold** and `code` together")
    assert "<b>bold</b>" in out
    assert "<code>code</code>" in out


def test_bold_does_not_swallow_across_paragraphs_unintentionally():
    # Two separate **bold** spans on different lines should both render.
    out = _markdownish_to_html("**a**\n**b**")
    assert out.count("<b>") == 2
