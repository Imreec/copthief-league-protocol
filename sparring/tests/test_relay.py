"""The message relay: it must accept strangers, persist across restarts, and never crash on junk."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sparring.relay import MessageRelay


@pytest.fixture
def relay(tmp_path: Path) -> MessageRelay:
    """A relay that persists to a temporary file."""
    return MessageRelay(persist=tmp_path / "messages.json")


def test_a_message_is_assigned_a_sequence_number(relay: MessageRelay) -> None:
    msg = relay.add("best2934", "thief restarted")
    assert msg["seq"] == 1
    assert msg["from"] == "best2934"
    assert msg["text"] == "thief restarted"
    assert "ts" in msg


def test_messages_arrive_in_order(relay: MessageRelay) -> None:
    relay.add("a", "first")
    relay.add("b", "second")
    relay.add("c", "third")
    texts = [m["text"] for m in relay.all()]
    assert texts == ["first", "second", "third"]


def test_since_filters_by_sequence(relay: MessageRelay) -> None:
    relay.add("a", "one")
    relay.add("b", "two")
    relay.add("c", "three")
    assert [m["text"] for m in relay.since(1)] == ["two", "three"]
    assert [m["text"] for m in relay.since(3)] == []


def test_messages_survive_a_restart(tmp_path: Path) -> None:
    r1 = MessageRelay(persist=tmp_path / "msgs.json")
    r1.add("x", "hello")
    r1.add("y", "world")

    r2 = MessageRelay(persist=tmp_path / "msgs.json")
    assert len(r2.all()) == 2
    assert r2.all()[0]["text"] == "hello"
    # And the sequence continues rather than resetting
    msg = r2.add("z", "third")
    assert msg["seq"] == 3


def test_a_corrupt_file_does_not_crash(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("not json at all")
    relay = MessageRelay(persist=tmp_path / "bad.json")
    assert relay.all() == []
    relay.add("a", "works after corruption")
    assert len(relay.all()) == 1


def test_sender_and_text_are_capped(relay: MessageRelay) -> None:
    msg = relay.add("a" * 200, "b" * 10000)
    assert len(msg["from"]) <= 64
    assert len(msg["text"]) <= 4096


def test_empty_text_is_stored_but_the_http_layer_would_reject_it(relay: MessageRelay) -> None:
    # The relay itself stores anything; the HTTP handler rejects empty. Both are correct.
    msg = relay.add("a", "   ")
    assert msg["text"] == ""


def test_old_messages_are_evicted_when_the_cap_is_reached(tmp_path: Path) -> None:
    relay = MessageRelay(persist=tmp_path / "msgs.json")
    for i in range(510):
        relay.add("flood", f"msg {i}")
    assert len(relay.all()) == 500
    assert relay.all()[0]["text"] == "msg 10"  # first 10 evicted
