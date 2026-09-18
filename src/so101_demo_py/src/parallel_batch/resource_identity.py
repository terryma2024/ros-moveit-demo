"""Acyclic identity for exact-N resource qualification.

This module builds L (normalization rule), S (normalized semantic config), E/I
(execution and installed inventories), R (runtime fingerprint) and the two
full-byte deployment audits A0/A1. It deliberately cannot sign approvals: B, Q,
P, M and D belong to later stages and are never referenced from here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, fields as dataclass_fields
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import ClassVar, Mapping, Sequence

from .contracts import (
    ClockRulesV2,
    ContractError,
    CoverageRulesV2,
    DeploymentReferencesV2,
    ParallelRuntimeConfigV2,
    SamplingRulesV2,
    SafetyRulesV2,
    V2_EXECUTION_SCALAR_FIELDS,
    V2_DEPLOYMENT_REFERENCE_FIELDS,
    parse_parallel_runtime_config_v2,
)

SOURCE_CARRIER_LOGICAL_PATH = "src/so101_demo_py/config/mujoco/parallel_batch_v2.yaml"
INSTALLED_CARRIER_LOGICAL_PATH = (
    "install/so101_demo_py/share/so101_demo_py/config/mujoco/parallel_batch_v2.yaml"
)
CARRIER_LOGICAL_PATH = SOURCE_CARRIER_LOGICAL_PATH

DEPLOYMENT_REFERENCE_LITERAL = "DEPLOYMENT_REFERENCE_V2"
NORMALIZATION_ALGORITHM = "DEPLOYMENT_REFERENCE_SUBSTITUTION_V2"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SELF_REFERENTIAL_FACTS = frozenset(
    {"profile", "profile_sha256", "promotion", "promotion_sha256", "deployment_receipt",
     "deployment_receipt_sha256", "qualification", "qualification_sha256", "authorization"}
)


def canonical_sha256(value: object) -> str:
    """Canonical UTF-8 JSON digest: sorted keys, no NaN, explicit types."""

    _require_json_safe(value)
    try:
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ContractError("CANONICAL_JSON") from error
    return hashlib.sha256(payload).hexdigest()


def _require_json_safe(value: object, path: str = "$") -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"NONFINITE: {path}")
    elif isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError(f"JSON_KEY_TYPE: {path}")
            _require_json_safe(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _require_json_safe(item, f"{path}[{index}]")
    else:
        raise ContractError(f"JSON_TYPE: {path}")


def _require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ContractError(f"SHA256: {name}")
    return value


def _execution_document_fields() -> dict[str, tuple[str, ...]]:
    return {
        "scalars": tuple(sorted(V2_EXECUTION_SCALAR_FIELDS)),
        "sampling": tuple(sorted(item.name for item in dataclass_fields(SamplingRulesV2))),
        "clock": tuple(sorted(item.name for item in dataclass_fields(ClockRulesV2))),
        "safety": tuple(sorted(item.name for item in dataclass_fields(SafetyRulesV2))),
        "coverage": tuple(sorted(item.name for item in dataclass_fields(CoverageRulesV2))),
    }


def normalization_document() -> Mapping[str, object]:
    """L binds the normalization algorithm, exact field lists and inventory rules."""

    return MappingProxyType(
        {
            "schema_version": 2,
            "algorithm": NORMALIZATION_ALGORITHM,
            "deployment_reference_literal": DEPLOYMENT_REFERENCE_LITERAL,
            "deployment_fields": tuple(sorted(V2_DEPLOYMENT_REFERENCE_FIELDS)),
            "execution_fields": _execution_document_fields(),
            "inventory_rules": {
                "semantic_carriers": (
                    INSTALLED_CARRIER_LOGICAL_PATH,
                    SOURCE_CARRIER_LOGICAL_PATH,
                ),
                "non_carrier_digest": "raw_bytes_sha256",
                "excluded_from_inventory": ("evidence_root_raw", "docs", "ledger"),
            },
            "digest": "canonical_utf8_json_sorted_keys_nonfinite_rejected",
        }
    )


def normalization_sha256() -> str:
    return canonical_sha256(dict(normalization_document()))


def _semantic_config_sha256(document: object) -> str:
    parse_parallel_runtime_config_v2(document)
    assert isinstance(document, Mapping)
    normalized = {
        "schema_version": 2,
        "execution": dict(document["execution"]),
        "deployment": {
            name: DEPLOYMENT_REFERENCE_LITERAL
            for name in sorted(V2_DEPLOYMENT_REFERENCE_FIELDS)
        },
    }
    return canonical_sha256(normalized)


def semantic_config_sha256(document: object) -> str:
    """S: closed-parsed execution content plus fixed deployment reference literals."""

    return _semantic_config_sha256(document)


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    logical_path: str
    raw_sha256: str
    semantic_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.logical_path, str) or not self.logical_path:
            raise ContractError("INVENTORY_LOGICAL_PATH")
        path = PurePosixPath(self.logical_path)
        if path.is_absolute() or ".." in path.parts:
            raise ContractError("INVENTORY_LOGICAL_PATH")
        _require_sha256("raw_sha256", self.raw_sha256)
        if self.semantic_sha256 is not None:
            _require_sha256("semantic_sha256", self.semantic_sha256)

    @property
    def content_sha256(self) -> str:
        return self.semantic_sha256 or self.raw_sha256

    def as_document(self) -> dict[str, object]:
        return {
            "logical_path": self.logical_path,
            "raw_sha256": self.raw_sha256,
            "semantic_sha256": self.semantic_sha256,
        }


def build_inventory(
    files: Mapping[str, bytes], *, semantic_carriers: Mapping[str, str] | None = None
) -> tuple[InventoryEntry, ...]:
    """Build a logical-path inventory; only declared carriers may use a semantic digest."""

    if not isinstance(files, Mapping) or not files:
        raise ContractError("INVENTORY_FILES")
    carriers = dict(semantic_carriers or {})
    for logical_path, semantic in carriers.items():
        if logical_path not in files:
            raise ContractError(f"CARRIER_NOT_IN_FILES: {logical_path}")
        _require_sha256("semantic_carrier", semantic)
    entries = []
    for logical_path in sorted(files):
        content = files[logical_path]
        if not isinstance(content, (bytes, bytearray)):
            raise ContractError(f"INVENTORY_CONTENT: {logical_path}")
        entries.append(
            InventoryEntry(
                logical_path=logical_path,
                raw_sha256=hashlib.sha256(bytes(content)).hexdigest(),
                semantic_sha256=carriers.get(logical_path),
            )
        )
    return tuple(entries)


def inventory_sha256(entries: Sequence[InventoryEntry]) -> str:
    if not entries:
        raise ContractError("INVENTORY_EMPTY")
    return canonical_sha256(
        [
            {"logical_path": item.logical_path, "digest": item.content_sha256}
            for item in entries
        ]
    )


def _validated_inventory(entries: Sequence[InventoryEntry], name: str) -> tuple[InventoryEntry, ...]:
    values = tuple(entries)
    if not values:
        raise ContractError(f"INVENTORY_EMPTY: {name}")
    if len({item.logical_path for item in values}) != len(values):
        raise ContractError(f"INVENTORY_DUPLICATE: {name}")
    for item in values:
        if not isinstance(item, InventoryEntry):
            raise ContractError(f"INVENTORY_ENTRY: {name}")
    return values


@dataclass(frozen=True, slots=True)
class RuntimeFingerprint:
    schema_version: int
    facts: Mapping[str, object]
    normalization_sha256: str
    semantic_config_sha256: str
    execution_inventory_sha256: str
    installed_inventory_sha256: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 2:
            raise ContractError("SCHEMA_VERSION")
        if not isinstance(self.facts, Mapping) or not self.facts:
            raise ContractError("RUNTIME_FACTS")
        _require_json_safe(dict(self.facts), "$.facts")
        for name in (
            "normalization_sha256",
            "semantic_config_sha256",
            "execution_inventory_sha256",
            "installed_inventory_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        object.__setattr__(self, "facts", MappingProxyType(dict(self.facts)))

    def as_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "facts": dict(self.facts),
            "normalization_sha256": self.normalization_sha256,
            "semantic_config_sha256": self.semantic_config_sha256,
            "execution_inventory_sha256": self.execution_inventory_sha256,
            "installed_inventory_sha256": self.installed_inventory_sha256,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.as_document())


def build_runtime_fingerprint(
    *,
    config: object,
    source_inventory: Sequence[InventoryEntry],
    installed_inventory: Sequence[InventoryEntry],
    runtime_facts: Mapping[str, object],
    semantic_config_sha256: str | None = None,
) -> RuntimeFingerprint:
    """R: hardware/model/container/thread facts plus L/S/E/I. Never B/Q/P/M/D."""

    if isinstance(config, ParallelRuntimeConfigV2):
        if semantic_config_sha256 is None:
            raise ContractError("SEMANTIC_CONFIG_IDENTITY_REQUIRED")
    elif isinstance(config, Mapping):
        if semantic_config_sha256 is not None:
            raise ContractError("SEMANTIC_CONFIG_IDENTITY_AMBIGUOUS")
        semantic_config_sha256 = _semantic_config_sha256(config)
    else:
        raise ContractError("CONFIG_TYPE")
    if not isinstance(runtime_facts, Mapping) or not runtime_facts:
        raise ContractError("RUNTIME_FACTS")
    self_referential = _SELF_REFERENTIAL_FACTS & set(runtime_facts)
    if self_referential:
        raise ContractError(f"SELF_REFERENTIAL_FACT: {sorted(self_referential)!r}")
    source = _validated_inventory(source_inventory, "source")
    installed = _validated_inventory(installed_inventory, "installed")
    return RuntimeFingerprint(
        schema_version=2,
        facts=runtime_facts,
        normalization_sha256=normalization_sha256(),
        semantic_config_sha256=semantic_config_sha256,
        execution_inventory_sha256=inventory_sha256(source),
        installed_inventory_sha256=inventory_sha256(installed),
    )


@dataclass(frozen=True, slots=True)
class FullByteAudit:
    schema_version: int
    source_commit: str
    source_clean: bool
    prefix: str
    files: tuple[InventoryEntry, ...]
    origins: Mapping[str, str]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 2:
            raise ContractError("SCHEMA_VERSION")
        if not isinstance(self.source_commit, str) or re.fullmatch(
            r"[0-9a-f]{40}", self.source_commit
        ) is None:
            raise ContractError("SOURCE_COMMIT")
        if self.source_clean is not True:
            raise ContractError("SOURCE_NOT_CLEAN")
        if not isinstance(self.prefix, str) or not Path(self.prefix).is_absolute():
            raise ContractError("AUDIT_PREFIX")
        object.__setattr__(self, "files", _validated_inventory(self.files, "audit"))
        if not isinstance(self.origins, Mapping) or not self.origins:
            raise ContractError("AUDIT_ORIGINS")
        for name, origin in self.origins.items():
            if not isinstance(name, str) or not isinstance(origin, str) or not Path(
                origin
            ).is_absolute():
                raise ContractError("AUDIT_ORIGINS")
        object.__setattr__(self, "origins", MappingProxyType(dict(self.origins)))

    _FIELDS = ("schema_version", "source_commit", "source_clean", "prefix", "files", "origins")

    @classmethod
    def from_document(cls, document: object) -> "FullByteAudit":
        """Closed load: an audit produced anywhere must carry exactly these bytes' fields."""

        if not isinstance(document, Mapping):
            raise ContractError("AUDIT_MAPPING")
        unknown = set(document) - set(cls._FIELDS)
        missing = set(cls._FIELDS) - set(document)
        if unknown:
            raise ContractError(f"AUDIT_UNKNOWN_FIELD: {sorted(unknown)!r}")
        if missing:
            raise ContractError(f"AUDIT_MISSING_FIELD: {sorted(missing)!r}")
        raw_files = document["files"]
        if not isinstance(raw_files, (list, tuple)):
            raise ContractError("AUDIT_FILES")
        entries = []
        for payload in raw_files:
            if not isinstance(payload, Mapping):
                raise ContractError("AUDIT_FILE_MAPPING")
            unknown_file = set(payload) - {"logical_path", "raw_sha256", "semantic_sha256"}
            if unknown_file or "logical_path" not in payload or "raw_sha256" not in payload:
                raise ContractError("AUDIT_FILE_FIELDS")
            entries.append(InventoryEntry(
                logical_path=str(payload["logical_path"]),
                raw_sha256=payload["raw_sha256"],
                semantic_sha256=payload.get("semantic_sha256")))
        origins = document["origins"]
        if not isinstance(origins, Mapping):
            raise ContractError("AUDIT_ORIGINS")
        return cls(
            schema_version=document["schema_version"],
            source_commit=document["source_commit"],
            source_clean=document["source_clean"],
            prefix=document["prefix"],
            files=tuple(entries),
            origins={str(name): str(origin) for name, origin in origins.items()},
        )

    def as_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_commit": self.source_commit,
            "source_clean": self.source_clean,
            "prefix": self.prefix,
            "files": [item.as_document() for item in self.files],
            "origins": dict(self.origins),
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.as_document())


def verify_runtime_identity(fingerprint: RuntimeFingerprint, declared: str | None) -> str:
    """R is derived from real bytes; a declared identity must equal that digest."""

    if isinstance(fingerprint, str) or not isinstance(fingerprint, RuntimeFingerprint):
        raise ContractError("RUNTIME_FINGERPRINT")
    if declared is None:
        return fingerprint.sha256
    _require_sha256("declared_identity", declared)
    if fingerprint.sha256 != declared:
        raise ContractError("RUNTIME_FINGERPRINT_MISMATCH")
    return declared


def verify_deployment_equivalence(
    *,
    measured: FullByteAudit,
    deployed: FullByteAudit,
    measured_identity: RuntimeFingerprint,
    deployed_identity: RuntimeFingerprint,
) -> None:
    """Allow only declared carrier references and a registered location binding."""

    for name in (
        "normalization_sha256",
        "semantic_config_sha256",
        "execution_inventory_sha256",
        "installed_inventory_sha256",
    ):
        if getattr(measured_identity, name) != getattr(deployed_identity, name):
            raise ContractError(f"IDENTITY_DRIFT: {name}")
    if dict(measured_identity.facts) != dict(deployed_identity.facts):
        raise ContractError("RUNTIME_FACT_DRIFT")
    measured_files = {item.logical_path: item for item in measured.files}
    deployed_files = {item.logical_path: item for item in deployed.files}
    if set(measured_files) != set(deployed_files):
        raise ContractError("INVENTORY_PATH_DRIFT")
    for logical_path, before in measured_files.items():
        after = deployed_files[logical_path]
        if before.semantic_sha256 is not None or after.semantic_sha256 is not None:
            if before.semantic_sha256 is None or after.semantic_sha256 is None:
                raise ContractError(f"CARRIER_BOUNDARY_DRIFT: {logical_path}")
            if before.semantic_sha256 != after.semantic_sha256:
                raise ContractError(f"CARRIER_SEMANTIC_DRIFT: {logical_path}")
            continue
        if before.raw_sha256 != after.raw_sha256:
            raise ContractError(f"UNALLOWED_BYTE_DRIFT: {logical_path}")
    for name, origin in measured.origins.items():
        target = deployed.origins.get(name)
        if target == origin:
            continue
        if (
            origin != measured.prefix
            or target != deployed.prefix
            or measured.prefix == deployed.prefix
        ):
            raise ContractError(f"ORIGIN_MAPPING_UNREGISTERED: {name}")
