"""Phase 3b A-prime root wiring: one shared client, one session, zero startup I/O.

The root must build the bound authority through a single testable factory so the
broker, the session and the registry port all share the exact same client object.
"""

import inspect

import pytest


def _factory():
    """The single production composition root helper (must exist in the root module)."""

    from so101_demo.adapters.act import broker_authority_wiring as wiring

    factory = getattr(wiring, "build_bound_act_broker", None)
    assert factory is not None, (
        "the root has no single bound-authority factory: broker, session and port "
        "cannot be proven to share one client")
    return factory


class _Driver:
    def __init__(self):
        self.stopped_flag = True

    def stopped(self):
        return self.stopped_flag

    def stop_all(self, reason="STOP"):
        self.stopped_flag = True
        return True

    def prepare_goal(self, *a, **k):
        return "uuid-1"

    def send_prepared(self, *a, **k):
        return True

    def discard_prepared(self, *a, **k):
        return True


class _Ownership:
    """Real Ownership is used in the lifecycle suites; here the broker only binds it."""

    state = "IDLE"

    def bind_control_events(self, events):
        return True

    def confirm_stopped(self, *a, **k):
        return True

    def acquire(self, *scope):
        self.state = "RUNNING"
        return "lease-root"

    def ticket(self, token, *scope):
        return (1, token) + tuple(scope)

    def authorized(self, *scope):
        class _Ctx:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, *exc):
                return False

        return _Ctx()

    def require_ticket(self, ticket):
        return True


class _Client:
    """Records every controller interaction; nothing may happen at construction."""

    def __init__(self):
        self.calls = []

    def arm_generation(self, ticket):
        self.calls.append(("arm", ticket))
        return True

    def query_identity(self, role):
        self.calls.append(("query", role))
        return (1, f"inc-{role}", f"boot-{role}")

    def reserve(self, *a, **k):
        self.calls.append(("reserve",))
        return True

    def close_generation(self, generation):
        self.calls.append(("close", generation))
        return True

    def close(self, reason="CLOSED", generation=None):
        self.calls.append(("close_unified", generation))
        return True

    def close_all_attempted(self):
        return []

    def identity_snapshot(self, role):
        return (1, f"inc-{role}", f"boot-{role}")

    def install_authority(self, authority):
        self.calls.append(("install_authority",))
        self.authority = authority
        return True


class _History:
    version = 1
    incarnation = "clock-session"


class _Admission:
    def owner_is_active(self):
        return True

    def revoke_current(self, reason):
        self.revoked = reason
        return True


class _Registry:
    pass


def _domain():
    from so101_demo.adapters.act.authority_transaction import AuthorityTransactionRegistry

    history = _History()
    return history, _Admission(), AuthorityTransactionRegistry(clock_ns=lambda: 9906000000,
                                                              history=history)


def test_factory_exists_and_takes_a_client_it_does_not_duplicate():
    factory = _factory()
    parameters = inspect.signature(factory).parameters
    assert "reservation_port" in parameters or "client" in parameters, parameters


def _real_client():
    from so101_demo.adapters.act.controller_reservation_client import ControllerReservationClient

    return ControllerReservationClient({"arm": "/tmp/root-arm", "gripper": "/tmp/root-grip"},
                                       capability={"arm": b"a" * 32, "gripper": b"b" * 32},
                                       timeout_s=1.0)


def test_root_wiring_performs_zero_controller_io_at_construction():
    factory = _factory()
    client = _real_client()
    history, admission, registry = _domain()
    built = factory(reservation_port=client, session_id="clock-session",
                    roles=("arm", "gripper"), history=history, admission=admission,
                    registry=registry, driver=_Driver(), ownership=_Ownership())
    session = built["session"]
    # no identity was confirmed and no generation was armed at startup
    assert session._confirmed is False and session._armed is None
    with pytest.raises(Exception):
        client.identity_snapshot("arm")      # nothing was queried, so nothing is cached


def test_broker_session_and_port_share_one_client_object():
    factory = _factory()
    client = _real_client()
    history, admission, registry = _domain()
    built = factory(reservation_port=client, session_id="clock-session",
                    roles=("arm", "gripper"), history=history, admission=admission,
                    registry=registry, driver=_Driver(), ownership=_Ownership())
    session = built["session"] if isinstance(built, dict) else built.session
    broker = built["broker"] if isinstance(built, dict) else built.broker
    assert session.reservation_port is client, "the session must own the same client"
    assert broker.reservation_port is client, "the broker must use the same client"
    assert broker.authority is session.composition, "the broker must use the session's domain"
    assert broker._bound_authority_session is session


def test_physics_clock_domain_builds_from_the_root_settings_without_io():
    """The root must be able to build its domain purely from calibrated settings."""

    from so101_demo.adapters.act.broker_authority_wiring import physics_clock_domain

    settings = {"stop_velocity_rad_s": 0.2, "max_wall_age_s": 0.25,
                "max_source_skew_s": 0.2, "max_sim_gap_s": 0.003,
                "joint_tolerance_rad": 0.002}
    history, admission, registry = physics_clock_domain(
        session_id="clock-session", nq=6, nv=6, settings=settings,
        clock_ns=lambda: 9906000000)
    assert history.incarnation == "clock-session"
    assert history.version == 0, "a fresh history has no committed sample yet"
    assert registry is not None and admission is not None


def test_physics_clock_domain_fails_closed_on_bad_inputs():
    from so101_demo.adapters.act.broker_authority_wiring import physics_clock_domain

    good = {"max_wall_age_s": 0.25, "max_sim_gap_s": 0.003}
    with pytest.raises(ValueError, match="SESSION_REQUIRED"):
        physics_clock_domain(session_id="", nq=6, nv=6, settings=good)
    with pytest.raises(ValueError, match="MODEL_INVALID"):
        physics_clock_domain(session_id="s", nq=0, nv=6, settings=good)
    for broken in ({}, {"max_wall_age_s": 0.25}, {"max_wall_age_s": -1, "max_sim_gap_s": 1e-3},
                   {"max_wall_age_s": 0.25, "max_sim_gap_s": 0}):
        with pytest.raises(ValueError, match="SETTINGS_INVALID"):
            physics_clock_domain(session_id="s", nq=6, nv=6, settings=broken)


def _root_source():
    """Locate the root module in either the source tree or a test mirror layout."""

    from pathlib import Path

    here = Path(__file__).resolve()
    candidates = []
    for base in here.parents:
        candidates.append(base / "so101_teleop" / "so101_teleop" / "unified" / "ros_child.py")
        candidates.append(base / "src" / "so101_teleop" / "so101_teleop" / "unified" / "ros_child.py")
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(), candidate.parent
    raise AssertionError(f"ros_child.py not found from {here}")


def test_root_bound_wiring_is_gated_on_the_task8_profile():
    """A-prime scope: only the admitted Task-8 profile installs the bound session.

    The root needs rclpy to execute, so this guards the gate structurally: the bound
    branch must sit behind the hash-bound Task-8 manifest check and must be gated, never
    unconditional; the legacy broker construction must remain the else-branch.
    """

    source, root = _root_source()
    assert root.joinpath("ros_child.py").exists(), "the root module moved"
    gate = '_manifest.get("kind") == "ACT_TASK8_LIVE"'
    assert gate in source, "the Task-8 profile gate is missing from the root wiring"
    # the bound construction sits after the gate and the legacy construction is the else
    gate_at = source.index(gate)
    bound_at = source.index("build_bound_act_broker(", gate_at)
    legacy_at = source.index("self._act_command_broker = CommandBroker(", gate_at)
    assert gate_at < bound_at < legacy_at, (
        "the bound wiring must be gated before the legacy fallback, in that order")
    # no unconditional bound install: the call must be inside the gated branch
    assert source.count("build_bound_act_broker(") == 1, "bound wiring must appear once"
    assert "self._act_bound_session = _bound[\"session\"]" in source, (
        "the root must keep the one-shot session it installed")


def test_root_uses_one_client_shared_by_session_and_broker():
    source, _ = _root_source()
    # the factory is called with the same reservation_port object created above it
    assert "reservation_port=reservation_port" in source, (
        "the bound wiring must pass the root's own client instance")
