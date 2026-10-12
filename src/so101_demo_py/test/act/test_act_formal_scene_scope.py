"""A formal collection scope is valid for a row of the scene manifest the frozen input set binds.

One frozen input set serves a whole campaign. In `formal` mode only, a set may bind its scene manifest (the optional
`scene_manifest` key, covered by `inputs_sha256`), and a collection scope is then valid when its `(scene_id, seed)` is a row of
that bound file. A set without the key, and every `preselected_target_diagnostic` set, keeps the anchor-derived scope.

Real here: `freeze_inputs`/`verify_frozen_inputs`/`read_inputs_manifest` (the freezer copies and hashes the scene manifest
bytes), `build_collection_scope`, `require_scope_for_inputs` and, for the offline refusal, `process_bag` over the synthetic bag.
Controlled: the role candidates of `_registry` (synthetic approvals, as in the sibling freeze tests) and the scene-manifest rows
(hand-written; the sampler's manifest has the same `scenarios[]` shape with `scene_id`, `split`, `seed`).
"""

import hashlib
import json

import pytest

from so101_demo.act.collection_scope import build_collection_scope
from so101_demo.act.diagnostic_episode_inputs import (
    INPUT_ROLES, _canonical, freeze_inputs, read_inputs_manifest, verify_frozen_inputs)
from test_act_diagnostic_episode_scope import _registry, _write_registry

ROWS = [dict(scene_id="scene-a", seed=11, split="train", xy=[0.2, 0.1], cup_position_world_m=[0.2, 0.1, 0.165]),
        dict(scene_id="scene-b", seed=12, split="validation", xy=[0.25, -0.05],
             cup_position_world_m=[0.25, -0.05, 0.165])]
BOUND_PATH = "scene_manifest/scenes.json"
FORMAL = "formal"
DIAGNOSTIC = "preselected_target_diagnostic"


def scene_file(directory, rows=ROWS, name="scenes-source.json"):
    path = directory / name
    path.write_bytes(json.dumps({"scenarios": rows}).encode())
    return path


def candidates(tmp_path):
    return _write_registry(tmp_path, _registry(tmp_path))


def freeze_bound(tmp_path, *, rows=ROWS, mode=FORMAL, name="inputs"):
    source = scene_file(tmp_path, rows)
    return freeze_inputs(candidates(tmp_path), tmp_path / name, mode=mode, scene_manifest=source), source


def rewrite(manifest_path, document):
    """Rewrite a manifest with its hash chain recomputed, as a self-consistent forger would."""
    from so101_demo.act.diagnostic_episode_inputs import _MANIFEST_OPTIONAL
    extra = {key: document[key] for key in _MANIFEST_OPTIONAL if key in document}
    document["inputs_sha256"] = hashlib.sha256(_canonical({**document["roles"], **extra})).hexdigest()
    manifest_path.write_bytes(_canonical(document))


def golden_document():
    """A fixed, hand-written manifest of a set that predates `scene_manifest`: every role, mode and one policy key."""
    role = {name: {"path": f"{name}/{name}.json", "sha256": hashlib.sha256(name.encode()).hexdigest(),
                   "bytes": len(name), "approval": "source_controlled", "identity": None} for name in INPUT_ROLES}
    return {"kind": "ACT_DIAGNOSTIC_EPISODE_INPUTS", "schema_version": 2, "source_root": "/golden/source",
            "source_commit": "a" * 40, "config_sha256": "b" * 64, "evidence_root": "/golden/evidence", "roles": role,
            "mode": FORMAL}


#: sha256 of the canonical `{**roles, mode}` of `golden_document()`, computed with the code as it was BEFORE this change
GOLDEN_INPUTS_SHA256 = "3ddde7820ff5b0c125e7d1634e37dc2cd1ac939236749f1b54fe9b15efc441d3"


# ---- A1: binding ----------------------------------------------------------------------------------------------------------

def test_freeze_binds_scene_manifest_into_inputs_sha256(tmp_path):
    from so101_demo.act.diagnostic_episode_inputs import frozen_scene_rows

    manifest_path, source = freeze_bound(tmp_path)
    document = json.loads(manifest_path.read_bytes())
    binding = document["scene_manifest"]
    payload = source.read_bytes()
    assert binding == {"path": BOUND_PATH, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
                       "scene_count": 2}
    assert (manifest_path.parent / BOUND_PATH).read_bytes() == payload
    extra = {key: document[key] for key in ("mode", "scene_manifest")}
    assert document["inputs_sha256"] == hashlib.sha256(_canonical({**document["roles"], **extra})).hexdigest()
    assert read_inputs_manifest(manifest_path)["scene_manifest"] == binding
    frozen = verify_frozen_inputs(manifest_path)
    assert [(row["scene_id"], row["seed"]) for row in frozen_scene_rows(frozen, manifest_path)] == [
        ("scene-a", 11), ("scene-b", 12)]
    # the same roles with another scene list, and with no scene list, are three different input sets
    other = freeze_inputs(candidates(tmp_path), tmp_path / "other", mode=FORMAL,
                          scene_manifest=scene_file(tmp_path, ROWS[:1], "other-source.json"))
    plain = freeze_inputs(candidates(tmp_path), tmp_path / "plain", mode=FORMAL)
    digests = {json.loads(path.read_bytes())["inputs_sha256"] for path in (manifest_path, other, plain)}
    assert len(digests) == 3


def test_manifest_without_scene_manifest_hashes_as_before(tmp_path):
    # `_registry` embeds its tmp_path in the calibration role, so a freeze of it has no tmp-independent digest. The golden
    # therefore pins the reader/hasher on a fixed hand-written manifest, and the freezer is pinned against the old formula.
    document = golden_document()
    assert hashlib.sha256(_canonical({**document["roles"], "mode": FORMAL})).hexdigest() == GOLDEN_INPUTS_SHA256
    path = tmp_path / "golden-manifest.json"
    path.write_bytes(_canonical({**document, "inputs_sha256": GOLDEN_INPUTS_SHA256}))
    assert read_inputs_manifest(path)["inputs_sha256"] == GOLDEN_INPUTS_SHA256
    manifest_path = freeze_inputs(candidates(tmp_path), tmp_path / "inputs", mode=FORMAL)
    frozen = json.loads(manifest_path.read_bytes())
    assert "scene_manifest" not in frozen and not (manifest_path.parent / "scene_manifest").exists()
    assert frozen["inputs_sha256"] == hashlib.sha256(_canonical({**frozen["roles"], "mode": FORMAL})).hexdigest()
    assert "scene_manifest" not in verify_frozen_inputs(manifest_path)


@pytest.mark.parametrize("mode", [DIAGNOSTIC, None])
def test_scene_manifest_refused_outside_formal_mode(tmp_path, mode):
    source = scene_file(tmp_path)
    with pytest.raises(ValueError, match="INPUT_SCENE_MANIFEST_REQUIRES_FORMAL"):
        freeze_inputs(candidates(tmp_path), tmp_path / "inputs", mode=mode, scene_manifest=source)
    assert not (tmp_path / "inputs").exists()


def test_a_forged_diagnostic_set_carrying_a_scene_manifest_is_refused_at_verify(tmp_path):
    manifest_path, _ = freeze_bound(tmp_path)
    document = json.loads(manifest_path.read_bytes())
    document["mode"] = DIAGNOSTIC
    rewrite(manifest_path, document)
    with pytest.raises(ValueError, match="INPUTS_SCENE_MANIFEST_INVALID"):
        verify_frozen_inputs(manifest_path)


@pytest.mark.parametrize("damage", ["changed_bytes", "same_size", "missing", "symlink"])
def test_replaced_scene_manifest_bytes_refused_at_verify(tmp_path, damage):
    manifest_path, source = freeze_bound(tmp_path)
    frozen = manifest_path.parent / BOUND_PATH
    payload = frozen.read_bytes()
    if damage == "changed_bytes":
        frozen.write_bytes(payload + b" ")
    elif damage == "same_size":
        frozen.write_bytes(payload.replace(b"scene-a", b"scene-z"))
    elif damage == "missing":
        frozen.unlink()
    else:
        frozen.unlink()
        frozen.symlink_to(source)
    with pytest.raises(ValueError, match="INPUTS_SCENE_MANIFEST_INVALID"):
        verify_frozen_inputs(manifest_path)


def test_a_tampered_binding_is_refused(tmp_path):
    manifest_path, _ = freeze_bound(tmp_path)
    for change in ({"path": "scene_manifest/other.json"}, {"scene_count": 3}, {"bytes": 1}, {"extra": 1},
                   {"sha256": "c" * 64}):
        document = json.loads(manifest_path.read_bytes())
        document["scene_manifest"] = {**document["scene_manifest"], **change}
        # reuse the real frozen tree, change only the manifest: verify resolves the file under the manifest's directory
        target = manifest_path.parent / "inputs-forged.json"
        rewrite(target, document)
        with pytest.raises(ValueError, match="INPUTS_SCENE_MANIFEST_INVALID"):
            verify_frozen_inputs(target)


def _duplicate_key_bytes():
    return (b'{"scenarios":[{"scene_id":"scene-a","seed":1,"split":"train","seed":2}]}')


@pytest.mark.parametrize("rows", [
    [],
    [dict(ROWS[0]), dict(ROWS[0])],
    [dict(ROWS[0], seed=True)],
    [dict(ROWS[0], seed="11")],
    [dict(ROWS[0], seed=-1)],
    [dict(ROWS[0], seed=1.0)],
    [{key: value for key, value in ROWS[0].items() if key != "seed"}],
    [{key: value for key, value in ROWS[0].items() if key != "scene_id"}],
    [dict(ROWS[0], scene_id="")],
    [dict(ROWS[0], scene_id=" scene-a")],
    [dict(ROWS[0], scene_id=7)],
    [dict(ROWS[0], split="")],
    ["scene-a"],
], ids=["empty", "duplicate_id", "seed_bool", "seed_str", "seed_negative", "seed_float", "no_seed", "no_scene_id",
        "empty_id", "padded_id", "int_id", "empty_split", "row_not_object"])
def test_invalid_scene_manifest_rows_are_refused_at_freeze_and_at_verify(tmp_path, rows):
    source = scene_file(tmp_path, rows, "invalid-source.json")
    with pytest.raises(ValueError, match="INPUT_SCENE_MANIFEST_INVALID"):
        freeze_inputs(candidates(tmp_path), tmp_path / "inputs", mode=FORMAL, scene_manifest=source)
    assert not (tmp_path / "inputs").exists()
    # a self-consistent forger who swaps the frozen bytes and fixes the binding and the hash chain is still refused
    manifest_path, _ = freeze_bound(tmp_path, name="good")
    document = json.loads(manifest_path.read_bytes())
    payload = source.read_bytes()
    (manifest_path.parent / BOUND_PATH).write_bytes(payload)
    document["scene_manifest"].update(sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload))
    rewrite(manifest_path, document)
    with pytest.raises(ValueError, match="INPUTS_SCENE_MANIFEST_INVALID"):
        verify_frozen_inputs(manifest_path)


@pytest.mark.parametrize("payload", [b"not json", b"[]", b'{"scenarios":"x"}', b'{}', b'{"scenarios":[NaN]}',
                                     _duplicate_key_bytes()])
def test_a_bound_file_that_is_not_a_scene_manifest_is_refused(tmp_path, payload):
    source = tmp_path / "scenes-source.json"
    source.write_bytes(payload)
    with pytest.raises(ValueError, match="INPUT_SCENE_MANIFEST_INVALID"):
        freeze_inputs(candidates(tmp_path), tmp_path / "inputs", mode=FORMAL, scene_manifest=source)
    assert not (tmp_path / "inputs").exists()


def test_a_symlinked_or_missing_source_is_refused_at_freeze(tmp_path):
    real = scene_file(tmp_path)
    link = tmp_path / "link.json"
    link.symlink_to(real)
    for source in (link, tmp_path / "absent.json"):
        with pytest.raises(ValueError, match="INPUT_SCENE_MANIFEST_INVALID"):
            freeze_inputs(candidates(tmp_path), tmp_path / "inputs", mode=FORMAL, scene_manifest=source)
        assert not (tmp_path / "inputs").exists()


# ---- A2: acceptance ---------------------------------------------------------------------------------------------------------

MISMATCH = "EPISODE_SCOPE_INPUTS_MISMATCH"


def scope_of(frozen, scene_id, seed, mode=FORMAL):
    return build_collection_scope(mode, scene_id=scene_id, seed=seed, inputs_sha256=frozen["inputs_sha256"])


def bound(tmp_path):
    manifest_path, _ = freeze_bound(tmp_path)
    return manifest_path, verify_frozen_inputs(manifest_path)


def anchor_of(frozen):
    identity = frozen["roles"]["anchor_scene"]["identity"]
    return identity["scene_id"], identity["seed"]


def test_formal_scope_binds_manifest_row(tmp_path):
    from so101_demo.act.diagnostic_episode_inputs import require_scope_for_inputs

    manifest_path, frozen = bound(tmp_path)
    for row in ROWS:
        require_scope_for_inputs(scope_of(frozen, row["scene_id"], row["seed"]), frozen, manifest_path)


@pytest.mark.parametrize("scene,seed", [("scene-z", 11), ("default", 0), ("scene-a ", 11), ("", 11)])
def test_scope_for_unlisted_scene_refused(tmp_path, scene, seed):
    from so101_demo.act.diagnostic_episode_inputs import require_scope_for_inputs

    manifest_path, frozen = bound(tmp_path)
    document = scope_of(frozen, "scene-a", 11)
    document.update(scene_id=scene, seed=seed)
    with pytest.raises(ValueError, match=MISMATCH):
        require_scope_for_inputs(document, frozen, manifest_path)


def test_the_anchor_scope_is_valid_for_a_bound_set_only_when_default_is_a_row(tmp_path):
    from so101_demo.act.diagnostic_episode_inputs import require_scope_for_inputs

    manifest_path, _ = freeze_bound(tmp_path, rows=[dict(ROWS[0], scene_id="default", seed=0), ROWS[1]])
    frozen = verify_frozen_inputs(manifest_path)
    require_scope_for_inputs(scope_of(frozen, "default", 0), frozen, manifest_path)
    require_scope_for_inputs(scope_of(frozen, "scene-b", 12), frozen, manifest_path)


@pytest.mark.parametrize("seed", [0, 10, 12, 111])
def test_row_seed_mismatch_refused(tmp_path, seed):
    from so101_demo.act.diagnostic_episode_inputs import require_scope_for_inputs

    manifest_path, frozen = bound(tmp_path)
    with pytest.raises(ValueError, match=MISMATCH):
        require_scope_for_inputs(scope_of(frozen, "scene-a", seed), frozen, manifest_path)


def test_a_scope_of_another_input_set_or_mode_or_shape_is_refused(tmp_path):
    from so101_demo.act.diagnostic_episode_inputs import require_scope_for_inputs

    manifest_path, frozen = bound(tmp_path)
    good = scope_of(frozen, "scene-a", 11)
    for change in ({"inputs_sha256": "d" * 64}, {"mode": DIAGNOSTIC}, {"kind": "OTHER"}):
        with pytest.raises(ValueError, match=MISMATCH):
            require_scope_for_inputs({**good, **change}, frozen, manifest_path)
    with pytest.raises(ValueError, match=MISMATCH):
        require_scope_for_inputs({**good, "extra": 1}, frozen, manifest_path)


def test_the_helper_rereads_the_bound_file_and_refuses_a_replaced_one(tmp_path):
    from so101_demo.act.diagnostic_episode_inputs import require_scope_for_inputs

    manifest_path, frozen = bound(tmp_path)
    document = scope_of(frozen, "scene-a", 11)
    (manifest_path.parent / BOUND_PATH).write_bytes(json.dumps({"scenarios": [dict(ROWS[0], scene_id="scene-q")]}).encode())
    with pytest.raises(ValueError, match="INPUTS_SCENE_MANIFEST_INVALID"):
        require_scope_for_inputs(document, frozen, manifest_path)


def test_diagnostic_scope_still_anchor_only(tmp_path):
    from so101_demo.act.diagnostic_episode_inputs import require_scope_for_inputs

    manifest_path = freeze_inputs(candidates(tmp_path), tmp_path / "inputs", mode=DIAGNOSTIC)
    frozen = verify_frozen_inputs(manifest_path)
    scene, seed = anchor_of(frozen)
    require_scope_for_inputs(scope_of(frozen, scene, seed, DIAGNOSTIC), frozen, manifest_path)
    for document in (scope_of(frozen, "scene-a", 11, DIAGNOSTIC), scope_of(frozen, scene, seed, FORMAL)):
        with pytest.raises(ValueError, match=MISMATCH):
            require_scope_for_inputs(document, frozen, manifest_path)


def test_formal_without_manifest_still_anchor_only(tmp_path):
    from so101_demo.act.diagnostic_episode_inputs import require_scope_for_inputs

    manifest_path = freeze_inputs(candidates(tmp_path), tmp_path / "inputs", mode=FORMAL)
    frozen = verify_frozen_inputs(manifest_path)
    scene, seed = anchor_of(frozen)
    require_scope_for_inputs(scope_of(frozen, scene, seed), frozen, manifest_path)
    for document in (scope_of(frozen, "scene-a", 11), scope_of(frozen, scene, seed + 1),
                     scope_of(frozen, scene, seed, DIAGNOSTIC)):
        with pytest.raises(ValueError, match=MISMATCH):
            require_scope_for_inputs(document, frozen, manifest_path)


def offline_lease():
    from offline_synthetic_bag import ATTEMPT
    return dict(batch_id="batch-1", coordinator_epoch=1, worker_id="w00", worker_generation=1, point_id="point-1",
                attempt_id=ATTEMPT, lease_generation=1, lease_issued_monotonic_s=1.0,
                lease_deadline_monotonic_s=9_999_999.0)


class Reached(Exception):
    """Raised by the injected episode factory: the processor got past the scope decision."""


def refusing_factory(options):
    raise Reached


def test_offline_default_scope_refused_when_manifest_bound(tmp_path):
    """Real: `process_bag` over the synthetic MCAP and a real bound frozen set. Controlled: the bag and the episode factory."""
    from offline_synthetic_bag import build_bag
    from so101_demo.act.offline import processor
    from test_act_child_recorder_binding import frozen_child_inputs

    manifest_path, _, _ = frozen_child_inputs(tmp_path, mode=FORMAL, scene_manifest=scene_file(tmp_path),
                                              scope_scene=("scene-a", 11))
    bag = build_bag(tmp_path / "raw")
    out = tmp_path / "sealed"
    with pytest.raises(processor.OfflineRefused, match="OFFLINE_SCOPE_REQUIRED"):
        processor.process_bag(bag, out, inputs_manifest=manifest_path, lease=offline_lease(), scope=None,
                              episode_factory=refusing_factory)
    assert not (out / "episode-scope.json").exists() and not (out / "episode").exists()


def test_offline_default_scope_is_still_derived_without_a_bound_manifest(tmp_path):
    from offline_synthetic_bag import build_bag
    from so101_demo.act.collection_scope import read_collection_scope
    from so101_demo.act.offline import processor
    from test_act_child_recorder_binding import frozen_child_inputs

    manifest_path, manifest, _ = frozen_child_inputs(tmp_path)
    bag = build_bag(tmp_path / "raw")
    out = tmp_path / "sealed"
    with pytest.raises(Reached):
        processor.process_bag(bag, out, inputs_manifest=manifest_path, lease=offline_lease(), scope=None,
                              episode_factory=refusing_factory)
    derived = read_collection_scope(out / "episode-scope.json")
    assert (derived["scene_id"], derived["seed"], derived["mode"]) == ("default", 0, manifest["mode"])


def test_a_scope_passed_to_the_offline_processor_is_not_replaced_when_a_manifest_is_bound(tmp_path):
    from offline_synthetic_bag import build_bag
    from so101_demo.act.offline import processor
    from test_act_child_recorder_binding import _scope_for, frozen_child_inputs

    manifest_path, manifest, _ = frozen_child_inputs(tmp_path, mode=FORMAL, scene_manifest=scene_file(tmp_path),
                                                     scope_scene=("scene-b", 12))
    scope = _scope_for(tmp_path, "given-scope.json", "scene-b", 12, manifest["inputs_sha256"])
    with pytest.raises(Reached):
        processor.process_bag(build_bag(tmp_path / "raw"), tmp_path / "sealed", inputs_manifest=manifest_path,
                              lease=offline_lease(), scope=scope, episode_factory=refusing_factory)
    assert not (tmp_path / "sealed" / "episode-scope.json").exists()
