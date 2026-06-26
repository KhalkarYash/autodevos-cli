"""ToolCall argument parsing tests (audit C2: arguments type confusion)."""

from client.response import (
    ToolCall,
    parse_tool_call_arguments,
    serialize_tool_call_arguments,
)


def test_parse_json_string_to_dict():
    assert parse_tool_call_arguments('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_parse_dict_passthrough():
    assert parse_tool_call_arguments({"a": 1}) == {"a": 1}


def test_parse_empty_returns_empty_dict():
    assert parse_tool_call_arguments("") == {}
    assert parse_tool_call_arguments(None) == {}


def test_parse_non_dict_json_wrapped():
    assert parse_tool_call_arguments("[1,2,3]") == {"raw_arguments": [1, 2, 3]}


def test_toolcall_normalizes_string_arguments():
    tc = ToolCall(call_id="1", name="t", arguments='{"path": "f.txt"}')
    assert tc.arguments == {"path": "f.txt"}


def test_toolcall_normalizes_none_arguments():
    tc = ToolCall(call_id="1", name="t", arguments=None)
    assert tc.arguments == {}


def test_roundtrip_serialize_parse():
    original = {"path": "f.txt", "n": 3}
    s = serialize_tool_call_arguments(original)
    assert parse_tool_call_arguments(s) == original
