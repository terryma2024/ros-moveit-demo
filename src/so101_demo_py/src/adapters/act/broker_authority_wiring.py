"""Single production composition root for the Task 8 bound authority.

Real ordering (the C++ SOIA query is refused while the gate is unarmed, so identity
can never be confirmed at install time):

1. startup: construct the domain, seal + install the composition -- NO queries;
2. CommandBroker acquire: stop proof, then ``arm_generation(ticket)``;
3. only then confirm ``query_identity(role)`` for the live roles and require
   ``generation == ticket[0]``;
4. register the generation/domain/live ticket with the same composition.

Any partial role, failed query or generation drift closes the generation, revokes
ownership and returns no lease.
"""

from so101_demo.adapters.act.broker_authority_composition import BrokerAuthorityComposition
from so101_demo.adapters.act.ros_controller_port import RosControllerPort


def install_bound_authority(*, reservation_port, session_id, roles, history, admission,
                            registry):
    """Construct, seal and install the composition once. No identity queries here."""

    roles = tuple(roles)
    if not roles or any(role not in ("arm", "gripper", "neck") for role in roles):
        raise ValueError("BOUND_AUTHORITY_ROLES_INVALID")
    if history is None or admission is None or registry is None:
        raise ValueError("BOUND_AUTHORITY_DOMAIN_REQUIRED")
    composition = BrokerAuthorityComposition(history=history, admission=admission,
                                             registry=registry,
                                             controller_port=RosControllerPort(reservation_port),
                                             expected_roles=roles)
    reservation_port.install_authority(composition)
    return composition


def confirm_role_identities(*, reservation_port, composition, roles, ticket, ownership=None):
    """Post-arm confirmation: query every live role and bind the generation.

    Returns the confirmed per-role tuples. On any partial/failed/drifting result the
    generation is really closed (outside any client lock), ownership is revoked and
    the caller receives no lease.
    """

    roles = tuple(roles)
    if not isinstance(ticket, tuple) or len(ticket) != 5:
        raise ValueError("BOUND_AUTHORITY_TICKET_INVALID")
    generation = ticket[0]
    confirmed = {}
    for role in roles:
        try:
            snapshot = reservation_port.query_identity(role)
        except Exception:
            _abort(reservation_port, ownership, generation)
            raise
        if not isinstance(snapshot, tuple) or len(snapshot) != 3 or snapshot[0] != generation:
            _abort(reservation_port, ownership, generation)
            raise ValueError(f"BOUND_AUTHORITY_GENERATION_DRIFT:{role}:{snapshot}")
        confirmed[role] = snapshot
    try:
        # one atomic commit: either every live role is bound or none is
        composition.register_live_roles(entries=[
            {"role": role, "generation": snapshot[0], "incarnation": snapshot[1],
             "boot": snapshot[2], "ticket": ticket} for role, snapshot in confirmed.items()])
    except Exception:
        _abort(reservation_port, ownership, generation)
        raise
    return confirmed


def _abort(reservation_port, ownership, generation,
           reason="BOUND_AUTHORITY_ABORTED"):
    """Close the generation and revoke ownership; never return a lease on failure."""

    try:
        closer = getattr(reservation_port, "close", None)
        if callable(closer):
            closer(reason, generation=generation)   # one unified close call
        else:
            reservation_port.close_generation(generation)
    finally:
        if ownership is not None:
            detach = getattr(ownership, "revoke", None)
            if callable(detach):
                detach(f"BOUND_AUTHORITY_ABORTED:{generation}")


class BoundAuthoritySession:
    """One-shot bound-authority lifecycle shared by every production root.

    install() (startup, no I/O) -> arm(ticket) -> confirm() binds the frozen role set
    atomically. Any arm/confirm failure fences the session permanently: the
    composition is revoked and no further arm/confirm is accepted, and a successful
    confirm can never be repeated.
    """

    def __init__(self, *, reservation_port, session_id, roles, history, admission, registry):
        self.roles = tuple(roles)
        self.composition = install_bound_authority(
            reservation_port=reservation_port, session_id=session_id, roles=self.roles,
            history=history, admission=admission, registry=registry)
        self._reservation_port = reservation_port
        self._armed = None
        self._confirmed = False
        self._fenced_reason = None

    # --- state helpers ----------------------------------------------------
    @property
    def fenced_reason(self):
        return self._fenced_reason

    @property
    def reservation_port(self):
        """The client this session owns; the broker must be constructed with it."""

        return self._reservation_port

    def _fence(self, reason, original):
        """Revoke the composition once; never mask the original failure."""

        if self._fenced_reason is None:
            self._fenced_reason = reason
            try:
                self.composition.revoke(reason)
            except Exception:
                # the logical termination already ran inside revoke(); a controller
                # close failure must not replace the original error the caller sees
                pass
        return original

    def _refuse_if_unusable(self):
        if self._fenced_reason is not None:
            raise RuntimeError(f"BOUND_AUTHORITY_SESSION_FENCED:{self._fenced_reason}")
        if self._confirmed:
            raise RuntimeError("BOUND_AUTHORITY_SESSION_CONSUMED")

    def abort(self, reason="BOUND_AUTHORITY_ABORTED"):
        """Public idempotent fence: terminate the composition and close the generation.

        Safe to call on every post-arm non-commit path and repeatedly; the first
        terminal reason is preserved and the controller close happens at most once
        per live generation (the composition clears its live generation).
        """

        if self._fenced_reason is None:
            self._fenced_reason = reason
        try:
            self.composition.revoke(reason)
        except Exception:
            # the logical termination inside revoke() already ran; a controller close
            # failure must not mask the caller's original failure
            pass
        return self._fenced_reason

    # --- lifecycle --------------------------------------------------------
    def arm(self, ticket):
        self._refuse_if_unusable()
        if self._armed is not None:
            raise ValueError("BOUND_AUTHORITY_ALREADY_ARMED")
        try:
            armed = self._reservation_port.arm_generation(ticket)
        except Exception as failure:
            self._fence(f"ARM_ERROR:{failure}", failure)
            raise
        if armed is not True:
            self._fence("ARM_REFUSED", None)
            raise RuntimeError("BOUND_AUTHORITY_ARM_FAILED")
        self._armed = ticket
        return ticket[0]

    def confirm(self, ownership=None):
        self._refuse_if_unusable()
        if self._armed is None:
            raise ValueError("BOUND_AUTHORITY_NOT_ARMED")
        try:
            confirmed = confirm_role_identities(
                reservation_port=self._reservation_port, composition=self.composition,
                roles=self.roles, ticket=self._armed, ownership=ownership)
        except Exception as failure:
            self._fence(f"CONFIRM_ERROR:{failure}", failure)
            raise
        self._confirmed = True
        return confirmed


def build_bound_act_broker(*, reservation_port, session_id, roles, history, admission,
                           registry, driver, ownership, simulation_session_id=None,
                           prefix_source_authority=None, prefix_source_port=None):
    """The single production composition root for the Task-8 bound ACT path.

    One ControllerReservationClient instance backs all three consumers: the
    BoundAuthoritySession (and therefore its RosControllerPort), and the CommandBroker
    that dispatches through it. Construction performs no controller I/O: the session
    is only sealed and installed, and the per-role identities are confirmed later, at
    the exact ACT acquire, after arm_generation.
    """

    from so101_demo.adapters.act.command_broker import CommandBroker

    session = BoundAuthoritySession(reservation_port=reservation_port, session_id=session_id,
                                    roles=roles, history=history, admission=admission,
                                    registry=registry)
    broker = CommandBroker(driver, ownership=ownership,
                           simulation_session_id=simulation_session_id,
                           reservation_port=reservation_port,
                           prefix_source_authority=prefix_source_authority,
                           prefix_source_port=prefix_source_port,
                           authority=session.composition,
                           bound_authority_session=session)
    return {"session": session, "broker": broker}


def physics_clock_domain(*, session_id, nq, nv, settings, clock_ns=None):
    """Build the physics-clock domain the root passes to build_bound_act_broker.

    Pure construction from the root's calibrated settings: no controller I/O and no
    ROS calls, so the root's startup stays I/O-free. The settings keys are the ones
    ``bound_act_source_settings`` returns; a mismatch fails closed.
    """

    from so101_demo.adapters.act.authority_transaction import AuthorityTransactionRegistry
    from so101_demo.adapters.act.physics_clock_admission import PhysicsClockAdmission
    from so101_demo.adapters.act.physics_clock_history import PhysicsClockHistory

    if not isinstance(session_id, str) or not session_id:
        raise ValueError("BOUND_AUTHORITY_SESSION_REQUIRED")
    # P1-5: `clock_ns` defaults to None here, and None was forwarded explicitly to constructors whose own default is
    # `time.monotonic_ns` - so the default could never take effect and a caller that omitted the argument (which is what
    # `ros_child.py` does when it builds the ACT child) got PHYSICS_CLOCK_CONFIG_INVALID instead of a domain. Restoring
    # the default rather than inventing a clock: this is the same function the constructors themselves would have used.
    if clock_ns is None:
        import time as _time

        clock_ns = _time.monotonic_ns
    if type(nq) is not int or type(nv) is not int or nq <= 0 or nv <= 0:
        raise ValueError("BOUND_AUTHORITY_MODEL_INVALID")
    try:
        max_age_s = float(settings["max_wall_age_s"])
        max_sim_gap_s = float(settings["max_sim_gap_s"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("BOUND_AUTHORITY_SETTINGS_INVALID") from error
    if not 0 < max_age_s or not 0 < max_sim_gap_s:
        raise ValueError("BOUND_AUTHORITY_SETTINGS_INVALID")
    history = PhysicsClockHistory(session_id=session_id, nq=nq, nv=nv,
                                  max_age_s=max_age_s,
                                  max_source_step_gap_ns=int(max_sim_gap_s * 1e9),
                                  clock_ns=clock_ns)
    admission = PhysicsClockAdmission(history, selected_max_age_s=max_age_s,
                                      clock_ns=clock_ns)
    registry = AuthorityTransactionRegistry(clock_ns=clock_ns, history=history)
    return history, admission, registry
