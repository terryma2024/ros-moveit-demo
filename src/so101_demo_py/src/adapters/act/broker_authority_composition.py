"""Sole owner of the sealed Gate-6 authority domain for one CommandBroker process.

One instance per real broker process. It owns the physics adapter/history,
admission, the controller port and the sealed registry, derives every authority
value internally, and is the only source of reservation bindings.

Lifecycle
---------
1. compose (build dependencies) and ``seal()`` once, before any permit exists;
2. register the broker-owned identity domain and the live tickets;
3. ``adopt_sample`` — the SEARCH/source side hands over only a *physical sample*;
   the composition calls its owned admission/history and stores an immutable
   admitted-evidence reference (no raw authority field crosses this API);
4. ``claim_prepared_goal`` — after ``prepare_goal`` returns the real UUID, the
   composition consumes the stored evidence, derives the target digest from the
   exact prepared-goal bytes, issues/captures/claims and stores the handle under
   an immutable dispatch key ``(ticket, role, goal_uuid)``;
5. the broker reserves with that opaque handle only.

Lock order: the composition lock protects only its own state transitions and is
never held across controller socket I/O, a history deepcopy, or a port close.
"""

import hashlib
import threading

from rclpy.serialization import serialize_message
from collections import namedtuple

from so101_demo.adapters.act.authority_transaction import (
    AuthorityRefused,
    AuthorityTransactionRegistry,
)

AdmittedEvidence = namedtuple(
    "AdmittedEvidence",
    "reference ticket role step history_version incarnation reset_epoch identity "
    "receipt_ns fingerprint allowed_roles")
DispatchKey = namedtuple("DispatchKey", "ticket role goal_uuid")


class BrokerAuthorityComposition:
    """Owns admitted evidence, the dispatch keys and the sealed registry."""

    def __init__(self, *, history, admission, registry, controller_port,
                 expected_roles=None):
        if type(registry) is not AuthorityTransactionRegistry:
            raise TypeError("COMPOSITION_REGISTRY_INVALID")
        if getattr(registry, "_sealed", False):
            raise ValueError("COMPOSITION_REGISTRY_ALREADY_SEALED")
        # the production port contract is narrow on purpose: identity snapshot plus a
        # real generation closure. reserve/send are NOT part of it -- the only
        # dispatch path is CommandBroker.claim_prepared_goal -> reserve_bound -> send.
        for name, value in (("identity_snapshot",
                             getattr(controller_port, "identity_snapshot", None)),
                            ("close", getattr(controller_port, "close", None))):
            if not callable(value):
                raise TypeError(f"COMPOSITION_PORT_INVALID:{name}")
        self.history = history
        self.admission = admission
        self.controller_port = controller_port
        self.registry = registry
        # one-time seal before any permit can be issued
        registry.bind(admission=admission, history=history, port=controller_port).seal()
        self._sealed = True
        self._lock = threading.RLock()
        self._domains: dict = {}
        self._tickets: dict = {}
        self._evidence: dict = {}
        self._identities: dict = {}
        self._expected_roles: tuple = tuple(expected_roles) if expected_roles else ()
        self._live_generation = None
        self._handles: dict = {}
        self._used_keys: set = set()
        self._used_roles: dict = {}
        self._pending_keys: set = set()
        self._pending_roles: dict = {}
        self._revoked_reason: str | None = None

    # --- ownership ----------------------------------------------------------
    def sealed(self) -> bool:
        with self._lock:
            return self._sealed

    def register_identity_domain(self, *, owner, session_id, attempt_id, reset_epoch,
                                 generation, identity):
        """Store the broker-owned identity-domain mapping explicitly.

        The broker ticket tuple is *not* assumed to be the admission identity:
        the mapping is recorded here from broker-owned fields and validated.
        """

        if owner != "act" or not session_id or not attempt_id:
            raise ValueError("COMPOSITION_DOMAIN_INVALID")
        if (type(reset_epoch) is not int or type(generation) is not int
                or type(identity) is not tuple or len(identity) != 5
                or identity[1] != session_id or identity[3] != generation):
            raise ValueError("COMPOSITION_DOMAIN_MISMATCH")
        with self._lock:
            self._domains[(session_id, attempt_id)] = {
                "owner": owner, "session_id": session_id, "attempt_id": attempt_id,
                "reset_epoch": reset_epoch, "generation": generation, "identity": identity}

    def register_live_roles(self, *, entries):
        """Atomically bind every ACK-confirmed live role (all or none)."""

        if not entries:
            raise ValueError("COMPOSITION_ROLES_EMPTY")
        staged = {}
        generation = None
        for entry in entries:
            role = entry.get("role")
            if role not in ("arm", "gripper", "neck"):
                raise ValueError("COMPOSITION_ROLE_INVALID")
            if role in staged:
                raise ValueError("COMPOSITION_ROLE_DUPLICATE")
            value = entry.get("generation")
            if type(value) is not int or value <= 0:
                raise ValueError("COMPOSITION_GENERATION_INVALID")
            if generation is None:
                generation = value
            elif value != generation:
                raise ValueError("COMPOSITION_GENERATION_DRIFT")
            incarnation, boot = entry.get("incarnation"), entry.get("boot")
            if not isinstance(incarnation, str) or not incarnation or \
                    not isinstance(boot, str) or not boot:
                raise ValueError("COMPOSITION_IDENTITY_INVALID")
            staged[role] = {"generation": value, "incarnation": incarnation, "boot": boot,
                            "ticket": entry.get("ticket")}
        with self._lock:                       # single commit: no partial identity state
            if self._revoked_reason is not None:
                raise AuthorityRefused(f"AUTHORITY_REVOKED:{self._revoked_reason}")
            if self._expected_roles and set(staged) != set(self._expected_roles):
                # the role set is frozen at install; a caller cannot widen or narrow it
                raise ValueError(
                    f"COMPOSITION_ROLE_SET_MISMATCH:{sorted(staged)}:{sorted(self._expected_roles)}")
            if any(existing["generation"] != generation for existing in self._identities.values()):
                raise ValueError("COMPOSITION_GENERATION_DRIFT")
            self._identities.update(staged)
            self._live_generation = generation
            return dict(self._identities)

    def confirmed_identity(self, role):
        with self._lock:
            entry = self._identities.get(role)
            if entry is None:
                raise ValueError(f"COMPOSITION_IDENTITY_UNCONFIRMED:{role}")
            return (entry["generation"], entry["incarnation"], entry["boot"])

    def register_ticket(self, ticket, *, session_id, attempt_id, role, owner="act",
                        ticket_guard=None, allowed_roles=None):
        """Bind a live ticket after the broker-owned guard proves it is live.

        The guard is a broker-owned dependency (``Ownership.require_ticket`` style);
        a tuple that merely hashes into the map is not a live ticket. The ticket's
        own fields are compared against the registered identity domain.
        """

        if not callable(ticket_guard):
            raise ValueError("COMPOSITION_TICKET_GUARD_REQUIRED")
        if not isinstance(role, str) or not role:
            raise ValueError("COMPOSITION_TICKET_INVALID")
        guard = getattr(ticket_guard, "require_ticket", ticket_guard)
        try:
            guard(ticket)                      # raises for an unknown/foreign ticket
        except Exception as error:  # noqa: BLE001 - a failed guard is a refusal
            raise ValueError(f"COMPOSITION_TICKET_NOT_LIVE:{error}") from error
        with self._lock:
            domain = self._domains.get((session_id, attempt_id))
            if domain is None or domain["owner"] != owner:
                raise ValueError("COMPOSITION_TICKET_DOMAIN_UNKNOWN")
            if ticket in self._tickets:
                raise ValueError("COMPOSITION_TICKET_REUSED")
            # strict positional form: (generation, lease token, owner, session, attempt);
            # membership comparison is forbidden because a swapped or same-valued
            # field must not be able to authorize a foreign ticket
            if not isinstance(ticket, tuple) or len(ticket) != 5:
                raise ValueError("COMPOSITION_TICKET_SHAPE_INVALID")
            if (ticket[0] != domain["generation"] or ticket[2] != domain["owner"]
                    or ticket[3] != domain["session_id"] or ticket[4] != domain["attempt_id"]):
                raise ValueError("COMPOSITION_TICKET_DOMAIN_MISMATCH")
            roles = tuple(allowed_roles) if allowed_roles else (role,)
            if role not in roles:
                raise ValueError("COMPOSITION_TICKET_ROLE_NOT_ALLOWED")
            self._tickets[ticket] = {"role": role, "domain": domain,
                                     "allowed_roles": roles}

    # --- 3. physical sample -> admitted evidence ---------------------------
    def adopt_sample(self, *, ticket, sample):
        """Admit a physical sample through the owned dependencies only.

        Returns an immutable admitted-evidence reference. The caller supplies no
        identity, history version, epoch, controller snapshot, instant or deadline.
        """

        with self._lock:
            live = self._tickets.get(ticket)
            if live is None:
                raise ValueError("COMPOSITION_TICKET_UNKNOWN")
            if self._revoked_reason is not None:
                raise AuthorityRefused(f"AUTHORITY_REVOKED:{self._revoked_reason}")
            domain = live["domain"]
        admitted = self.admission.admit_sample(
            sample=sample, ticket=domain["session_id"], generation=domain["generation"],
            reset_epoch=domain["reset_epoch"])
        # keep one immutable snapshot of the *actual* admitted result: later
        # claims are built from this, never from current history scalars
        from types import MappingProxyType

        snapshot = MappingProxyType(dict(admitted))
        receipt = snapshot.get("commit_receipt")
        receipt = dict(receipt) if receipt is not None else {}
        identity = snapshot.get("identity")
        reference = AdmittedEvidence(
            reference=f"ev-{hashlib.sha256(repr((domain['attempt_id'], receipt.get('step'))).encode()).hexdigest()[:16]}",
            ticket=ticket, role=live["role"],
            # the admitted result carries the selected step and its receipt inside
            # commit_receipt; the reset epoch is the identity's own field
            step=receipt.get("step"),
            history_version=snapshot.get("history_version"),
            incarnation=receipt.get("incarnation") or (identity[2] if identity else None),
            reset_epoch=(identity[4] if isinstance(identity, tuple) and len(identity) == 5
                         else None),
            identity=identity,
            receipt_ns=receipt.get("commit_monotonic_ns"),
            fingerprint=hashlib.sha256(repr(snapshot.get("sample")).encode("utf-8")).hexdigest()[:32],
            allowed_roles=frozenset(live.get("allowed_roles") or (live["role"],)))
        with self._lock:                       # re-validate, then store under the same key
            if self._revoked_reason is not None:
                raise AuthorityRefused(f"AUTHORITY_REVOKED:{self._revoked_reason}")
            live_now = self._tickets.get(ticket)
            if live_now is None or live_now["domain"] is not domain:
                raise ValueError("COMPOSITION_TICKET_CHANGED_DURING_ADMISSION")
            if self._evidence.get(ticket) is not None:
                raise ValueError("COMPOSITION_EVIDENCE_ALREADY_STORED")
            self._evidence[ticket] = reference
        return reference

    # --- 4. prepared goal -> claimed handle --------------------------------
    def claim_prepared_goal(self, *, ticket, role, goal_uuid, goal):
        """Consume the stored evidence once and claim a handle for this dispatch."""

        key = DispatchKey(ticket, role, goal_uuid)
        handle = None
        with self._lock:
            if self._revoked_reason is not None:
                raise AuthorityRefused(f"AUTHORITY_REVOKED:{self._revoked_reason}")
            reference = self._evidence.get(ticket)          # kept for every allowed role
            if reference is None:
                raise ValueError("COMPOSITION_EVIDENCE_MISSING")
            if role not in reference.allowed_roles:
                raise ValueError("COMPOSITION_ROLE_NOT_ALLOWED")
            if key in self._used_keys or key in self._pending_keys:
                raise ValueError("COMPOSITION_DISPATCH_KEY_REUSED")
            if role in self._used_roles.get(ticket, ()) or role in self._pending_roles.get(ticket, ()):
                raise ValueError("COMPOSITION_ROLE_ALREADY_CLAIMED")
            if self._tickets.get(ticket) is None:
                raise ValueError("COMPOSITION_TICKET_UNKNOWN")
            # in-lock placeholder: two concurrent identical claims cannot both issue
            self._pending_keys.add(key)
            self._pending_roles.setdefault(ticket, set()).add(role)
        try:
            digest = hashlib.sha256(serialize_message(goal)).hexdigest()  # canonical ROS bytes
            snapshot_identity = self.controller_port.identity_snapshot(role)  # no locks held
            handle = self.registry.issue_handle(
                identity=reference.identity, stage="route_dispatch", step=reference.step,
                history_version=reference.history_version, incarnation=reference.incarnation,
                epoch=reference.reset_epoch, role=role,
                controller_generation=snapshot_identity[0], goal_uuid=goal_uuid,
                target_digest=digest, controller_incarnation=snapshot_identity[1])
            self.registry.capture_controller_identity(handle)
            token = {"identity": reference.identity, "owner_identity": reference.identity,
                     "stage": "route_dispatch", "history_version": reference.history_version,
                     "incarnation": reference.incarnation,
                     "reset_epoch": reference.reset_epoch, "physics_step": reference.step}
            self.registry.claim_bound(handle, identity=reference.identity,
                                      controller_generation=snapshot_identity[0], token=token)
        except Exception as error:  # noqa: BLE001 - the composition owns closure
            with self._lock:
                self._pending_keys.discard(key)
                self._pending_roles.get(ticket, set()).discard(role)
            if handle is not None:
                self._terminalize(handle, f"COMPOSITION_CLAIM_FAILED:{error}")
            raise
        with self._lock:
            if self._revoked_reason is not None:              # concurrent revoke wins
                self._terminalize(handle, self._revoked_reason)
                raise AuthorityRefused(f"AUTHORITY_REVOKED:{self._revoked_reason}")
            self._pending_keys.discard(key)
            self._pending_roles.get(ticket, set()).discard(role)
            self._handles[key] = handle
            self._used_keys.add(key)
            self._used_roles.setdefault(ticket, set()).add(role)
        return handle

    def handle_for(self, *, ticket, role, goal_uuid):
        with self._lock:
            return self._handles.get(DispatchKey(ticket, role, goal_uuid))

    def _terminalize(self, handle, reason) -> None:
        """One irreversible terminalization for a permit the composition drops."""

        terminate = getattr(self.registry, "terminate", None)
        if callable(terminate):
            try:
                terminate(handle, reason=reason)
            except Exception:  # noqa: BLE001 - already terminal is acceptable
                pass

    # --- resolver interface (reservation client) ---------------------------
    def reservation_binding(self, handle):
        with self._lock:
            if self._revoked_reason is not None:
                raise AuthorityRefused(f"AUTHORITY_REVOKED:{self._revoked_reason}")
            associated = any(stored is handle for stored in self._handles.values())
        if not associated:
            raise AuthorityRefused("COMPOSITION_HANDLE_NOT_ASSOCIATED")
        return self.registry.reservation_binding(handle)

    # --- fail-closed revocation -------------------------------------------
    def revoke(self, reason: str) -> None:
        """Latch, terminate every permit, revoke registry/admission, then close.

        Order matters: the irreversible logical termination (handles, registry,
        admission) runs first and is never skipped by a controller-side failure. The
        controller close runs last; a failure there is recorded as
        ``CLOSE_FAILED``/``FENCING_REQUIRED`` and aggregated, never masking the
        terminalization that already happened.
        """

        with self._lock:
            if self._revoked_reason is not None and self._live_generation is None \
                    and not self._handles:
                return                      # already terminal: no second close/revoke
            if self._revoked_reason is None:
                self._revoked_reason = reason
            handles = list(self._handles.values())
            live_generation = self._live_generation
            self._identities.clear()               # no cached live identity survives
            self._live_generation = None
            self._evidence.clear()
            self._handles.clear()
            self._used_keys.clear()
            self._used_roles.clear()
            self._pending_keys.clear()
            self._pending_roles.clear()
            admission, port, registry = self.admission, self.controller_port, self.registry
        for handle in handles:
            self._terminalize(handle, reason)       # no orphan IN_FLIGHT permits
        failures = []
        revoke_registry = getattr(registry, "revoke", None)
        if callable(revoke_registry):
            try:
                revoke_registry(reason)
            except Exception as failure:            # recorded, but terminalization goes on
                failures.append(f"REGISTRY_REVOKE_FAILED:{failure}")
        revoke_admission = getattr(admission, "revoke_current", None)
        if callable(revoke_admission):
            try:
                revoke_admission(reason)
            except Exception as failure:
                failures.append(f"ADMISSION_REVOKE_FAILED:{failure}")
        # exactly one close call: the precise live generation when there is one,
        # otherwise the port closes its whole attempted range itself
        closer = getattr(port, "close", None)
        if callable(closer):
            try:
                closer(reason, generation=live_generation)
            except Exception as failure:
                # the authority is already logically terminated; a failed
                # controller close only requires fencing, it does not undo it
                failures.append(f"CLOSE_FAILED:{live_generation}:{failure}")
                with self._lock:
                    self._fencing_required = True
        if failures:
            with self._lock:
                self._revocation_failures = tuple(failures)
            raise AuthorityRefused("COMPOSITION_REVOKE_INCOMPLETE:" + "|".join(failures))

    def fencing_required(self) -> bool:
        with self._lock:
            return bool(getattr(self, "_fencing_required", False))

    def revocation_failures(self) -> tuple:
        with self._lock:
            return tuple(getattr(self, "_revocation_failures", ()))
