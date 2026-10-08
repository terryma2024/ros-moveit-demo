"""Recorder round 12b (CP-3425): the capture is running before the Teacher starts.

L2 5daa904e: the Teacher announced its reset as the oldest record of its own 3 s observer ring, stamped with a receipt time,
10 ms before its first command, so no live capture start could satisfy verified_reset <= capture_start <= initial_capture <=
first_command. The order is now: the worker resets and resumes the simulation; the Recorder starts, takes its own pre-SETUP
alignment, starts the capture on its own clock and commits the initial boundary; only then the
Teacher starts (the ready file CAPTURING is gone with the live Recorder); its SETUP is a `world_sync` alignment; its first command comes last. The verified reset is the Recorder's own
first evidence of the epoch on the evidence producer's clock. Nothing here changes what the Teacher does or whether it runs.
"""
import copy
import random
import time

import pytest

from b2_collection_fixtures import materials_v2
from so101_demo.act.offline.engine import RC_VALID
from test_act_scene_association import frozen_scene  # noqa: F401  (fixture)
from test_act_episode_recorder import NOT_EXHAUSTED, readback, result_of, teacher_script
from test_rec2_stall_replay import RealTimeSources, run_replay


from test_b2_collection_v2 import verify


# ---- the order, in the sealed originals ----------------------------------------------------------------------------------

def test_the_order_reset_then_capture_start_then_teacher_start_then_first_command_is_what_the_qc_reads(frozen_scene):
    events, identity, window, boundaries, _s, _x, teacher = materials_v2(frozen_scene)
    reset = boundaries["verified_reset"]["source_clock"]
    start = boundaries["capture_start"]
    initial = boundaries["initial_capture"]["source_clock"]
    teacher_start = teacher[0]
    assert reset["end_monotonic_ns"] <= start["begin_monotonic_ns"] and reset["sim_time_ns"] <= start["sim_time_ns"]
    assert initial["begin_monotonic_ns"] >= start["end_monotonic_ns"]
    assert teacher_start["type"] == "reset_complete" and teacher_start["monotonic_ns"] >= initial["end_monotonic_ns"]
    assert verify(events, identity, window, frozen_scene)["goal_phase_begins"] == 1


def test_a_teacher_that_started_before_the_capture_was_running_is_invalid(frozen_scene):
    events, identity, window, boundaries, _s, _x, teacher = materials_v2(frozen_scene)
    row = next(item for item in events if item["kind"] == "teacher_event_v2"
               and item["payload"]["teacher_event"]["type"] == "reset_complete")
    document = row["payload"]["teacher_event"]
    document["monotonic_ns"] = boundaries["capture_start"]["begin_monotonic_ns"] - 1       # before the capture start
    document["payload"]["received_monotonic_ns"] = document["monotonic_ns"]
    with pytest.raises(ValueError, match="NATIVE_QC_BOUNDARY_ORDER_INVALID"):
        verify(events, identity, window, frozen_scene)


def test_a_verified_reset_after_the_capture_start_is_invalid_the_old_order_is_gone(frozen_scene):
    events, identity, window, boundaries, _s, _x, _t = materials_v2(frozen_scene)
    boundary = next(item for item in events if item["kind"] == "collection_boundary_v1"
                    and item["payload"]["collection_boundary"]["stage"] == "verified_reset")
    clock = boundary["payload"]["collection_boundary"]["value"]["source_clock"]
    clock["begin_monotonic_ns"] = clock["end_monotonic_ns"] = boundaries["capture_start"]["end_monotonic_ns"] + 10
    boundary["monotonic_ns"] = clock["end_monotonic_ns"] + 1
    boundary["payload"]["collection_boundary"]["value"]["physical_source"]["received_wall_s"] = clock["end_monotonic_ns"] / 1e9
    with pytest.raises(ValueError):
        verify(events, identity, window, frozen_scene)


def test_a_missing_world_sync_before_the_first_command_makes_the_data_invalid(frozen_scene):
    events, identity, window, _b, _s, _x, _t = materials_v2(frozen_scene)
    kept = [item for item in events if not (item["kind"] == "source_alignment_v1"
                                            and item["payload"]["association"]["operation"] == "world_sync")]
    with pytest.raises(ValueError, match="NATIVE_QC_WORLD_SYNC_REQUIRED"):
        verify(kept, identity, window, frozen_scene)


def test_a_world_sync_whose_readback_came_after_the_first_command_does_not_count(frozen_scene):
    events, identity, window, _b, _s, _x, _t = materials_v2(frozen_scene)
    sync = next(item for item in events if item["kind"] == "source_alignment_v1"
                and item["payload"]["association"]["operation"] == "world_sync")
    sync["payload"]["association"]["query"]["record"]["response_ros_clock"]["sim_time_ns"] = 9_000_000
    with pytest.raises(ValueError, match="NATIVE_QC_WORLD_SYNC_REQUIRED"):
        verify(events, identity, window, frozen_scene)


@pytest.mark.parametrize("change", ["missing", "twice", "old_schema", "after_start"])
def test_exactly_one_pre_setup_initial_alignment_of_the_current_schema_before_the_capture_start(frozen_scene, change):
    events, identity, window, boundaries, _s, _x, _t = materials_v2(frozen_scene)
    initial = next(item for item in events if item["kind"] == "source_alignment_v1"
                   and item["payload"]["association"]["operation"] == "initial")
    if change == "missing":
        events.remove(initial)
    elif change == "twice":
        events.append(copy.deepcopy(initial))
    elif change == "old_schema":
        initial["payload"]["association"]["schema_version"] = 2
    else:
        initial["payload"]["association"]["query"]["record"]["request_ros_clock"]["sim_time_ns"] = \
            boundaries["capture_start"]["sim_time_ns"] + 1
    with pytest.raises(ValueError, match="NATIVE_QC_INITIAL_ALIGNMENT_INVALID"):
        verify(events, identity, window, frozen_scene)


# ---- the Recorder side: the verified reset ----------------------------------------------------------------------------------

def test_the_verified_reset_is_taken_from_the_producers_clock_of_the_first_world_record_that_has_its_raw_step():
    from types import SimpleNamespace
    from so101_demo.act.offline.sources import OfflineRosSources
    sources = OfflineRosSources.__new__(OfflineRosSources)
    sources.episode = SimpleNamespace(identity={"session_id": "s", "attempt_id": "a", "reset_epoch": 1})
    raw = {5: {"sample": {"clock_interval_begin_monotonic_ns": 10_000_000, "clock_interval_end_monotonic_ns": 10_100_000}}}
    sources._raw_lookup = lambda step: raw.get(step)

    def record(step, sequence, sim):
        return SimpleNamespace(evidence=SimpleNamespace(simulation_session_id="s", reset_epoch=1, simulation_step=step,
                                                        publisher_sequence=sequence, simulation_time_s=sim),
                               received_monotonic_s=0.0102)
    boundary = sources._epoch_boundary([record(1, 10, 0.002), record(5, 14, 0.010), record(6, 15, 0.012)])
    assert boundary["schema_version"] == 3
    assert boundary["physical_source"]["publisher_sequence"] == 14, "the first record that still has its raw step"
    assert boundary["source_clock"] == {"sim_time_ns": 10_000_000, "begin_monotonic_ns": 10_000_000,
                                        "end_monotonic_ns": 10_100_000}, "the producer's interval, not a receipt"
    assert sources._epoch_boundary([record(1, 10, 0.002)]) is None, "no raw step: no boundary, the gate stays closed"
    from so101_demo.act.collection_boundaries import validate_verified_reset
    validate_verified_reset(boundary, identity={"session_id": "s", "attempt_id": "a", "reset_epoch": 1})


def test_the_teachers_reset_complete_cannot_name_evidence_older_than_the_recorders_own():
    from so101_demo.act.teacher_collection_v2 import validate_reset_complete_matches
    from b2_collection_fixtures import envelope
    identity = dict(session_id="s", attempt_id="a", reset_epoch=2)
    boundary = dict(kind="ACT_VERIFIED_RESET_BOUNDARY", schema_version=3, session_id="s", attempt_id="a", reset_epoch=2,
                    source_clock=dict(sim_time_ns=5_000_000, begin_monotonic_ns=8_000_000_000, end_monotonic_ns=8_000_000_100),
                    physical_source=dict(session_id="s", reset_epoch=2, simulation_step=2, publisher_sequence=30,
                                         simulation_time_s=.005, received_wall_s=8.0001))
    ok = envelope(1, "reset_complete", 9_000_000, 9_000_000_000,
                  dict(session_id="s", reset_epoch=2, simulation_time_s=.008, simulation_step=4, publisher_sequence=40,
                       received_monotonic_ns=9_000_000_000), identity=identity)
    validate_reset_complete_matches(ok, boundary)
    older = envelope(1, "reset_complete", 9_000_000, 9_000_000_000,
                     dict(session_id="s", reset_epoch=2, simulation_time_s=.004, simulation_step=1, publisher_sequence=20,
                          received_monotonic_ns=9_000_000_000), identity=identity)
    with pytest.raises(ValueError, match="NATIVE_QC_RESET_EVENT_MISMATCH"):
        validate_reset_complete_matches(older, boundary)


# ---- a real-rate replay of the whole sequence ----------------------------------------------------------------------------

class TeacherAfterCapturing(RealTimeSources):
    """The Teacher's events reach the Recorder only 0.3 s after the capture started (the capture is running first)."""

    DELAY_S = 0.3

    def __init__(self, box, script, **kwargs):
        super().__init__(box, script, **kwargs)
        self.started_wall = None
        self.held = []
        self.delivered_after_start = []

    def try_start(self, engine):
        started = super().try_start(engine)
        if started is not None and self.started_wall is None:
            self.started_wall = time.monotonic()
        return started

    def deliver_rest(self, engine, item):
        held = self.held

        class Held:
            """The engine as the sources see it, with the Teacher's events held back."""
            def __getattr__(self, name):
                return getattr(engine, name)

            def on_event_text(self, text):
                held.append(text)
        super().deliver_rest(Held(), item)

    def pump(self, engine):
        if self.held and self.started_wall is not None and time.monotonic() - self.started_wall >= self.DELAY_S:
            for text in self.held:
                self.delivered_after_start.append(time.monotonic() - self.started_wall)
                engine.on_event_text(text)
            self.held = []
        super().pump(engine)


@pytest.mark.parametrize("seed", range(6))
def test_a_real_rate_replay_with_the_teacher_starting_after_the_capture_seals_valid_and_reads_back(tmp_path, seed):
    engine, sources, working = run_replay(tmp_path, script=teacher_script(),
                                          sources_cls=TeacherAfterCapturing)
    sources.DELAY_S = 0.15 + 0.05 * random.Random(seed).randint(0, 6)
    # the replay's own script ends the data 0.5 s after the capture start: the held events must still fit
    code = engine.process(NOT_EXHAUSTED)
    result = result_of(working)
    assert sources.delivered_after_start and min(sources.delivered_after_start) >= sources.DELAY_S - 0.01
    assert code == RC_VALID and result["status"] == "VALID", result["reasons"]
    seal, manifest, references = readback(working)
    assert seal["status"] == "PASSED" and references["status"] == "PASS"
