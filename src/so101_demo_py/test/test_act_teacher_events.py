"""The Teacher event stream is bounded, non-blocking and one-way (Teacher/ACT decoupling A3a)."""

import threading
import time

import pytest

from so101_demo.act.teacher_events import DEFAULT_DEPTH, SCHEMA, TeacherEventQueue


def test_events_are_closed_documents_with_gapless_sequence_numbers():
    queue = TeacherEventQueue()
    assert queue.depth == DEFAULT_DEPTH == 64
    for index in range(3):
        assert queue.publish("phase_begin", {"phase": f"P{index}"}) is True
    events = queue.drain()
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert all(set(event) == {"schema", "sequence", "kind", "monotonic_ns", "payload"} for event in events)
    assert all(event["schema"] == SCHEMA for event in events)
    assert queue.drain() == []
    assert queue.snapshot() == {"depth": 64, "pending": 0, "published": 3, "dropped": 0}


def test_payload_is_copied_so_the_producer_cannot_be_changed_by_the_consumer():
    queue = TeacherEventQueue()
    payload = {"values": [1, 2]}
    queue.publish("native_start", payload)
    payload["values"].append(3)
    assert queue.drain()[0]["payload"] == {"values": [1, 2]}


def test_overflow_drops_counts_and_leaves_a_visible_sequence_gap_without_raising():
    queue = TeacherEventQueue(depth=2)
    results = [queue.publish("phase_begin", {"n": index}) for index in range(5)]
    assert results == [True, True, False, False, False]
    assert queue.dropped == 3
    assert [event["sequence"] for event in queue.drain()] == [1, 2]
    assert queue.publish("phase_finish") is True
    assert queue.drain()[0]["sequence"] == 6  # the consumer sees 3, 4, 5 missing
    assert queue.snapshot()["dropped"] == 3


def test_publish_does_not_wait_for_a_consumer_that_holds_the_lock():
    queue = TeacherEventQueue()
    held, release = threading.Event(), threading.Event()

    def consumer():
        with queue._lock:
            held.set()
            release.wait(5)

    thread = threading.Thread(target=consumer)
    thread.start()
    try:
        assert held.wait(2)
        began = time.monotonic()
        assert queue.publish("phase_begin") is False
        assert time.monotonic() - began < 0.5
    finally:
        release.set()
        thread.join(2)
    assert queue.dropped == 1


@pytest.mark.parametrize("depth", [0, -1, True, 1.5, 5000, "4"])
def test_depth_is_a_bounded_integer(depth):
    with pytest.raises(ValueError, match="TEACHER_EVENT_QUEUE_DEPTH_INVALID"):
        TeacherEventQueue(depth=depth)


def test_drain_limit_returns_the_oldest_events_first():
    queue = TeacherEventQueue()
    for index in range(4):
        queue.publish("phase_begin", {"n": index})
    assert [event["payload"]["n"] for event in queue.drain(limit=2)] == [0, 1]
    assert [event["payload"]["n"] for event in queue.drain()] == [2, 3]
