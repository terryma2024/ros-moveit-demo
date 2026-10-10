"""The general runtime policy: the three bounds every dynamic pick-place execution shares (pure, standalone).

The general (non-Teacher) runtime reads ``state_max_age_s``, ``state_unavailable_stop_s`` and ``execution_deadline_s`` from
one closed document, ``config/act/general_runtime_policy.yaml``. The Teacher has its own, larger policy
(``teacher_endpoint.load_teacher_execution_policy``); both documents answer to the same three value names.
"""

from __future__ import annotations

from .teacher_endpoint import EXECUTION_VALUES, _load_document, _real, _sha256

GENERAL_RUNTIME_KIND = "ACT_GENERAL_RUNTIME_POLICY"
GENERAL_RUNTIME_SCHEMA = 1
GENERAL_RUNTIME_FILE = "general_runtime_policy.yaml"
GENERAL_RUNTIME_FIELDS = frozenset({"kind", "schema_version", *EXECUTION_VALUES})


def load_general_runtime_policy(source) -> dict:
    """Load and validate the general runtime policy from YAML bytes or a path, with its sha256.

    A missing or extra field, an unknown kind or schema, or a bound that is not a finite positive number is refused
    (``GENERAL_RUNTIME_POLICY_INVALID``)."""

    code = "GENERAL_RUNTIME_POLICY_INVALID"
    document = _load_document(source, code)
    if not isinstance(document, dict) or set(document) != GENERAL_RUNTIME_FIELDS:
        raise ValueError(f"{code}: not the closed policy document")
    version = document["schema_version"]
    if document["kind"] != GENERAL_RUNTIME_KIND or type(version) is not int or version != GENERAL_RUNTIME_SCHEMA:
        raise ValueError(f"{code}: unknown kind or schema version")
    policy = {"kind": GENERAL_RUNTIME_KIND, "schema_version": version}
    for key in EXECUTION_VALUES:
        policy[key] = _real(document[key], key, code, allow_zero=False)
    return {**policy, "policy_sha256": _sha256(policy)}
