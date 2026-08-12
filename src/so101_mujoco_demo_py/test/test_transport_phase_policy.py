from __future__ import annotations

import ast
from pathlib import Path

import pytest

from so101_mujoco_demo_py.dynamic_transport_evidence import ContactForceMode
from so101_mujoco_demo_py.mujoco.transport_observer import check_force

STATIC_THRESHOLD_N = 1.1579004532160448
DIAGNOSTIC_STOP_N = 11.60


def test_static_pretransport_hold_remains_fail_closed() -> None:
    decision = check_force(
        1.20,
        ContactForceMode.PRE_TRANSPORT_STATIC_HOLD,
        static_threshold_n=STATIC_THRESHOLD_N,
        diagnostic_stop_n=DIAGNOSTIC_STOP_N,
    )

    assert decision.cancel is True
    assert decision.static_threshold_crossed is True
    assert decision.diagnostic_hazard_breached is False


def test_dynamic_transport_records_static_crossing_without_canceling() -> None:
    decision = check_force(
        1.20,
        ContactForceMode.DYNAMIC_TRANSPORT_SHADOW,
        static_threshold_n=STATIC_THRESHOLD_N,
        diagnostic_stop_n=DIAGNOSTIC_STOP_N,
    )

    assert decision.cancel is False
    assert decision.static_threshold_crossed is True
    assert decision.diagnostic_hazard_breached is False


@pytest.mark.parametrize("force_n", [DIAGNOSTIC_STOP_N, DIAGNOSTIC_STOP_N + 0.01])
def test_dynamic_diagnostic_stop_is_inclusive_and_has_no_grace(force_n: float) -> None:
    decision = check_force(
        force_n,
        ContactForceMode.DYNAMIC_TRANSPORT_SHADOW,
        static_threshold_n=STATIC_THRESHOLD_N,
        diagnostic_stop_n=DIAGNOSTIC_STOP_N,
    )

    assert decision.cancel is True
    assert decision.diagnostic_hazard_breached is True


def test_force_policy_requires_a_typed_mode() -> None:
    with pytest.raises(TypeError, match="ContactForceMode"):
        check_force(
            1.0,
            "DYNAMIC_TRANSPORT_SHADOW",  # type: ignore[arg-type]
            static_threshold_n=STATIC_THRESHOLD_N,
            diagnostic_stop_n=DIAGNOSTIC_STOP_N,
        )


def test_live_transport_wires_static_prehold_and_dynamic_postsettle_explicitly() -> None:
    source_path = (
        Path(__file__).parents[1] / "so101_mujoco_demo_py" / "live_phases" / "transport.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    stable_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "stable_bilateral"
    ]
    modes = [ast.unparse(call.args[1]) for call in stable_calls if len(call.args) >= 2]

    assert modes == [
        "ContactForceMode.PRE_TRANSPORT_STATIC_HOLD",
        "ContactForceMode.DYNAMIC_TRANSPORT_SHADOW",
    ]
    assert "on_goal_dispatched=goal_dispatched" in source
    assert "checkpoint_producer_provenance" in source
    assert "checkpoint_snapshot_session" in source
    assert '"publisher_provenance"' in source
    assert "force boundary exceeded during transport" not in source
