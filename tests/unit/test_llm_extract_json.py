"""Coverage for the JSON extractor that replaces the fragile find/rfind blocks."""

import pytest

from blufire.llm import LLMOutputError, extract_json


def test_raw_json() -> None:
    assert extract_json('{"subject": "hi", "body": "x"}') == {"subject": "hi", "body": "x"}


def test_fenced_json() -> None:
    out = extract_json('Sure, here you go:\n```json\n{"a": 1}\n```\nLet me know!')
    assert out == {"a": 1}


def test_prose_wrapped_json() -> None:
    out = extract_json('Here is the JSON: {"name": "ACME", "score": 7}\nSee you!')
    assert out == {"name": "ACME", "score": 7}


def test_braces_inside_strings_do_not_confuse_scanner() -> None:
    out = extract_json('Result: {"text": "look at {this}!", "ok": true}')
    assert out == {"text": "look at {this}!", "ok": True}


def test_escape_in_string() -> None:
    out = extract_json(r'{"q": "say \"hi\"", "n": 1}')
    assert out == {"q": 'say "hi"', "n": 1}


def test_truncated_raises() -> None:
    with pytest.raises(LLMOutputError):
        extract_json('Almost JSON: {"a": 1')


def test_no_json_raises() -> None:
    with pytest.raises(LLMOutputError):
        extract_json("Sorry, I can't help with that.")


def test_nested_objects() -> None:
    out = extract_json('Output: {"a": {"b": {"c": 3}}, "d": [1, 2, 3]}')
    assert out == {"a": {"b": {"c": 3}}, "d": [1, 2, 3]}


def test_escaped_backslash_then_quote_in_string() -> None:
    """``"value\\\\"`` inside a JSON string must not confuse the brace scanner."""
    out = extract_json(r'Result: {"k": "ends with backslash\\", "n": 1}')
    assert out == {"k": "ends with backslash\\", "n": 1}


def test_unicode_escapes() -> None:
    out = extract_json(r'{"emoji": "☃", "ok": true}')
    assert out == {"emoji": "☃", "ok": True}


def test_truncated_error_shows_head_and_tail() -> None:
    raw = "garbage prefix " + ("x" * 2000) + " trailing junk that we want to see"
    with pytest.raises(LLMOutputError) as exc_info:
        extract_json(raw)
    msg = str(exc_info.value)
    assert "garbage prefix" in msg
    assert "trailing junk" in msg
    assert "elided" in msg
