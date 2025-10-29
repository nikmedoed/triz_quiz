from app.rich_text import format_rich_text


def test_format_rich_text_converts_hyphen_lines_to_list():
    result = format_rich_text("- First option\n- Second option")

    assert result["has_text"] is True
    assert result["is_multi"] is True
    assert str(result["html"]) == "<ul><li>First option</li><li>Second option</li></ul>"


def test_format_rich_text_handles_paragraph_and_list_together():
    value = "Intro paragraph:\n- Item one\n- Item two"
    result = format_rich_text(value)

    assert result["has_text"] is True
    assert result["is_multi"] is True
    assert str(result["html"]) == "<p>Intro paragraph:</p><ul><li>Item one</li><li>Item two</li></ul>"


def test_format_rich_text_preserves_bold_inside_list_items():
    result = format_rich_text("- **Bold** choice")

    assert str(result["html"]) == "<ul><li><strong>Bold</strong> choice</li></ul>"
