"""Consume one owner-created pick-place validation stack proof before a reset side effect.

The receipt producer is deliberately absent until real bounded stack probes exist.
This verifier alone does not authorize a live pick-place validation case or FULL_RESTART.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from .bridge import _retirement_owner_state
from .contracts import MutationError, OwnerKey


_CHECKS = frozenset((
    "mujoco_session", "advancing_physics", "controller_states",
    "moveit_graph", "physical_stop", "head_rgb", "wrist_rgb",
))
_BASE_CHECKS = frozenset(("mujoco_session", "advancing_physics", "controller_states",
                          "moveit_graph", "physical_stop"))


def checks_for_camera_names(camera_names) -> frozenset:
    """The exact check set of a stack whose rig has these cameras: the five stack checks and one `<camera>_rgb` each.

    The names are the observer's (`so101_demo.cli.act_stack_ready.check_order_for`); a test pins the two together."""
    return _BASE_CHECKS | frozenset(f"{camera}_rgb" for camera in camera_names)


def checks_for_rig(rig: str, rig_profile) -> frozenset:
    """The exact check set of the rig a stack composes, from the rig name and its profile file.

    The default rig (`head-wrist`, no profile file) is the fixed `_CHECKS` of the stacks that predate rigs; any other rig is
    derived from the profile file the observer is given. A profile whose rig is not `rig` is refused. Raises `ValueError`."""
    if rig == "head-wrist":
        if rig_profile is not None:
            raise ValueError("ACT_STACK_RIG_INVALID")
        return _CHECKS
    if rig_profile is None:
        raise ValueError("ACT_STACK_RIG_INVALID")
    from so101_demo.act.rig_profile import load_rig_profile

    profile = load_rig_profile(rig_profile)
    if profile.rig != rig:
        raise ValueError("ACT_STACK_RIG_INVALID")
    return checks_for_camera_names(profile.camera_names)


_ARTIFACT_HASHES = (
    "source_sha256", "manifest_sha256", "runtime_config_sha256",
    "collection_config_sha256", "contact_policy_fingerprint",
)
_RECEIPT_KEYS = frozenset((
    "schema_version", "campaign_id", "operation_id", "worker_id",
    "execution_generation", "session_id", "ros_domain_id", *_ARTIFACT_HASHES,
    "stack_owner", "child_owner", "readiness_sha256", "issued_monotonic_ns",
))
_READINESS_KEYS = frozenset((
    "schema_version", "session_id", "ros_domain_id", "captured_monotonic_ns", "checks",
))
_MAX_BYTES = 1 << 20
_MAX_AGE_NS = 30_000_000_000
_MAX_ISSUE_LAG_NS = 10_000_000_000


def _read_regular_json(path: Path) -> tuple[dict, bytes]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.getuid():
            raise ValueError("startup proof file type or owner")
        raw = stream.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("startup proof file too large")
    value = json.loads(raw)
    if type(value) is not dict:
        raise ValueError("startup proof document type")
    return value, raw


def _owner_matches(observed, expected: OwnerKey) -> bool:
    fields = asdict(expected)
    return (type(observed) is dict and set(observed) == set(fields)
            and all(observed[key] == value and type(observed[key]) is type(value)
                    for key, value in fields.items()))


class PickPlaceStartupProofConsumer:
    """Validate a fresh receipt from the fixed admitted path exactly once."""

    def __init__(self, context, child, *, stack_owner: OwnerKey,
                 child_owner: OwnerKey, checks: frozenset, live_probe=None,
                 clock_ns=time.monotonic_ns) -> None:
        # `checks` is the exact set of the rig the stack composes, passed explicitly: there is no default, so a consumer
        # can never silently expect the check set of a rig other than the stack's.
        if (not isinstance(stack_owner, OwnerKey) or not isinstance(child_owner, OwnerKey)
                or not isinstance(checks, frozenset) or not checks
                or not all(isinstance(name, str) for name in checks)
                or not callable(clock_ns) or live_probe is not None and not callable(live_probe)):
            raise ValueError("PICK_PLACE_VALIDATION_STARTUP_CONSUMER_CONFIG_INVALID")
        self.context, self.child = context, child
        self.stack_owner, self.child_owner = stack_owner, child_owner
        self.checks = checks
        self.live_probe = live_probe or (lambda owner: _retirement_owner_state(owner) == "live")
        self.clock_ns = clock_ns

    def _root(self) -> Path:
        try:
            campaign_id = self.context.campaign_id
            campaign_root = Path(self.context.evidence_root)
            if (not isinstance(campaign_id, str)
                    or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", campaign_id) is None
                    or not campaign_root.is_absolute() or ".." in campaign_root.parts
                    or self.child.campaign_id != campaign_id):
                raise ValueError("scope")
            root = campaign_root / "pick-place-live" / campaign_id / "stack"
            if (not root.is_dir()
                    or any(part.is_symlink() for part in (
                        campaign_root, root.parent.parent, root.parent, root,
                    ))):
                raise ValueError("path")
            return root
        except (AttributeError, OSError, TypeError, ValueError) as error:
            raise MutationError("PICK_PLACE_VALIDATION_STARTUP_SCOPE_INVALID") from error

    def _claim(self, root: Path, now_ns: int) -> None:
        marker = root / "startup-consumed.json"
        try:
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600)
        except FileExistsError as error:
            raise MutationError("PICK_PLACE_VALIDATION_STARTUP_PROOF_ALREADY_CONSUMED") from error
        except OSError as error:
            raise MutationError("PICK_PLACE_VALIDATION_STARTUP_PROOF_INVALID") from error
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(json.dumps({"schema_version": 1,
                                         "attempted_monotonic_ns": now_ns}).encode())
                stream.flush()
                os.fsync(stream.fileno())
            dir_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError as error:
            raise MutationError("PICK_PLACE_VALIDATION_STARTUP_PROOF_INVALID") from error

    def consume(self) -> dict:
        """Burn the capability before validation; failure cannot be retried."""
        root = self._root()
        receipt_path = root / "startup-receipt.json"
        if not receipt_path.exists() and not receipt_path.is_symlink():
            raise MutationError("PICK_PLACE_VALIDATION_STARTUP_PROOF_UNAVAILABLE")
        now_ns = self.clock_ns()
        if type(now_ns) is not int or now_ns <= 0:
            raise MutationError("PICK_PLACE_VALIDATION_STARTUP_PROOF_INVALID")
        self._claim(root, now_ns)
        try:
            receipt, _ = _read_regular_json(receipt_path)
            readiness, raw = _read_regular_json(root / "readiness.json")
            expected = {
                "schema_version": 1,
                "campaign_id": self.context.campaign_id,
                "operation_id": self.context.operation_id,
                "worker_id": self.child.worker_id,
                "execution_generation": self.child.execution_generation,
                "session_id": self.child.mujoco_session_id,
                "ros_domain_id": self.child.ros_domain_id,
                "stack_owner": asdict(self.stack_owner),
                "child_owner": asdict(self.child_owner),
                **{key: getattr(self.context, key) for key in _ARTIFACT_HASHES},
            }
            if (set(receipt) != _RECEIPT_KEYS
                    or any(receipt.get(key) != value or type(receipt.get(key)) is not type(value)
                           for key, value in expected.items())
                    or not _owner_matches(receipt.get("stack_owner"), self.stack_owner)
                    or not _owner_matches(receipt.get("child_owner"), self.child_owner)
                    or not isinstance(receipt.get("readiness_sha256"), str)
                    or hashlib.sha256(raw).hexdigest() != receipt["readiness_sha256"]
                    or set(readiness) != _READINESS_KEYS
                    or readiness.get("schema_version") != 1
                    or type(readiness.get("schema_version")) is not int
                    or readiness.get("session_id") != self.child.mujoco_session_id
                    or readiness.get("ros_domain_id") != self.child.ros_domain_id
                    or type(readiness.get("ros_domain_id")) is not int
                    or type(readiness.get("checks")) is not dict
                    or set(readiness["checks"]) != self.checks
                    or any(value is not True for value in readiness["checks"].values())):
                raise ValueError("identity, hash or readiness mismatch")
            captured = readiness["captured_monotonic_ns"]
            issued = receipt["issued_monotonic_ns"]
            if (type(captured) is not int or type(issued) is not int
                    or not 0 < captured <= issued <= now_ns
                    or now_ns - captured > _MAX_AGE_NS
                    or issued - captured > _MAX_ISSUE_LAG_NS
                    or self.live_probe(self.stack_owner) is not True
                    or self.live_probe(self.child_owner) is not True):
                raise ValueError("stale or retired owner")
            return receipt
        except (AttributeError, KeyError, OSError, TypeError, ValueError,
                UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MutationError("PICK_PLACE_VALIDATION_STARTUP_PROOF_INVALID") from error
