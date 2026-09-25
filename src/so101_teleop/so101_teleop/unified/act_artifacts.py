"""Closed artifact paths passed from ACT admission to its isolated ROS child."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Mapping


_HASHED = ("source", "manifest", "runtime_config", "collection_config", "calibration_report")
_POLICY = ("proposal", "activation_receipt")
_PATHS = _HASHED + _POLICY
_ENV_PREFIX = "SO101_ACT_ARTIFACT_"
_SHA_PATTERN = re.compile(r"[0-9a-f]{64}")


def _regular_digest(path: Path) -> str:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("ACT_ARTIFACT_NOT_REGULAR")
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as error:
        raise ValueError("ACT_ARTIFACT_UNAVAILABLE") from error


def _regular_json(path: Path) -> dict:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("ACT_ARTIFACT_NOT_REGULAR")
            raw = stream.read((1 << 20) + 1)
        if len(raw) > (1 << 20):
            raise ValueError("ACT_ARTIFACT_TOO_LARGE")
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise ValueError("ACT_ARTIFACT_INVALID")
        return document
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("ACT_ARTIFACT_UNAVAILABLE") from error


@dataclass(frozen=True, slots=True)
class ActArtifactBinding:
    evidence_root: Path
    paths: tuple[tuple[str, Path], ...]
    hashes: tuple[tuple[str, str], ...]
    policy_fingerprint: str

    @classmethod
    def from_admission(cls, payload: Mapping[str, object], context) -> "ActArtifactBinding":
        """Bind only the source identities already accepted by one admission."""
        if not isinstance(payload, Mapping):
            raise ValueError("ACT_ARTIFACT_BINDING_INVALID")
        try:
            if (payload["evidence_root"] != context.evidence_root
                    or payload["contact_policy_fingerprint"] != context.contact_policy_fingerprint
                    or any(payload[f"{name}_sha256"] != getattr(context, f"{name}_sha256")
                           for name in _HASHED if name != "calibration_report")):
                raise ValueError("ACT_ARTIFACT_BINDING_INVALID")
            root = Path(payload["evidence_root"])
            paths = tuple((name, Path(payload[f"{name}_path"])) for name in _PATHS)
            hashes = tuple((name, payload[f"{name}_sha256"]) for name in _HASHED)
            fingerprint = payload["contact_policy_fingerprint"]
        except (AttributeError, KeyError, TypeError) as error:
            raise ValueError("ACT_ARTIFACT_BINDING_INVALID") from error
        binding = cls(root, paths, hashes, fingerprint)
        binding.verify()
        return binding

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "ActArtifactBinding":
        try:
            root = Path(environment[_ENV_PREFIX + "EVIDENCE_ROOT"])
            paths = tuple((name, Path(environment[_ENV_PREFIX + name.upper() + "_PATH"]))
                          for name in _PATHS)
            hashes = tuple((name, environment[_ENV_PREFIX + name.upper() + "_SHA256"])
                           for name in _HASHED)
            fingerprint = environment[_ENV_PREFIX + "POLICY_FINGERPRINT"]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("ACT_ARTIFACT_BINDING_INVALID") from error
        return cls(root, paths, hashes, fingerprint)

    @classmethod
    def verify_environment(cls, environment: Mapping[str, str]) -> "ActArtifactBinding":
        binding = cls.from_environment(environment)
        binding.verify()
        return binding

    def environment(self) -> dict[str, str]:
        result = {_ENV_PREFIX + "EVIDENCE_ROOT": str(self.evidence_root),
                  _ENV_PREFIX + "POLICY_FINGERPRINT": self.policy_fingerprint}
        result.update({_ENV_PREFIX + name.upper() + "_PATH": str(path)
                       for name, path in self.paths})
        result.update({_ENV_PREFIX + name.upper() + "_SHA256": digest
                       for name, digest in self.hashes})
        return result

    def read_hashed_json(self, name: str) -> dict:
        """Read one admitted JSON artifact through a single no-follow open."""
        if name not in _HASHED:
            raise ValueError("ACT_ARTIFACT_BINDING_INVALID")
        paths, hashes = dict(self.paths), dict(self.hashes)
        if name not in paths or name not in hashes:
            raise ValueError("ACT_ARTIFACT_BINDING_INVALID")
        path = paths[name]
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("ACT_ARTIFACT_BINDING_INVALID")
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("ACT_ARTIFACT_NOT_REGULAR")
                raw = stream.read((1 << 20) + 1)
        except OSError as error:
            raise ValueError("ACT_ARTIFACT_UNAVAILABLE") from error
        if len(raw) > (1 << 20):
            raise ValueError("ACT_ARTIFACT_TOO_LARGE")
        if hashlib.sha256(raw).hexdigest() != hashes[name]:
            raise ValueError("ACT_ARTIFACT_HASH_MISMATCH")
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("ACT_ARTIFACT_INVALID") from error
        if not isinstance(value, dict):
            raise ValueError("ACT_ARTIFACT_INVALID")
        return value

    def verify(self) -> None:
        if (not self.evidence_root.is_absolute() or ".." in self.evidence_root.parts
                or not self.evidence_root.is_dir()
                or tuple(name for name, _ in self.paths) != _PATHS
                or tuple(name for name, _ in self.hashes) != _HASHED
                or not isinstance(self.policy_fingerprint, str)
                or _SHA_PATTERN.fullmatch(self.policy_fingerprint) is None):
            raise ValueError("ACT_ARTIFACT_BINDING_INVALID")
        paths = dict(self.paths)
        hashes = dict(self.hashes)
        for name, path in self.paths:
            if not path.is_absolute() or ".." in path.parts:
                raise ValueError("ACT_ARTIFACT_BINDING_INVALID")
            if name in (*_POLICY, "calibration_report") and not path.is_relative_to(self.evidence_root):
                raise ValueError("ACT_ARTIFACT_BINDING_INVALID")
        for name, digest in self.hashes:
            if not isinstance(digest, str) or _SHA_PATTERN.fullmatch(digest) is None:
                raise ValueError("ACT_ARTIFACT_BINDING_INVALID")
            if _regular_digest(paths[name]) != digest:
                raise ValueError("ACT_ARTIFACT_HASH_MISMATCH")
        from so101_demo.act.contact_calibration import verify_disabled_proposal
        from so101_demo.act.contact_policy import verify_activation

        proposal = _regular_json(paths["proposal"])
        receipt = _regular_json(paths["activation_receipt"])
        try:
            verify_disabled_proposal(proposal)
            verify_activation(proposal["payload"], receipt)
            if (proposal["policy_fingerprint"] != self.policy_fingerprint
                    or receipt["policy_fingerprint"] != self.policy_fingerprint
                    or receipt["evidence_root"] != str(self.evidence_root)):
                raise ValueError("ACT_POLICY_BINDING_INVALID")
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("ACT_POLICY_BINDING_INVALID") from error
