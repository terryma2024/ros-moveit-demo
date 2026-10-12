"""Single-flight shard retirement with independently readable original evidence."""

import asyncio
import copy
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import re

from so101_demo.runtime.container_campaign.controller_stop import ControllerStopObservation, observe_act_controller_stop
from so101_demo.runtime.container_campaign.paths import _path
from so101_demo.runtime.container_campaign.process_identity import ProcessOwnerKey, pid_namespace_inode, process_owner_matches
from so101_demo.runtime.inference.config import _open_regular
from so101_demo.runtime.parallel_ipc.frames import _pairs, canonical_json


def _require(value):
    if not value:
        raise ValueError("SHARD_STOP_EVIDENCE_INVALID")


def _json(raw):
    return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_pairs,
        parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("nonfinite")))


def _read(path):
    with _open_regular(path) as stream:
        raw = stream.read(1024*1024+1)
    _require(len(raw) <= 1024*1024)
    return raw


def _write(root, name, raw):
    fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _native(raw, *, owner, session_id, ros_domain_id, after_ns):
    value = _json(raw)
    fields = {"schema_version", "leader_pid", "pgid", "started_ticks", "argv_sha256", "session_id",
              "ros_domain_id", "group_clear", "graph_clear", "physical_stop_confirmed", "parent_exited",
              "term_sent", "kill_sent", "finished_at_monotonic_ns"}
    _require(type(value) is dict and set(value) == fields)
    expected = dict(schema_version=1, leader_pid=owner.pid, pgid=owner.pgid,
        started_ticks=owner.started_ticks, argv_sha256=owner.argv_sha256,
        session_id=session_id, ros_domain_id=ros_domain_id)
    _require(all(value[name] == item and type(value[name]) is type(item) for name,item in expected.items()))
    _require(all(type(value[name]) is bool for name in (
        "group_clear", "graph_clear", "physical_stop_confirmed", "parent_exited", "term_sent", "kill_sent")))
    _require(type(value["finished_at_monotonic_ns"]) is int and value["finished_at_monotonic_ns"] >= after_ns)
    _require(all(value[name] is True for name in ("group_clear", "graph_clear", "physical_stop_confirmed")))
    return value


class NativeShardRetirement:
    def __init__(self, *, process_owner, launch_generation, evidence_root, stack, ros_namespace,
                 goal_stop_budget_s, stack_stop_budget_s, goal_stop_probe=observe_act_controller_stop):
        from so101_teleop.unified.act_stack import ActStackProcessOwner

        if (type(process_owner) is not ProcessOwnerKey or process_owner.pid != os.getpid()
                or type(launch_generation) is not int or launch_generation <= 0
                or not isinstance(stack, ActStackProcessOwner) or not callable(goal_stop_probe)
                or type(ros_namespace) is not str
                or re.fullmatch(r"(?:/[a-zA-Z_][a-zA-Z0-9_]*)+", ros_namespace) is None
                or any(type(value) not in (int,float) or not math.isfinite(value) or value <= 0
                       for value in (goal_stop_budget_s, stack_stop_budget_s))
                or stack_stop_budget_s > 30):
            raise ValueError("SHARD_RETIREMENT_CONFIG_INVALID")
        self.root = _path(evidence_root, directory=True)
        if (stack.launch.evidence_root != self.root / "stack"
                or self.root.stat().st_uid != os.getuid()):
            raise ValueError("SHARD_RETIREMENT_CONFIG_INVALID")
        self.owner, self.generation, self.stack = process_owner, launch_generation, stack
        self.namespace = ros_namespace
        self.goal_budget, self.stack_budget, self.goal_probe = goal_stop_budget_s, stack_stop_budget_s, goal_stop_probe
        self.namespace_inode = pid_namespace_inode()
        self._task = None

    async def retire(self, *, fenced):
        if fenced is not True:
            raise ValueError("SHARD_RETIREMENT_NOT_FENCED")
        if self._task is None:
            self._task = asyncio.create_task(self._retire())
        return copy.deepcopy(await asyncio.shield(self._task))

    async def _retire(self):
        if not process_owner_matches(self.owner) or pid_namespace_inode() != self.namespace_inode:
            raise ValueError("SHARD_RETIREMENT_PROCESS_CHANGED")
        audit_root = self.root / "retirement"
        audit_root.mkdir(mode=0o700)
        native_owner = self.stack.owner
        goal_observation, native_observation = None, None
        goal_ref = native_ref = None
        errors = []
        try:
            goal_observation = await asyncio.wait_for(asyncio.to_thread(self.goal_probe,
                ros_namespace=self.namespace, timeout_s=self.goal_budget), timeout=self.goal_budget)
            if type(goal_observation) is not ControllerStopObservation:
                raise ValueError("ACT_CONTROLLER_STOP_OBSERVATION_REQUIRED")
            if goal_observation.document["ros_namespace"] != self.namespace:
                raise ValueError("ACT_CONTROLLER_STOP_NAMESPACE_CHANGED")
            _write(audit_root, "controller-stop.json", goal_observation.payload)
            goal_ref = hashlib.sha256(goal_observation.payload).hexdigest()
        except Exception as error:
            errors.append(dict(boundary="goal_stop", error_type=type(error).__name__, reason=str(error)))
            goal_observation = None
        try:
            if native_owner is None or self.stack.process is None:
                raise ValueError("SHARD_NATIVE_STACK_NOT_OWNED")
            await self.stack.stop(timeout_s=self.stack_budget)
            raw = _read(self.root / "stack/cleanup-receipt.json")
            native_observation = _native(raw, owner=native_owner, session_id=self.stack.launch.session_id,
                ros_domain_id=self.stack.launch.ros_domain_id,
                after_ns=goal_observation.document["completed_monotonic_ns"] if goal_observation else 1)
            _write(audit_root, "stack-stop.json", raw)
            native_ref = hashlib.sha256(raw).hexdigest()
        except Exception as error:
            errors.append(dict(boundary="native_stop", error_type=type(error).__name__, reason=str(error)))
            native_observation = None
        if not process_owner_matches(self.owner) or pid_namespace_inode() != self.namespace_inode:
            raise ValueError("SHARD_RETIREMENT_PROCESS_CHANGED")
        receipt = dict(schema_version=1, kind="shard_stop_receipt", generation=self.generation,
            process_owner=asdict(self.owner), pid_namespace_inode=self.namespace_inode,
            goals_stopped=goal_observation is not None and goal_observation.proven,
            controllers_stopped=native_observation is not None,
            ros_children_exited=native_observation is not None, ros_graph_empty=native_observation is not None,
            forced=native_observation is not None and native_observation["kill_sent"])
        _write(audit_root, "audit.json", canonical_json(dict(schema_version=1, kind="ACT_SHARD_STOP_AUDIT",
            generation=self.generation, process_owner=asdict(self.owner), pid_namespace_inode=self.namespace_inode,
            ros_namespace=self.namespace, session_id=self.stack.launch.session_id,
            ros_domain_id=self.stack.launch.ros_domain_id,
            native_owner=None if native_owner is None else asdict(native_owner),
            controller_stop_sha256=goal_ref, native_stop_sha256=native_ref, errors=errors)))
        _write(self.root, "shard-stop.json", canonical_json(receipt))
        return receipt


def read_shard_stop_evidence(root, *, process_owner, launch_generation, ros_namespace, session_id, ros_domain_id,
                             namespace_inode):
    from so101_teleop.unified.contracts import OwnerKey

    try:
        _require(type(process_owner) is ProcessOwnerKey and type(launch_generation) is int and launch_generation > 0
                 and type(namespace_inode) is int and namespace_inode > 0
                 and type(ros_domain_id) is int and 0 <= ros_domain_id <= 232
                 and type(session_id) is str and bool(session_id)
                 and type(ros_namespace) is str
                 and re.fullmatch(r"(?:/[a-zA-Z_][a-zA-Z0-9_]*)+", ros_namespace) is not None)
        root = _path(root, directory=True)
        receipt = _json(_read(root / "shard-stop.json"))
        audit = _json(_read(root / "retirement/audit.json"))
        expected = dict(generation=launch_generation, process_owner=asdict(process_owner), pid_namespace_inode=namespace_inode)
        _require(type(receipt) is dict and set(receipt) == {"schema_version", "kind", *expected,
            "goals_stopped", "controllers_stopped", "ros_children_exited", "ros_graph_empty", "forced"})
        _require(type(receipt["schema_version"]) is int and receipt["schema_version"] == 1
                 and receipt["kind"] == "shard_stop_receipt")
        _require(type(audit) is dict and set(audit) == {"schema_version", "kind", *expected, "ros_namespace", "session_id",
            "ros_domain_id", "native_owner", "controller_stop_sha256", "native_stop_sha256", "errors"})
        _require(type(audit["schema_version"]) is int and audit["schema_version"] == 1 and audit["kind"] == "ACT_SHARD_STOP_AUDIT")
        _require(type(audit["errors"]) is list)
        for error in audit["errors"]:
            _require(type(error) is dict and set(error) == {"boundary", "error_type", "reason"}
                     and error["boundary"] in {"goal_stop", "native_stop"}
                     and type(error["error_type"]) is str and bool(error["error_type"])
                     and type(error["reason"]) is str)
        for document in (receipt,audit):
            _require(type(document["generation"]) is int and type(document["pid_namespace_inode"]) is int
                     and ProcessOwnerKey(**document["process_owner"]) == process_owner)
            _require(all(document[name] == value for name,value in expected.items()))
        _require(audit["ros_namespace"] == ros_namespace and audit["session_id"] == session_id
                 and type(audit["ros_domain_id"]) is int and audit["ros_domain_id"] == ros_domain_id)
        goal, native = None, None
        if audit["controller_stop_sha256"] is not None:
            raw = _read(root / "retirement/controller-stop.json")
            _require(hashlib.sha256(raw).hexdigest() == audit["controller_stop_sha256"])
            goal = ControllerStopObservation(raw)
            _require(goal.document["ros_namespace"] == ros_namespace)
        if audit["native_stop_sha256"] is not None:
            raw = _read(root / "retirement/stack-stop.json")
            _require(hashlib.sha256(raw).hexdigest() == audit["native_stop_sha256"])
            owner = ProcessOwnerKey(**audit["native_owner"])
            native = _native(raw, owner=OwnerKey(**asdict(owner)), session_id=session_id,
                ros_domain_id=ros_domain_id, after_ns=goal.document["completed_monotonic_ns"] if goal else 1)
        facts = dict(goals_stopped=goal is not None and goal.proven, controllers_stopped=native is not None,
            ros_children_exited=native is not None, ros_graph_empty=native is not None,
            forced=native is not None and native["kill_sent"])
        _require(all(type(receipt[name]) is bool and receipt[name] == value for name,value in facts.items()))
        _require(not audit["errors"] or not all(facts[name] for name in (
            "goals_stopped", "controllers_stopped", "ros_children_exited", "ros_graph_empty")))
        if not all(facts[name] for name in ("goals_stopped", "controllers_stopped", "ros_children_exited", "ros_graph_empty")) or facts["forced"]:
            raise ValueError("SHARD_STOP_EVIDENCE_UNCONFIRMED")
        return receipt
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as error:
        if str(error) == "SHARD_STOP_EVIDENCE_UNCONFIRMED":
            raise
        raise ValueError("SHARD_STOP_EVIDENCE_INVALID") from error
