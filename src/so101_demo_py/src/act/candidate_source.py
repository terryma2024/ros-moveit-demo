"""Task 10 inputs: a closed candidate-source document and its sampling config.

The document is supplied, never inferred: it names `minimum_gap_m` and the exact candidates of the
five formal splits plus the qualification sets (8 functional, 40 sustained-load). Nothing here invents
bounds, budgets, thresholds or scene membership, and nothing is loaded by module or import path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .contracts import finite, integer, sha256
from .sampling import COLLECTION_SPLITS, SPLITS

CANDIDATE_KEYS = frozenset({"xy", "arm_q", "search_start_rad", "seed"})
QUALIFICATION_KEYS = ("functional", "load")
QUALIFICATION_COUNTS = {"functional": 8, "load": 40}
_SOURCE_KEYS = frozenset({"schema_version", "kind", "config_sha256", "minimum_gap_m", "formal",
                          "qualification"})


def candidate_identity(candidate: dict) -> str:
    """The exact identity a reachability report must be keyed by (canonical bytes of the candidate)."""

    _require_candidate(candidate)
    # canonicalise the vectors so a list and a tuple of the same point share one identity
    canonical = {"xy": list(candidate["xy"]), "arm_q": list(candidate["arm_q"]),
                 "search_start_rad": candidate["search_start_rad"], "seed": candidate["seed"]}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _require_candidate(candidate: object) -> dict:
    if not isinstance(candidate, dict) or set(candidate) != CANDIDATE_KEYS:
        raise ValueError("CANDIDATE_INVALID")
    xy = candidate["xy"]
    arm_q = candidate["arm_q"]
    # make_manifest hands the verifier the point it actually sampled, whose vectors may be tuples
    if not isinstance(xy, (list, tuple)) or len(xy) != 2:
        raise ValueError("CANDIDATE_INVALID")
    if not isinstance(arm_q, (list, tuple)) or len(arm_q) != 6:
        raise ValueError("CANDIDATE_INVALID")
    # finite() VALIDATES and returns the value, so it must not be used as a predicate:
    # a legitimate 0.0 coordinate would read as falsy and reject a valid candidate.
    for value in (*xy, *arm_q):
        finite(value)
    finite(candidate["search_start_rad"])          # validates; the value itself may legitimately be 0.0
    integer(candidate["seed"])
    return candidate


def load_candidate_source(path: Path) -> dict:
    """Load and close a supplied candidate-source document."""

    document = json.loads(Path(path).read_bytes())
    if (not isinstance(document, dict) or set(document) != _SOURCE_KEYS
            or document["schema_version"] != 1 or document["kind"] != "act_candidate_source"):
        raise ValueError("CANDIDATE_SOURCE_INVALID")
    sha256(document["config_sha256"])
    gap = finite(document["minimum_gap_m"], nonnegative=True)
    if gap <= 0:
        raise ValueError("SPLIT_GAP_INVALID")
    formal = document["formal"]
    if not isinstance(formal, dict) or set(formal) != set(SPLITS):
        raise ValueError("CANDIDATE_SOURCE_INVALID")
    for name in SPLITS:
        candidates = formal[name]
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("CANDIDATE_SOURCE_INVALID")
        for candidate in candidates:
            _require_candidate(candidate)
    qualification = document["qualification"]
    if not isinstance(qualification, dict) or set(qualification) != set(QUALIFICATION_KEYS):
        raise ValueError("CANDIDATE_SOURCE_INVALID")
    for name, expected in QUALIFICATION_COUNTS.items():
        candidates = qualification[name]
        if not isinstance(candidates, list) or len(candidates) != expected:
            raise ValueError("QUALIFICATION_CANDIDATE_COUNT_INVALID")
        for candidate in candidates:
            _require_candidate(candidate)
    # the qualification sets are mutually exclusive with every formal split, by exact identity
    formal_ids = {candidate_identity(candidate) for name in SPLITS for candidate in formal[name]}
    qualification_ids = {candidate_identity(candidate)
                         for name in QUALIFICATION_KEYS for candidate in qualification[name]}
    if formal_ids & qualification_ids:
        raise ValueError("QUALIFICATION_FORMAL_OVERLAP")
    if len(qualification_ids) != sum(QUALIFICATION_COUNTS.values()):
        raise ValueError("QUALIFICATION_DUPLICATE_CANDIDATE")
    return {**document, "minimum_gap_m": gap}


def sampling_config(source: dict, *, candidate_port) -> dict:
    """The closed config `make_manifest` consumes, built only from the supplied document."""

    if not callable(getattr(candidate_port, "verify", None)):
        raise ValueError("CANDIDATE_PORT_REQUIRED")
    return {"schema_version": 1, "config_sha256": source["config_sha256"],
            "minimum_gap_m": source["minimum_gap_m"],
            "candidates": {name: list(source["formal"][name]) for name in SPLITS},
            "candidate_port": candidate_port}


def collection_splits() -> tuple[str, ...]:
    return tuple(COLLECTION_SPLITS)
