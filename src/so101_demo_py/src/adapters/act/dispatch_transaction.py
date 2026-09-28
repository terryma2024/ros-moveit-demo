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
        registry.bind(admission=admission, history=history, port=port)
        self._clock_ns = clock_ns
        self._permit_ttl_ns = permit_ttl_ns
        self._selected_max_age_ns = selected_max_age_ns
        self._barriers = {}
        self._stop_at = None
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
        self.handle = self.registry.issue_handle(
            identity=identity, stage=stage, step=1, history_version=token["history_version"],
            incarnation=token["incarnation"], epoch=epoch, role=role,
            controller_generation=controller_generation, goal_uuid=goal_uuid,
            target_digest=target_digest, controller_incarnation=controller_incarnation)
        try:
            claim = self.registry.claim_bound(self.handle, admission=self.admission,
                                              identity=identity,
                                              controller_generation=controller_generation,
                                              token=token)
        except AuthorityRefused as error:
            self.state, self.failure = "REJECTED", str(error)
            self.registry.terminate(self.handle, reason=self.failure)
            return self.state
        self.node("claim")
        try:
            reserved = self.port.reserve(
                permit_id=self.handle.permit_id, goal_uuid=goal_uuid, role=role,
                target_digest=target_digest, generation=controller_generation,
                controller_incarnation=controller_incarnation,
                deadline_ns=claim.deadline_ns, stage=stage,
                session_id=identity[1], broker_incarnation=identity[2],
                claim_monotonic_ns=claim.commit_monotonic_ns)
        except AuthorityRefused as error:
            self.state, self.failure = "REJECTED", str(error)
            self.registry.terminate(self.handle, reason=self.failure)
            return self.state
        if reserved != ACCEPTED:
            self.state = "REJECTED"
            self.failure = "AUTHORITY_RESERVATION_REFUSED"
            self.registry.terminate(self.handle, reason=self.failure)
            return self.state
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
            # timeout/unknown are irreversible: close the port *and* the permit
            self.port.close("DISPATCH_UNKNOWN")
            self.registry.terminate(self.handle, reason="DISPATCH_UNKNOWN")
            self.state = UNKNOWN
            return self.state
        if timeout_ns is not None and self._clock_ns() - claim.commit_monotonic_ns > timeout_ns:
            self.port.close("DISPATCH_TIMEOUT")
            self.registry.terminate(self.handle, reason="DISPATCH_TIMEOUT")
            self.state = UNKNOWN
            self.node("timeout")
            return self.state
        self.node("timeout")
        fields = self.port.last_receipt(permit_id=self.handle.permit_id)
        try:
            self.receipt = self.registry.receipt(self.handle, **fields)
        except AuthorityRefused as error:
            self.state, self.failure = UNKNOWN, str(error)
            self.registry.terminate(self.handle, reason=self.failure)
            return self.state
        self.state = self.receipt
        self.node("receipt")
        return self.state

    def _should_stop(self, node):
        return self._stop_at == node

    def run_to(self, stop_at, **kwargs):
        self._stop_at = stop_at
        try:
            return self.run(**kwargs)
        finally:
            self._stop_at = None
