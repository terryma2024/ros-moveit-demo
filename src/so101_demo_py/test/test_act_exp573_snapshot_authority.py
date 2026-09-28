"""EXP-573 P2: the controller identity snapshot is broker-owned, never caller data."""

import pytest

from test_act_dispatch_transaction import _run, _transaction
from test_act_physics_clock_history import SOURCE_BASE_NS, STEP_NS


def _issue(history, admission, registry, generation=None):
    return registry.issue_handle(identity=admission.identity, stage="route_dispatch", step=1,
                                 history_version=history.snapshot()["version"],
                                 incarnation=history.incarnation, epoch=admission.identity[4],
                                 role="arm",
                                 controller_generation=(admission.identity[3] if generation is None
                                                        else generation),
                                 goal_uuid="g-1", target_digest="d-1",
                                 controller_incarnation="i")


def _token(history, admission, registry):
    return {"identity": admission.identity, "owner_identity": admission.identity,
            "stage": "route_dispatch", "history_version": history.snapshot()["version"],
            "incarnation": history.incarnation, "reset_epoch": admission.identity[4],
            "physics_step": 1}


def test_claim_without_the_broker_capture_refuses():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    handle = _issue(history, admission, registry)
    with pytest.raises(Exception, match="AUTHORITY_CONTROLLER_GENERATION_CHANGED"):
        registry.claim_bound(handle, identity=admission.identity,
                             controller_generation=admission.identity[3],
                             token=_token(history, admission, registry))
    assert port.reserve_calls == 0 and port.accepted_commands == 0


def test_claim_bound_exposes_no_snapshot_parameter():
    import inspect

    from so101_demo.adapters.act.authority_transaction import AuthorityTransactionRegistry

    parameters = inspect.signature(AuthorityTransactionRegistry.claim_bound).parameters
    assert "controller_snapshot" not in parameters
    assert not any("snapshot" in name for name in parameters)


def test_caller_cannot_install_forged_snapshot_data():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    handle = _issue(history, admission, registry)
    with pytest.raises(TypeError):
        registry.capture_controller_identity(handle, snapshot=("forged", 1, "forged-boot"))
    assert registry.controller_snapshot_of(handle) is None
    with pytest.raises(TypeError):
        registry.claim_bound(handle, identity=admission.identity,
                             controller_generation=admission.identity[3],
                             token=_token(history, admission, registry),
                             controller_snapshot={"generation": 1, "boot_incarnation": "forged"})


def test_generation_change_between_capture_and_reserve_refuses_with_zero_send():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    registry.capture_controller_identity(_issue(history, admission, registry))
    port.arm_generation(2, controller_incarnation="i")       # rearm before reserve
    state = _run(tx)
    assert state in ("REJECTED", "UNKNOWN"), state
    assert port.send_calls == 0 and port.accepted_commands == 0
    assert tx.handle is None or registry.state_of(tx.handle) in ("UNKNOWN", "REJECTED")


def test_boot_change_between_capture_and_reserve_refuses_with_zero_send():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    registry.capture_controller_identity(_issue(history, admission, registry))
    port.restart_controller(controller_incarnation="i")      # restart before reserve
    state = _run(tx)
    assert state in ("REJECTED", "UNKNOWN"), state
    assert port.send_calls == 0 and port.accepted_commands == 0
    assert tx.handle is None or registry.state_of(tx.handle) in ("UNKNOWN", "REJECTED")


def test_normal_captured_flow_succeeds():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    assert _run(tx) == "ACCEPTED"
    assert port.accepted_commands == 1
    assert registry.controller_snapshot_of(tx.handle) is not None
