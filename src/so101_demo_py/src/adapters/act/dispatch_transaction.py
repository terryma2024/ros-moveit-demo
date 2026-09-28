"""Authority-free offline dispatch transaction (Gate 5).

One callable transaction threads the real nodes of a dispatch:

    prepare -> claim -> reserve -> receive -> timeout -> receipt

Test barriers are installed *at these nodes* (``barrier("receive", fn)``) so an
interleaving is proven where it actually matters. The transaction holds no
authority: every stage is validated against the live admission identity and the
history commit receipt, the reservation freezes the full controller identity, and
timeout/unknown/malformed results are irreversible.
"""

from __future__ import annotations

import time

from so101_demo.adapters.act.authority_transaction import (ACCEPTED, REJECTED, UNKNOWN,
                                                           AuthorityRefused,
                                                           AuthorityTransactionRegistry,
                                                           ReservationFakeControllerPort)

NODES = ("prepare", "claim", "reserve", "receive", "timeout", "receipt")


class OfflineDispatchTransaction:
    """One offline dispatch attempt; never authorizes motion by itself."""

    def __init__(self, *, admission, history, registry, port, clock_ns=time.monotonic_ns,
                 permit_ttl_ns=30_000_000_000, selected_max_age_ns=350_000_000):
        self.admission = admission
        self.history = history
        self.registry = registry
        self.port = port
        registry.bind(admission=admission, history=history, port=port).seal()
        self._clock_ns = clock_ns
        self._permit_ttl_ns = permit_ttl_ns
        self._selected_max_age_ns = selected_max_age_ns
        self._barriers = {}
        self._stop_at = None
        self.unusable = False
        self.close_failed = False
        self.fencing_required = False
        self.state = "IDLE"
        self.failure = None
        self.receipt = None
        self.handle = None

    # ------------------------------------------------------------- test hooks
    def barrier(self, node, fn):
        if node not in NODES:
            raise ValueError(f"DISPATCH_NODE_UNKNOWN:{node}")
        self._barriers[node] = fn

    def node(self, node):
        fn = self._barriers.get(node)
        if fn is not None:
            fn(node)

    # ------------------------------------------------------------ transaction
    def run(self, *, stage, role, goal_uuid, target_digest, controller_generation,
            controller_incarnation, timeout_ns=None, stop_at=None):
        if self.unusable:
            # a closed transaction stays closed: this refusal is not an outcome
            raise AuthorityRefused("AUTHORITY_TRANSACTION_UNUSABLE")
        try:
            return self._run_guarded(
                stage=stage, role=role, goal_uuid=goal_uuid, target_digest=target_digest,
                controller_generation=controller_generation,
                controller_incarnation=controller_incarnation, timeout_ns=timeout_ns,
                stop_at=stop_at)
        except self.OPERATIONAL_ERRORS as error:
            if self.handle is None:
                # no permit was ever issued: this is a contract violation by the
                # caller (e.g. a generation that disagrees with the identity) and
                # must surface, not be swallowed as a terminal outcome
                raise
            # operational failures are terminal; process-control exceptions are not caught
            return self._fail_closed(f"{type(error).__name__}:{error}")

    def _run_guarded(self, *, stage, role, goal_uuid, target_digest, controller_generation,
                     controller_incarnation, timeout_ns=None, stop_at=None):
        """Run the transaction; ``stop_at`` halts after that node (test seam)."""

        if stop_at is not None and stop_at not in NODES:
            raise ValueError(f"DISPATCH_NODE_UNKNOWN:{stop_at}")
        changed = stop_at is not None
        previous_stop = self._stop_at
        if changed:
            self._stop_at = stop_at
        try:
            return self._run_nodes(stage=stage, role=role, goal_uuid=goal_uuid,
                                   target_digest=target_digest,
                                   controller_generation=controller_generation,
                                   controller_incarnation=controller_incarnation,
                                   timeout_ns=timeout_ns)
        finally:
            if changed:
                self._stop_at = previous_stop

    def _run_nodes(self, *, stage, role, goal_uuid, target_digest, controller_generation,
                   controller_incarnation, timeout_ns=None):
        self.node("prepare")
        identity = tuple(self.admission.identity)
        epoch = identity[4]
        token = {"identity": identity, "owner_identity": identity, "stage": stage,
                 "history_version": self.history.snapshot()["version"],
                 "incarnation": self.history.incarnation, "reset_epoch": epoch,
                 "physics_step": 1}
        try:
            self.handle = self.registry.issue_handle(
            identity=identity, stage=stage, step=1, history_version=token["history_version"],
            incarnation=token["incarnation"], epoch=epoch, role=role,
                controller_generation=controller_generation, goal_uuid=goal_uuid,
                target_digest=target_digest, controller_incarnation=controller_incarnation)
        except AuthorityRefused as error:
            # no permit exists yet: this is a pre-issue refusal, so there is
            # nothing to terminalize and no controller generation to close
            self.state, self.failure = "REJECTED", str(error)
            return self.state
        try:
            # broker-owned capture first (port mutex alone), then the claim
            self.registry.capture_controller_identity(self.handle)
            claim = self.registry.claim_bound(self.handle, identity=identity,
                                              controller_generation=controller_generation,
                                              token=token)
        except AuthorityRefused as error:
            return self._fail_closed(str(error))
        self.node("claim")
        try:
            frozen = self.registry.controller_snapshot_of(self.handle) or (None, None, None)
            reserved = self.port.reserve(
                permit_id=self.handle.permit_id, goal_uuid=goal_uuid, role=role,
                target_digest=target_digest, generation=controller_generation,
                controller_incarnation=controller_incarnation,
                expected_boot_incarnation=frozen[2],
                deadline_ns=claim.deadline_ns, stage=stage,
                session_id=identity[1], broker_incarnation=identity[2],
                claim_monotonic_ns=claim.commit_monotonic_ns)
        except AuthorityRefused as error:
            return self._fail_closed(str(error))
        if reserved != ACCEPTED:
            return self._fail_closed("AUTHORITY_RESERVATION_REFUSED")
        self.node("reserve")
        verdict = self.port.send(goal_uuid=goal_uuid, permit_id=self.handle.permit_id, role=role,
                                 target_digest=target_digest, generation=controller_generation,
                                 controller_incarnation=controller_incarnation,
                                 deadline_ns=claim.deadline_ns)
        self.node("receive")
        if self._should_stop("receive"):
            self.state = "IN_FLIGHT"
            return self.state
        if verdict != ACCEPTED:
            return self._fail_closed("DISPATCH_UNKNOWN")
        if timeout_ns is not None and self._clock_ns() - claim.commit_monotonic_ns > timeout_ns:
            self.node("timeout")
            return self._fail_closed("DISPATCH_TIMEOUT")
        self.node("timeout")
        try:
            fields = self.port.last_receipt(permit_id=self.handle.permit_id)
        except self.OPERATIONAL_ERRORS as error:
            return self._fail_closed(f"AUTHORITY_READBACK_FAILED:{error}")
        problem = self._receipt_field_problem(fields)
        if problem is not None:
            return self._fail_closed(problem)
        try:
            verdict = self.registry.receipt(self.handle, **fields)
        except self.OPERATIONAL_ERRORS + (TypeError, KeyError) as error:
            return self._fail_closed(f"AUTHORITY_RECEIPT_REFUSED:{error}")
        if verdict != ACCEPTED:
            # a structurally valid non-ACCEPTED receipt is a terminal outcome:
            # preserve its verdict and reason, but close through the same path
            reason = fields.get("reason") or verdict
            return self._fail_closed(f"AUTHORITY_RECEIPT_{verdict}:{reason}",
                                     terminal=(REJECTED if verdict == REJECTED else UNKNOWN))
        self.receipt = verdict
        self.state = self.receipt
        self.node("receipt")
        return self.state

    OPERATIONAL_ERRORS = (TimeoutError, OSError, ValueError, AuthorityRefused)

    def _controller_snapshot(self):
        """Broker-owned controller identity, read *before* the claim boundary.

        Taking it here keeps the controller-port mutex out of the claim boundary;
        ``reserve`` revalidates the same generation on the controller side.
        """

        port = self.port
        generation = port.current_generation() if hasattr(port, "current_generation") else None
        boot = port.boot_incarnation() if hasattr(port, "boot_incarnation") else "unknown"
        return {"generation": generation, "boot_incarnation": boot}

    def _receipt_field_problem(self, fields):
        """Return a refusal reason unless ``fields`` can bind safely.

        Exact string keys, no ``handle`` (which would collide with the positional
        argument) and exactly the frozen receipt field set are required, so the
        ``**fields`` expansion below cannot raise outside the fail-closed boundary.
        """

        from collections.abc import Mapping as _Mapping

        if not isinstance(fields, _Mapping):
            return "AUTHORITY_READBACK_INVALID"
        keys = list(fields.keys())
        if any(not isinstance(key, str) for key in keys):
            return "AUTHORITY_RECEIPT_KEY_TYPE"
        if "handle" in keys:
            return "AUTHORITY_RECEIPT_EXTRA_HANDLE"
        expected = set(self.registry.receipt_field_names())
        if set(keys) != expected:
            missing = sorted(expected - set(keys))
            extra = sorted(set(keys) - expected)
            return f"AUTHORITY_RECEIPT_FIELD_SET:missing={missing}:extra={extra}"
        return None

    def _fail_closed(self, reason, terminal=UNKNOWN):
        if terminal not in (UNKNOWN, REJECTED):
            raise ValueError(f"DISPATCH_TERMINAL_INVALID:{terminal}")
        """One irreversible closure: transaction, permit and controller port together.

        Called outside every critical section, so closing the controller port never
        happens under the registry, admission or history locks.
        """

        self.failure = reason
        self.unusable = True
        if self.handle is not None:
            try:
                # single-purpose terminalizer: a valid terminal receipt has already
                # persisted UNKNOWN/REJECTED, so terminate never needs an override
                self.registry.terminate(self.handle, reason=reason)
            except AuthorityRefused:
                pass
        try:
            self.port.close(reason)
        except Exception:  # noqa: BLE001 - a failed close is *not* success
            self.close_failed = True
            self.fencing_required = True
        self.state = terminal
        return self.state

    def _should_stop(self, node):
        return self._stop_at == node

    def run_to(self, stop_at, **kwargs):
        self._stop_at = stop_at
        try:
            return self.run(**kwargs)
        finally:
            self._stop_at = None
