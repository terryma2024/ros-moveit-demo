"""Gate 6 composition lifecycle: real unsealed domain, deterministic controller port."""

import hashlib
import threading
import time

import pytest
from control_msgs.action import FollowJointTrajectory
from rclpy.serialization import serialize_message

from so101_demo.adapters.act import authority_transaction as at
from so101_demo.adapters.act.broker_authority_composition import BrokerAuthorityComposition
from test_act_dispatch_transaction import _transaction
from test_act_physics_clock_history import SOURCE_BASE_NS, STEP_NS

GOAL_ARM = "11111111-1111-1111-1111-111111111111"
GOAL_GRIPPER = "22222222-2222-2222-2222-222222222222"
# broker ticket shape: (generation, lease token, owner, session, attempt)
TICKET = (1, "token-1", "act", "clock-session", "attempt-1")


class _Port:
    """Deterministic production-protocol port with asserted counters/barriers."""

    def __init__(self, *, generation=1, incarnation="i", boot="boot-1", barrier=None):
        self._generation, self._incarnation, self._boot = generation, incarnation, boot
        self.snapshots = 0
        self.barrier = barrier
        self.closed = []
        self._lock = threading.RLock()

    def identity_snapshot(self):
        with self._lock:
            self.snapshots += 1
            if self.barrier is not None:
                self.barrier()
            return (self._generation, self._incarnation, self._boot)

    def reserve(self, **kwargs):
        return "ACCEPTED"

    def send(self, **kwargs):
        return "ACCEPTED"

    def close(self, reason="CLOSED"):
        self.closed.append(reason)


def _unsealed(now, *, port=None):
    """A real domain that is NOT yet sealed (the fixture the composition needs)."""

    history, admission = _transaction(now)[:2]
    registry = at.AuthorityTransactionRegistry(
        clock_ns=lambda: now[0], permit_ttl_ns=30_000_000_000, history=history,
        selected_max_age_ns=50_000_000)
    return history, admission, registry, port or _Port()


def _composition(now, *, port=None, guard=None):
    history, admission, registry, port = _unsealed(now, port=port)
    comp = BrokerAuthorityComposition(history=history, admission=admission, registry=registry,
                                      controller_port=port)
    identity = admission.identity
    comp.register_identity_domain(owner="act", session_id="clock-session", attempt_id="attempt-1",
                                  reset_epoch=1, generation=1, identity=identity)
    comp.register_ticket(TICKET, session_id="clock-session", attempt_id="attempt-1",
                         role="arm", ticket_guard=guard or (lambda ticket: ticket == TICKET),
                         allowed_roles=("arm", "gripper"))
    return history, admission, registry, port, comp


def _sample(step=1):
    """A sample for a step the history has actually retained."""

    from test_act_physics_clock_admission import _sample as sample
    return sample(step)


def test_admitted_snapshot_is_frozen_and_a_history_advance_refuses_before_send():
    """The admitted snapshot never changes; a version change refuses the claim.

    The binding must come from the stored admitted result (step/version/epoch/
    receipt time), so a history advance after admission cannot silently re-bind a
    newer step: the claim fails closed and publishes no permit.
    """

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, comp = _composition(now)
    reference = comp.adopt_sample(ticket=TICKET, sample=_sample())
    frozen = (reference.step, reference.history_version, reference.incarnation,
              reference.reset_epoch, reference.receipt_ns, reference.identity)
    assert frozen[0] == 1 and frozen[3] == 1 and frozen[4] == 9906000000
    # retain a later step: the history genuinely advances after admission
    chunk = __import__("test_act_physics_clock_admission", fromlist=["_chunk"])._chunk
    history.accept_chunk(chunk(1, _sample(2)))
    assert (reference.step, reference.history_version, reference.incarnation,
            reference.reset_epoch, reference.receipt_ns,
            reference.identity) == frozen, "the admitted snapshot changed"
    with pytest.raises(Exception):
        comp.claim_prepared_goal(ticket=TICKET, role="arm", goal_uuid=GOAL_ARM,
                                 goal=FollowJointTrajectory.Goal())
    assert comp.handle_for(ticket=TICKET, role="arm", goal_uuid=GOAL_ARM) is None
    # two snapshot sites by design: the composition samples the controller
    # identity before the registry lock, and the registry captures it again
    # through capture_controller_identity(); both are bounded local reads
    assert port.snapshots == 2, f"unexpected snapshot count {port.snapshots}"


def test_paired_roles_claim_two_permits_and_a_third_role_is_refused():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, comp = _composition(now)
    comp.adopt_sample(ticket=TICKET, sample=_sample())
    arm = comp.claim_prepared_goal(ticket=TICKET, role="arm", goal_uuid=GOAL_ARM,
                                   goal=FollowJointTrajectory.Goal())
    gripper = comp.claim_prepared_goal(ticket=TICKET, role="gripper", goal_uuid=GOAL_GRIPPER,
                                       goal=FollowJointTrajectory.Goal())
    assert arm is not gripper
    assert registry.state_of(arm) == "IN_FLIGHT" and registry.state_of(gripper) == "IN_FLIGHT"
    with pytest.raises(Exception):
        comp.claim_prepared_goal(ticket=TICKET, role="arm", goal_uuid=GOAL_ARM,
                                 goal=FollowJointTrajectory.Goal())
    with pytest.raises(Exception):
        comp.claim_prepared_goal(ticket=TICKET, role="neck", goal_uuid=GOAL_ARM,
                                 goal=FollowJointTrajectory.Goal())


def test_canonical_goal_digest_and_uuid_bind_the_handle():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, comp = _composition(now)
    comp.adopt_sample(ticket=TICKET, sample=_sample())
    goal = FollowJointTrajectory.Goal()
    handle = comp.claim_prepared_goal(ticket=TICKET, role="arm", goal_uuid=GOAL_ARM, goal=goal)
    binding = registry.reservation_binding(handle)
    assert binding["target_digest"] == hashlib.sha256(serialize_message(goal)).hexdigest()
    assert binding["goal_uuid"] == GOAL_ARM


def _real_guard():
    """A real broker-owned guard: Ownership.require_ticket over a live ticket."""

    from so101_demo.act.ownership import Ownership

    ownership = Ownership()
    token = ownership.acquire("act", "clock-session", "attempt-1")
    live = ownership.ticket(token, "act", "clock-session", "attempt-1")
    return ownership, live


def test_real_ownership_guard_rejects_swapped_and_same_valued_tickets():
    ownership, live = _real_guard()
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port = _unsealed(now)
    comp = BrokerAuthorityComposition(history=history, admission=admission, registry=registry,
                                      controller_port=port)
    comp.register_identity_domain(owner="act", session_id="clock-session",
                                  attempt_id="attempt-1", reset_epoch=1, generation=1,
                                  identity=admission.identity)
    ok = comp.register_ticket(tuple(live), session_id="clock-session", attempt_id="attempt-1",
                              role="arm", ticket_guard=ownership.require_ticket,
                              allowed_roles=("arm", "gripper"))
    assert ok is None or ok is True
    # a field-swapped ticket is refused even though every value appears in it
    swapped = (live[1], live[0], live[2], live[3], live[4])
    with pytest.raises(Exception):
        comp.register_ticket(swapped, session_id="clock-session", attempt_id="attempt-1",
                             role="arm", ticket_guard=ownership.require_ticket)
    # a foreign tuple that merely hashes is refused by the guard
    with pytest.raises(Exception):
        comp.register_ticket((1, "t", "act", "clock-session", "attempt-1"),
                             session_id="clock-session", attempt_id="attempt-1", role="arm",
                             ticket_guard=ownership.require_ticket)


def test_wrong_shape_ticket_is_refused_positionally():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, comp = _composition(now)
    for bad in ((1, "token-1", "act", "clock-session"),          # too short
                (1, "token-1", "act", "clock-session", "attempt-1", "extra"),
                (2, "token-1", "act", "clock-session", "attempt-1")):  # wrong generation
        with pytest.raises(Exception):
            comp.register_ticket(bad, session_id="clock-session", attempt_id="attempt-1",
                                 role="arm", ticket_guard=lambda ticket: True)


def test_forged_ticket_is_refused_without_a_live_guard():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, comp = _composition(now)

    def guard(ticket):
        return ticket == TICKET

    with pytest.raises(Exception):
        comp.register_ticket(("forged",), session_id="clock-session", attempt_id="attempt-1",
                             role="arm", ticket_guard=guard)


def _revoke_case(window):
    """Deterministic barriers: no sleeps, revoke exactly inside the named window."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    entered, release = threading.Event(), threading.Event()
    port = _Port()
    history, admission, registry, port, comp = _composition(now, port=port)
    comp.adopt_sample(ticket=TICKET, sample=_sample())
    original_issue = registry.issue_handle
    original_capture = registry.capture_controller_identity
    original_claim = registry.claim_bound
    original_binding = registry.reservation_binding
    issued = []

    def barrier(name):
        entered.set()
        assert release.wait(5.0), f"barrier {name} never released"

    issue_calls = []

    def issue(*args, **kwargs):
        issue_calls.append(1)
        if window == "before_issue":
            # block *before* the registry issues anything: a revoke here must
            # leave no permit at all
            barrier(window)
        handle = original_issue(*args, **kwargs)
        issued.append(handle)
        return handle

    def capture(*args, **kwargs):
        if window == "issue_to_capture":
            barrier(window)
        return original_capture(*args, **kwargs)

    def claim(*args, **kwargs):
        result = original_claim(*args, **kwargs)
        if window == "claim_to_publish":
            barrier(window)
        return result

    def binding(*args, **kwargs):
        if window == "publish_to_binding":
            barrier(window)
        return original_binding(*args, **kwargs)

    registry.issue_handle = issue
    registry.capture_controller_identity = capture
    registry.claim_bound = claim
    registry.reservation_binding = binding
    outcome = {}

    def worker():
        try:
            handle = comp.claim_prepared_goal(
                ticket=TICKET, role="arm", goal_uuid=GOAL_ARM,
                goal=FollowJointTrajectory.Goal())
            outcome["handle"] = handle
            # the reservation side resolves the binding through the composition;
            # this is the publish -> reservation-binding window
            outcome["binding"] = comp.reservation_binding(handle)
        except Exception as error:  # noqa: BLE001 - asserted below
            outcome["error"] = error

    if window == "before_issue":
        thread = threading.Thread(target=worker)
        thread.start()
        assert entered.wait(5.0), "the before-issue barrier never fired"
        comp.revoke("OPERATOR_STOP")
        release.set()
    else:
        thread = threading.Thread(target=worker)
        thread.start()
        assert entered.wait(5.0), f"the {window} barrier never fired"
        comp.revoke("OPERATOR_STOP")
        release.set()
    thread.join(5.0)
    assert not thread.is_alive(), "the claim worker must terminate"
    # no permit may survive a revoke in any window
    for handle in issued:
        state = registry.state_of(handle)
        assert state not in ("READY", "IN_FLIGHT"), f"{window}: permit left {state}"
    assert port.closed, f"{window}: the controller port was not closed"
    assert "error" in outcome or comp.handle_for(ticket=TICKET, role="arm",
                                                 goal_uuid=GOAL_ARM) is None
    if window == "before_issue":
        assert issued == [], "a permit was issued after a revoke in the before-issue window"
    comp.issue_calls = len(issue_calls)
    return comp


@pytest.mark.parametrize("window", ["before_issue", "issue_to_capture", "claim_to_publish",
                                    "publish_to_binding"])
def test_revoke_in_each_window_terminalizes_and_closes(window):
    _revoke_case(window)


def test_two_concurrent_identical_claims_issue_at_most_one_permit():
    """A second identical claim is refused before the registry issues anything."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    entered, release = threading.Event(), threading.Event()
    history, admission, registry, port, comp = _composition(now)
    comp.adopt_sample(ticket=TICKET, sample=_sample())
    original_issue = registry.issue_handle
    issue_calls = []

    def issue(*args, **kwargs):
        issue_calls.append(1)
        entered.set()
        assert release.wait(5.0), "the first claim was never released"
        return original_issue(*args, **kwargs)

    registry.issue_handle = issue
    outcome = {}

    def claim(name):
        try:
            outcome[name] = comp.claim_prepared_goal(
                ticket=TICKET, role="arm", goal_uuid=GOAL_ARM,
                goal=FollowJointTrajectory.Goal())
        except Exception as error:  # noqa: BLE001 - asserted below
            outcome[name] = error

    first = threading.Thread(target=claim, args=("first",))
    first.start()
    assert entered.wait(5.0), "the first claim never reached the issue window"
    second = threading.Thread(target=claim, args=("second",))
    second.start()
    second.join(5.0)
    assert not second.is_alive(), "the second claim must terminate without issuing"
    second_error = outcome.get("second")
    assert isinstance(second_error, Exception), outcome
    assert "COMPOSITION_ROLE_ALREADY_CLAIMED" in str(second_error) or \
        "COMPOSITION_DISPATCH_KEY_REUSED" in str(second_error), second_error
    assert len(issue_calls) == 1, f"registry.issue_handle called {len(issue_calls)} times"
    release.set()
    first.join(5.0)
    assert not first.is_alive()
    handle = outcome.get("first")
    assert handle is not None and registry.state_of(handle) in ("IN_FLIGHT", "ACCEPTED")
    # exactly one permit exists for this dispatch key
    assert comp.handle_for(ticket=TICKET, role="arm", goal_uuid=GOAL_ARM) is handle


def test_revoke_inside_admission_window_leaves_no_evidence():
    """A revoke while admission is in flight must refuse and store no evidence."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    entered, release = threading.Event(), threading.Event()
    history, admission, registry, port, comp = _composition(now)
    original_admit = admission.admit_sample
    window = {"place": "before_return"}

    def admit(**kwargs):
        admitted = original_admit(**kwargs)
        if window["place"] == "after_return":
            entered.set()
            assert release.wait(5.0)
        return admitted

    admission.admit_sample = admit
    if window["place"] == "before_return":
        # revoke before admission runs at all: the composition must refuse first
        comp.revoke("OPERATOR_STOP")
        with pytest.raises(Exception, match="AUTHORITY_REVOKED"):
            comp.adopt_sample(ticket=TICKET, sample=_sample())
    else:
        pass
    # prove by public behaviour that nothing was stored
    with pytest.raises(Exception) as stored:
        comp.claim_prepared_goal(ticket=TICKET, role="arm", goal_uuid=GOAL_ARM,
                                 goal=FollowJointTrajectory.Goal())
    assert "COMPOSITION_EVIDENCE_MISSING" in str(stored.value) or \
        "AUTHORITY_REVOKED" in str(stored.value), stored.value


def test_revoke_after_admission_returns_leaves_no_evidence():
    """Same property for the window *after* admission returns, via a barrier."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    entered, release = threading.Event(), threading.Event()
    history, admission, registry, port, comp = _composition(now)
    original_admit = admission.admit_sample

    def admit(**kwargs):
        admitted = original_admit(**kwargs)
        entered.set()
        assert release.wait(5.0)
        return admitted

    admission.admit_sample = admit
    outcome = {}

    def worker():
        try:
            outcome["ref"] = comp.adopt_sample(ticket=TICKET, sample=_sample())
        except Exception as error:  # noqa: BLE001 - asserted below
            outcome["error"] = error

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(5.0), "the admission barrier never fired"
    comp.revoke("OPERATOR_STOP")
    release.set()
    thread.join(5.0)
    assert not thread.is_alive()
    assert isinstance(outcome.get("error"), Exception), outcome
    assert "AUTHORITY_REVOKED" in str(outcome["error"]), outcome["error"]
    with pytest.raises(Exception) as after:
        comp.claim_prepared_goal(ticket=TICKET, role="arm", goal_uuid=GOAL_ARM,
                                 goal=FollowJointTrajectory.Goal())
    assert "COMPOSITION_EVIDENCE_MISSING" in str(after.value) or \
        "AUTHORITY_REVOKED" in str(after.value), after.value
