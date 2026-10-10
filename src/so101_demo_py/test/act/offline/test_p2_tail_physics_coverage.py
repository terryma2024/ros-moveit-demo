"""Pilot 8d9ed9d3: the Teacher's end observation (step 56421, 115.770 s) lay in the last 100 ms physics chunk (steps 56401-56450,
ending 115.828 s), which the bag recorded after the `terminal` event. The camera grid reached the observation first
(collection end 115.8 s >= 115.77 s), the tail ended at once and the reference check found the newest retained physics step
(56400) before the end observation: TEACHER_REFERENCE_END_AFTER_RECORDING. The tail waits for the physics samples too."""

from types import SimpleNamespace

from so101_demo.act.offline.sources import OfflineRosSources


def _sources(retained):
    sources = object.__new__(OfflineRosSources)
    sources._finish_started, sources._jobs, sources._admissions = True, [], []
    sources.episode = SimpleNamespace(capture=SimpleNamespace(window={"collection_end_s": 115.8}))
    sources.binding = SimpleNamespace(physics_adapter=SimpleNamespace(retained_step_range=lambda: retained))
    return sources


def _engine():
    return SimpleNamespace(end_obs={"simulation_time_s": 115.77, "simulation_step": 56421})


def test_the_tail_waits_for_the_physics_chunk_that_holds_the_end_observation():
    assert _sources((651, 56400)).tail_ready(_engine()) is False
    assert _sources(None).tail_ready(_engine()) is False


def test_the_tail_ends_once_the_end_observation_step_is_retained():
    assert _sources((651, 56450)).tail_ready(_engine()) is True
    assert _sources((651, 56421)).tail_ready(_engine()) is True


def test_a_missing_end_observation_is_left_to_the_reference_check():
    assert _sources((651, 56400)).tail_ready(SimpleNamespace(end_obs=None)) is True
