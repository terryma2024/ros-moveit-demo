"""A proved default SEARCH binds one private expert source before any goal."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
import mujoco

from so101_demo.adapters.act.pick_place_search_port import (
    PickPlaceSearchPhasePort, PickPlaceSearchPortError,
)
from so101_demo.adapters.act.pick_place_child_port import (
    build_pick_place_child_search_port,
)
from so101_demo.adapters.act.visible_approach_expert_route import (
    VisibleApproachExpertRoute,
)

from test_act_task8_child_port import _inputs
from test_act_trusted_visible_approach_source import _case
from test_act_visible_approach_expert_route import POLICY, route


def _port(route, *, anchor="default", stop_after="APPROACH", factory_error=False):
    source_port, prior_port, broker, ticket, authority, source = _case(route)
    observed = prior_port.validated_search_observation()
    events = []
    request = {
        "mode": "phase_prefix", "stop_after": stop_after,
        "lifecycle": "FULL_RESTART", "scenario_id": "prefix-02",
        "session_id": source["session_id"], "attempt_id": source["attempt_id"],
        "deadline_ns": 9_000_000_000_000_000_000,
    }
    sources = SimpleNamespace(
        session_id=source["session_id"],
        contact_pairs=SimpleNamespace(
            model_sha256=route.manifest["model_sha256"], fingerprint=POLICY,
            for_phase=lambda _: frozenset()),
        contacts=SimpleNamespace(safe=lambda: True),
        readback=SimpleNamespace(max_skew=.02, joint_tolerance=.002),
    )
    reset = SimpleNamespace(
        sources=sources, broker=broker,
        manifest={"contact_policy_fingerprint": POLICY,
                  "prefix_cases": [{"case_id": "prefix-02", "anchor": anchor,
                                    "mode": "phase_prefix", "stop_after": stop_after,
                                    "lifecycle": "FULL_RESTART"}],
                  "full_cases": []},
        act_context={"lease_token": ticket[1]},
        receipt=SimpleNamespace(new_epoch=source["reset_epoch"]),
    )
    model = route.candidate.model
    neck_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, "neck_yaw_joint")
    sweep = SimpleNamespace(
        step_s=.002, neck_qpos=int(model.jnt_qposadr[neck_joint]),
        check=lambda *_args, **_kwargs: events.append("sweep") or True,
    )

    class Boundary:
        neck_sweep_checker = sweep

        def __init__(self):
            self.reset = reset

        def begin(self, item):
            events.append("reset")
            return {"session_id": item["session_id"],
                    "attempt_id": item["attempt_id"],
                    "reset_epoch": source["reset_epoch"],
                    "release_epoch": 0, "full_restart": False}

        def search(self, _item):
            events.append("search")
            return deepcopy(observed)

        def safe_stop(self, reason, _item):
            events.append(("stop", reason))
            broker.stop_attempt(reason)
            return True

    def factory(item):
        events.append("prevalidate")
        if factory_error:
            raise ValueError("ROUTE_PREVALIDATION_FAILED")
        assert item == request
        return route

    port = PickPlaceSearchPhasePort(Boundary(), expert_route_factory=factory)
    port.bind_startup_receipt({
        "schema_version": 1, "session_id": source["session_id"],
        "stack_owner": {"pid": 1}, "child_owner": {"pid": 2},
    })
    return port, request, events, authority, broker, ticket, source_port


def test_default_search_prevalidates_then_registers_private_source(route):
    port, request, events, authority, broker, ticket, source_port = _port(route)
    port.begin(request)
    evidence = port.run_phase("SEARCH", request)

    assert events == ["prevalidate", "reset", "search", "sweep"]
    assert evidence["phase"] == "SEARCH"
    assert authority._pending.source_kind == "EXPERT_ROUTE"
    assert authority._pending.owner_ticket == ticket
    assert source_port(ticket)["phase"] == "SEARCH"
    assert broker._goal_tickets == {}


def test_route_prevalidation_failure_prevents_reset_and_search(route):
    port, request, events, authority, broker, _, _ = _port(route, factory_error=True)
    with pytest.raises(PickPlaceSearchPortError, match="TASK8_BEGIN_EVIDENCE_INVALID"):
        port.begin(request)
    assert "reset" not in events and "search" not in events
    assert authority._pending is None
    assert broker.ownership.state != "RUNNING"
    with pytest.raises(PickPlaceSearchPortError, match="TASK8_BEGIN_REQUIRED"):
        port.run_phase("SEARCH", request)
    with pytest.raises(PickPlaceSearchPortError, match="TASK8_BEGIN_ALREADY_STARTED"):
        port.begin(request)


def test_changed_epoch_during_registration_stops_without_retaining_search(route):
    port, request, events, authority, broker, _, _ = _port(route)
    port.begin(request)
    broker.driver.current_epoch = lambda: {
        "session_id": request["session_id"], "reset_epoch": 99}
    with pytest.raises(PickPlaceSearchPortError, match="TASK8_SEARCH_EVIDENCE_INVALID"):
        port.run_phase("SEARCH", request)
    assert events[:3] == ["prevalidate", "reset", "search"]
    assert authority._pending is None
    assert broker._goal_tickets == {}
    assert broker.ownership.state != "RUNNING"
    with pytest.raises(PickPlaceSearchPortError,
                       match="PICK_PLACE_SEARCH_OBSERVATION_UNAVAILABLE"):
        port.validated_search_observation()


@pytest.mark.parametrize("anchor,stop_after", [
    ("default", "SEARCH"), ("left", "APPROACH"),
])
def test_search_only_and_other_anchor_do_not_register_expert_source(
        route, anchor, stop_after):
    port, request, events, authority, broker, _, _ = _port(
        route, anchor=anchor, stop_after=stop_after)
    port.begin(request)
    port.run_phase("SEARCH", request)
    assert "prevalidate" not in events
    assert authority._pending is None
    assert broker._goal_tickets == {}


def test_child_builder_prevalidates_expert_from_packaged_assets(tmp_path):
    inputs = _inputs(tmp_path)
    policy = inputs["manifest"]["contact_policy_fingerprint"]
    inputs["contact_pairs"].fingerprint = policy
    inputs["sources"].readback = SimpleNamespace(
        max_skew=.005, max_wall_age=.2, joint_tolerance=.002,
        cup_position_tolerance=.002,
    )
    inputs["command_broker"].driver = SimpleNamespace(stop_velocity=.002)

    def sweep_factory(*_args, **_kwargs):
        return SimpleNamespace(check=lambda *_args, **_kwargs: True, step_s=.002)

    def reset_factory(**kwargs):
        return SimpleNamespace(sources=kwargs["sources"])

    def boundary_factory(reset, **kwargs):
        return SimpleNamespace(
            reset=reset, neck_sweep_checker=kwargs["neck_sweep_checker"],
            begin=lambda _: None, search=lambda _: None,
            safe_stop=lambda *_: True,
        )

    port = build_pick_place_child_search_port(
        **inputs, sweep_factory=sweep_factory,
        reset_factory=reset_factory, boundary_factory=boundary_factory)
    expert = port._expert_route_factory({
        "session_id": inputs["sources"].session_id,
        "attempt_id": "attempt-296"})
    assert isinstance(expert, VisibleApproachExpertRoute)
    assert expert.manifest["policy_fingerprint"] == policy
    assert expert.manifest["expected_samples"] == 701
    assert expert.manifest["command_authority"] is False
