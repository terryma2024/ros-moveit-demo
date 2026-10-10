"""The recorder's reported losses are a recorded fact, the clock-map limit is 2 ms, and recorder_late records its evidence."""

import pytest

from test_p3_offline_switch import LEASE, FakePilot, FakeProcesses, collection_for


@pytest.fixture(autouse=True)
def _fresh_fake_pilots():
    FakePilot.instances.clear()
    FakePilot.log = None
    yield
    FakePilot.instances.clear()
    FakePilot.log = None


# ---- the recorder's reported losses are a recorded fact; the clock-map limit is 2 ms ----------------------

def test_the_transport_loss_the_recorder_reports_is_parsed_into_its_stats():
    from so101_demo.act.offline.raw_recorder import transport_lost_from_log

    log = ("[INFO] recording\n[WARN] [1791425951.943280991] [so101_raw_recorder]: Number of messages lost on the transport layer: 6\n"
           "[INFO] done\n")
    assert transport_lost_from_log(log) == 6
    assert transport_lost_from_log("[INFO] nothing lost\n") == 0
    assert transport_lost_from_log(log + log) == 12


def test_the_clock_map_limit_is_two_milliseconds_and_a_larger_residual_is_a_reason(tmp_path, monkeypatch):
    from so101_demo.act.offline import bag_io, processor, scan

    assert processor.CLOCK_RESIDUAL_LIMIT_NS == 2_000_000
    observed = [918, 2848]                                    # the two real bags
    assert max(observed) * 700 < processor.CLOCK_RESIDUAL_LIMIT_NS

    def run(residual):
        monkeypatch.setattr(bag_io, "bag_info", lambda bag: {"message_count": 1, "duration_ns": 1, "topics": {}})
        monkeypatch.setattr(processor, "load_clock_map", lambda bag, stats_file=None: ({}, {"max_residual_ns": residual}))
        monkeypatch.setattr(scan, "scan_bag", lambda bag, info=None, **loss: {"reasons": [], "timeline": {"identity": None}, "continuity": {},
                                                                      "counts": {}})
        return processor.process_bag(tmp_path / "bag", tmp_path / "out", inputs_manifest=tmp_path / "i.json", lease=LEASE)

    assert not any(reason.startswith("OFFLINE_CLOCK_MAP_INCONSISTENT") for reason in run(2_000_000)["reasons"])
    assert any(reason.startswith("OFFLINE_CLOCK_MAP_INCONSISTENT") for reason in run(2_000_001)["reasons"])


# ---- recorder_late records its evidence ----------------------------------------------------------------------

def test_recorder_late_records_when_the_teachers_setup_evidence_was_seen_and_when_the_bag_was_started(tmp_path):
    processes = FakeProcesses()
    collection, point, clock = collection_for(tmp_path, fault="recorder_late", processes=processes, late_delay_s=5.0)
    collection.start_before_teacher()
    trigger = point / "dynamic" / "reachability-observed.json"
    collection.teacher_started_now()
    collection.arm_late_start(trigger)
    trigger.write_text("{}")
    collection._late_thread.join(timeout=10)
    outcome = collection.finish(lease=LEASE)
    evidence = outcome.facts["late_evidence"]
    assert outcome.reason == "RECORDER_STARTED_AFTER_TEACHER" and evidence["delay_s"] == 5.0
    assert evidence["trigger_seen_system_ns"] <= evidence["start_requested_system_ns"]
    assert "bag_first_stamp_ns" in evidence or "bag_first_stamp_error" in evidence
