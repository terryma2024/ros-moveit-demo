"""Burn one owner-issued startup proof inside the child before Task 8 reset."""

from __future__ import annotations

import re
from types import SimpleNamespace

from .contracts import MutationError, OwnerKey
from .task8_startup_proof import Task8StartupProofConsumer


_HASH_ENV = {
    "source_sha256": "SO101_ACT_SOURCE_SHA256",
    "manifest_sha256": "SO101_ACT_MANIFEST_SHA256",
    "runtime_config_sha256": "SO101_ACT_RUNTIME_CONFIG_SHA256",
    "collection_config_sha256": "SO101_ACT_COLLECTION_CONFIG_SHA256",
    "contact_policy_fingerprint": "SO101_ACT_POLICY_FINGERPRINT",
}
_OWNER_FIELDS = frozenset((
    "pid", "pgid", "started_ticks", "argv_sha256", "environment_sha256",
))


def consume_child_task8_startup(request, child_owner: OwnerKey, environment,
                                *, live_probe=None, clock_ns=None) -> dict:
    """Derive all scope from admitted child environment and closed IPC identity."""
    try:
        if not isinstance(child_owner, OwnerKey):
            raise ValueError("child owner")
        stack = request.payload["stack_owner"]
        if (type(stack) is not dict or set(stack) != _OWNER_FIELDS
                or any(type(stack[key]) is not int or stack[key] <= 0
                       for key in ("pid", "pgid", "started_ticks"))
                or stack["pgid"] != stack["pid"]
                or any(type(stack[key]) is not str
                       or re.fullmatch(r"[0-9a-f]{64}", stack[key]) is None
                       for key in ("argv_sha256", "environment_sha256"))):
            raise ValueError("stack owner")
        campaign_id = environment["SO101_ACT_CAMPAIGN_ID"]
        worker_id = environment["SO101_ACT_WORKER_ID"]
        session_id = environment["SO101_SIMULATION_SESSION_ID"]
        operation_id = environment["SO101_ACT_OPERATION_ID"]
        generation = environment["SO101_ACT_GENERATION"]
        domain = environment["ROS_DOMAIN_ID"]
        if (request.operation not in ("task8_phase", "task8_full")
                or any(not isinstance(value, str) or not value for value in (
                    campaign_id, worker_id, session_id, operation_id,
                ))
                or not generation.isdecimal() or str(int(generation)) != generation
                or not domain.isdecimal() or str(int(domain)) != domain
                or request.campaign_id != campaign_id
                or request.worker_id != worker_id
                or request.session_id != session_id
                or request.execution_generation != int(generation)
                or request.token.operation_id != operation_id):
            raise ValueError("child identity")
        hashes = {name: environment[key] for name, key in _HASH_ENV.items()}
        if any(type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
               for value in hashes.values()):
            raise ValueError("admitted hashes")
        context = SimpleNamespace(
            evidence_root=environment["SO101_ACT_EVIDENCE_ROOT"],
            campaign_id=campaign_id, operation_id=operation_id, **hashes,
        )
        child = SimpleNamespace(
            campaign_id=campaign_id, worker_id=worker_id,
            execution_generation=int(generation), mujoco_session_id=session_id,
            ros_domain_id=int(domain),
        )
        owner = OwnerKey(**stack)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise MutationError("TASK8_STARTUP_SCOPE_INVALID") from error
    options = {}
    if live_probe is not None:
        options["live_probe"] = live_probe
    if clock_ns is not None:
        options["clock_ns"] = clock_ns
    return Task8StartupProofConsumer(
        context, child, stack_owner=owner, child_owner=child_owner, **options,
    ).consume()
