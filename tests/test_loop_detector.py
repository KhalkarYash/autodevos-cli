"""LoopDetector tests (audit M7, Phase 3)."""

from context.loop_detector import LoopDetector


def test_no_loop_initially():
    d = LoopDetector()
    assert d.check_for_loop() is None


def test_exact_repeat_detected():
    d = LoopDetector()
    for _ in range(3):
        d.record_action("tool_call", tool_name="read_file", args={"path": "a"})
    msg = d.check_for_loop()
    assert msg is not None
    assert "times" in msg  # regression guard for the old "tiems" typo


def test_distinct_actions_no_loop():
    d = LoopDetector()
    d.record_action("tool_call", tool_name="read_file", args={"path": "a"})
    d.record_action("tool_call", tool_name="read_file", args={"path": "b"})
    d.record_action("tool_call", tool_name="read_file", args={"path": "c"})
    assert d.check_for_loop() is None


def test_cycle_detected():
    d = LoopDetector()
    for _ in range(6):
        d.record_action("tool_call", tool_name="a", args={})
        d.record_action("tool_call", tool_name="b", args={})
    msg = d.check_for_loop()
    assert msg is not None
    assert "cycle" in msg.lower()


def test_clear_resets_history():
    d = LoopDetector()
    for _ in range(3):
        d.record_action("response", text="same")
    assert d.check_for_loop() is not None
    d.clear()
    assert d.check_for_loop() is None


def test_arg_order_independent_signature():
    d = LoopDetector()
    d.record_action("tool_call", tool_name="t", args={"a": 1, "b": 2})
    d.record_action("tool_call", tool_name="t", args={"b": 2, "a": 1})
    d.record_action("tool_call", tool_name="t", args={"a": 1, "b": 2})
    # All three normalize to the same signature -> exact repeat.
    assert d.check_for_loop() is not None
