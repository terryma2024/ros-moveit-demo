"""A selected SEARCH sample needs its original 51 physical frames."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from test_act_stationary_bridge_history import history
from test_act_task8_search_boundary import _boundary, _request


def _sources(model, observed, worlds, scenes, contacts):
    raw = observed.physical_readback
    model_hash = raw["scene"]["model_sha256"]
    return SimpleNamespace(
        session_id=raw["world"].simulation_session_id,
        reset_epoch=raw["world"].reset_epoch,
        phase="SEARCH",
        world=SimpleNamespace(recent_with_receipts=lambda: tuple(worlds)),
        scene=SimpleNamespace(recent_frames_with_receipts=lambda: tuple(scenes)),
        contacts=SimpleNamespace(recent_frames_with_receipts=lambda: tuple(contacts)),
        contact_pairs=SimpleNamespace(
            model_sha256=model_hash,
            for_phase=lambda phase: frozenset() if phase == "SEARCH" else None,
        ),
        readback=SimpleNamespace(
            max_skew=.02, max_wall_age=.2, monotonic=lambda: 10.11,
            broker=SimpleNamespace(stop_velocity=.002),
        ),
    )


def _verify(sources, observed, model, *, stopped_wall_s=9.99):
    from so101_demo.adapters.act.pick_place_search_history import (
        verify_search_stationary_physics,
    )

    return verify_search_stationary_physics(
        sources, observed, model=model, stopped_wall_s=stopped_wall_s,
    )


def test_selected_search_binds_all_original_physical_frames():
    model, observed, _, worlds, scenes, contacts = history()
    result = _verify(_sources(model, observed, worlds, scenes, contacts),
                     observed, model)
    assert result["first_physics_step"] == 100
    assert result["selected_physics_step"] == 150
    assert result["stop_confirmed_wall_s"] == 9.99
    assert result["controller_interval_proof_required"] is True
    assert result["command_authority"] is False
    assert result["eligible_for_collection"] is False


@pytest.mark.parametrize("change", ["missing_scene", "wrong_epoch", "pre_stop_receipt"])
def test_selected_search_rejects_incomplete_or_pre_stop_history(change):
    model, observed, _, worlds, scenes, contacts = history()
    if change == "missing_scene":
        scenes.pop(25)
    elif change == "wrong_epoch":
        original = worlds[25]
        worlds[25] = SimpleNamespace(
                evidence=replace(original.evidence, reset_epoch=99),
                received_monotonic_s=original.received_monotonic_s)
    elif change == "pre_stop_receipt":
        original = worlds[0]
        worlds[0] = SimpleNamespace(evidence=original.evidence,
                                    received_monotonic_s=9.98)
    with pytest.raises(ValueError, match="SEARCH_PHYSICS_HISTORY_INVALID"):
        _verify(_sources(model, observed, worlds, scenes, contacts),
                observed, model)


def test_production_search_boundary_supplies_real_history_verifier():
    model, observed, _, worlds, scenes, contacts = history()
    boundary, _, reset, _, _, _ = _boundary()
    reset.model = model
    reset.sources = _sources(model, observed, worlds, scenes, contacts)
    verified = []

    def segment_factory(_sources_arg, _adapter, _scene, _geometry, **kwargs):
        verified.append(kwargs["history_verifier"](observed, 9.99))
        return SimpleNamespace(run=lambda _request_arg, *, reset_epoch: observed)

    boundary.segment_factory = segment_factory
    request = dict(_request(), session_id=reset.sources.session_id,
                   attempt_id=observed.search_result["attempt_id"])
    boundary.begin(request)
    assert boundary.search(request) is observed
    assert len(verified) == 1
    assert verified[0]["first_physics_step"] == 100
    assert verified[0]["selected_physics_step"] == 150
    assert verified[0]["command_authority"] is False
