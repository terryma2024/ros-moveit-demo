"""The proof that lets a scene-variant stack declare the nominal model identity (indoor P3, decision D1).

A stack launched on a visual variant of the nominal scene publishes, in every scene-state message, THREE facts next to `model_sha256`
(which every consumer compares with the frozen nominal identity): `declared_model_sha256` (what it declares; equal to `model_sha256`),
`loaded_model_sha256` (the hash of the model it really loaded) and `equivalence_proof_sha256` (the sha256 of the proof below). The proof is
written by the shard before the stack is started: the variant's stripped physics fingerprint (version 2) equals the nominal scene's, and the
declared hash is the frozen one.

The substitution is visible and checked at every consumer of the scene state (`RosSceneStateAdapter`, live in the shard and in the Teacher,
and in the offline replay): a message that declares an override is accepted only when a proof with exactly that declared hash, loaded hash and
proof hash is bound to the process (`SO101_MODEL_EQUIVALENCE_PROOF`, a path, and `SO101_MODEL_EQUIVALENCE_PROOF_SHA256`); otherwise the scene
state is a hazard (`SCENE_STATE_OVERRIDE_UNPROVEN` / `_PROOF_MISMATCH`). A message without an override is exactly what it always was. The
Teacher manifest and the episode identity record the proof and both hashes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

KIND = "ACT_MODEL_EQUIVALENCE_PROOF"
SCHEMA_VERSION = 1
ENV_PATH = "SO101_MODEL_EQUIVALENCE_PROOF"
ENV_SHA256 = "SO101_MODEL_EQUIVALENCE_PROOF_SHA256"
DECLARED_ENV = "SO101_DECLARED_MODEL_SHA256"
FIELDS = frozenset({"kind", "schema_version", "scene_id", "declared_model_sha256", "loaded_model_sha256", "fingerprint_version",
                    "nominal_physics_fingerprint", "variant_physics_fingerprint", "realized_sha256", "variant_sha256"})
_HEX64 = re.compile(r"[0-9a-f]{64}")


class ModelEquivalenceRefused(ValueError):
    """The proof is not a proof, or a scene-state message declares an override that is not proved; `args[0]` is the refusal code."""


def _hex(value) -> bool:
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None


def make_proof(*, scene_id: str, declared_model_sha256: str, loaded_model_sha256: str, record: dict) -> dict:
    """The proof of one realized variant (`record` is `scene_variant_run.realize_into`'s record, which has already refused a physics difference)."""

    return verify_proof({"kind": KIND, "schema_version": SCHEMA_VERSION, "scene_id": scene_id, "declared_model_sha256": declared_model_sha256,
                         "loaded_model_sha256": loaded_model_sha256, "fingerprint_version": record["fingerprint_version"],
                         "nominal_physics_fingerprint": record["nominal_physics_fingerprint"],
                         "variant_physics_fingerprint": record["physics_fingerprint"], "realized_sha256": record["realized_sha256"],
                         "variant_sha256": record["variant_sha256"]})


def verify_proof(document, *, declared_expected: str | None = None) -> dict:
    """The proof, if it is a closed, well-formed proof of equal stripped physics fingerprints (and of `declared_expected`, when given)."""

    if not isinstance(document, dict) or set(document) != FIELDS or document["kind"] != KIND or document["schema_version"] != SCHEMA_VERSION:
        raise ModelEquivalenceRefused("MODEL_EQUIVALENCE_SHAPE_INVALID")
    if not isinstance(document["scene_id"], str) or not document["scene_id"] or document["fingerprint_version"] != 2:
        raise ModelEquivalenceRefused("MODEL_EQUIVALENCE_SHAPE_INVALID")
    for name in FIELDS - {"kind", "schema_version", "scene_id", "fingerprint_version"}:
        if not _hex(document[name]):
            raise ModelEquivalenceRefused("MODEL_EQUIVALENCE_HASH_INVALID: " + name)
    if document["nominal_physics_fingerprint"] != document["variant_physics_fingerprint"]:
        raise ModelEquivalenceRefused("MODEL_EQUIVALENCE_PHYSICS_DIFFERS")
    if document["declared_model_sha256"] == document["loaded_model_sha256"]:
        raise ModelEquivalenceRefused("MODEL_EQUIVALENCE_NOTHING_DECLARED")
    if declared_expected is not None and document["declared_model_sha256"] != declared_expected:
        raise ModelEquivalenceRefused("MODEL_EQUIVALENCE_NOT_THE_FROZEN_MODEL")
    return json.loads(json.dumps(document))


def proof_bytes(document: dict) -> bytes:
    return (json.dumps(document, sort_keys=True, indent=1, allow_nan=False) + "\n").encode()


def proof_sha256(document: dict) -> str:
    return hashlib.sha256(proof_bytes(document)).hexdigest()


def write_proof(directory, document: dict) -> tuple[Path, str]:
    """Write the proof once (`<scene id>.json`); returns its path and sha256."""

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    raw = proof_bytes(verify_proof(document))
    target = directory / f"{document['scene_id']}.json"
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    except FileExistsError:
        if target.is_symlink() or target.read_bytes() != raw:      # the same proof again is the same file; another one is a conflict
            raise
        return target, hashlib.sha256(raw).hexdigest()
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return target, hashlib.sha256(raw).hexdigest()


def bound(environ=None):
    """The proof bound to this process by `SO101_MODEL_EQUIVALENCE_PROOF`/`_SHA256`, as `{"proof", "sha256", "declared", "loaded"}`; None when none is bound.

    A path without its sha256, a file that is not the sha256, or a document that is not a proof is a refusal, never a silent None."""

    environ = os.environ if environ is None else environ
    path = environ.get(ENV_PATH)
    if not path:
        return None
    digest = environ.get(ENV_SHA256)
    if not _hex(digest):
        raise ModelEquivalenceRefused("MODEL_EQUIVALENCE_BINDING_INCOMPLETE")
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ModelEquivalenceRefused("MODEL_EQUIVALENCE_FILE_CHANGED")
    document = verify_proof(json.loads(raw))
    return {"proof": document, "sha256": digest, "declared": document["declared_model_sha256"], "loaded": document["loaded_model_sha256"]}


def bind(environ, path, digest: str | None) -> None:
    """Bind (`path` and `digest`) or clear (`path` None) the proof in `environ`."""

    if path is None:
        environ.pop(ENV_PATH, None)
        environ.pop(ENV_SHA256, None)
        return
    environ[ENV_PATH], environ[ENV_SHA256] = str(path), digest


def check_message(message, model_sha256: str, bound_proof) -> None:
    """Refuse a scene-state message whose override is not the bound proof's; accept (do nothing for) a message without one.

    `message` is the ROS message (or anything with the same attributes); the three fields an older message lacks read as empty."""

    declared = getattr(message, "declared_model_sha256", "") or ""
    loaded = getattr(message, "loaded_model_sha256", "") or ""
    proof = getattr(message, "equivalence_proof_sha256", "") or ""
    if not declared and not proof:
        if loaded not in ("", model_sha256):
            raise ModelEquivalenceRefused("SCENE_STATE_LOADED_MODEL_DIFFERS_WITHOUT_OVERRIDE")
        return
    if declared != model_sha256 or not _hex(loaded) or not _hex(proof) or loaded == declared:
        raise ModelEquivalenceRefused("SCENE_STATE_OVERRIDE_INVALID")
    if bound_proof is None:
        raise ModelEquivalenceRefused("SCENE_STATE_OVERRIDE_UNPROVEN")
    if (bound_proof["declared"], bound_proof["loaded"], bound_proof["sha256"]) != (declared, loaded, proof):
        raise ModelEquivalenceRefused("SCENE_STATE_OVERRIDE_PROOF_MISMATCH")
