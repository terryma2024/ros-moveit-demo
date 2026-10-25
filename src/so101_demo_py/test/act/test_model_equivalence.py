"""The proof that lets a scene-variant stack declare the nominal model identity (indoor P3, decision D1).

Pins: an override is accepted only against a proof bound to the process; without an override nothing changes; both hashes and the proof reach
the Teacher manifest and episode.json; the offline processor binds (and unbinds) the proof of the episode it processes."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from so101_demo.act import model_equivalence as me

NOMINAL = "ab" * 32
LOADED = "cd" * 32
RECORD = {"fingerprint_version": 2, "nominal_physics_fingerprint": "11" * 32, "physics_fingerprint": "11" * 32,
          "realized_sha256": "22" * 32, "variant_sha256": "33" * 32}


def proof(**changes):
    return me.make_proof(scene_id="p3-001", declared_model_sha256=changes.pop("declared", NOMINAL),
                         loaded_model_sha256=changes.pop("loaded", LOADED), record={**RECORD, **changes})


def message(*, model=NOMINAL, declared="", loaded="", digest=""):
    return SimpleNamespace(model_sha256=model, declared_model_sha256=declared, loaded_model_sha256=loaded, equivalence_proof_sha256=digest)


def bound_proof(tmp_path, document=None):
    document = document or proof()
    path, digest = me.write_proof(tmp_path / "proofs", document)
    environ = {}
    me.bind(environ, path, digest)
    return me.bound(environ), environ, path, digest


def test_a_proof_needs_equal_stripped_fingerprints_a_declared_identity_that_differs_from_the_loaded_one_and_closed_hex_fields():
    document = proof()
    assert set(document) == me.FIELDS and me.verify_proof(document, declared_expected=NOMINAL) == document
    with pytest.raises(me.ModelEquivalenceRefused, match="MODEL_EQUIVALENCE_PHYSICS_DIFFERS"):
        proof(physics_fingerprint="44" * 32)
    with pytest.raises(me.ModelEquivalenceRefused, match="MODEL_EQUIVALENCE_NOTHING_DECLARED"):
        proof(loaded=NOMINAL)
    with pytest.raises(me.ModelEquivalenceRefused, match="MODEL_EQUIVALENCE_NOT_THE_FROZEN_MODEL"):
        me.verify_proof(document, declared_expected="ef" * 32)
    for key in ("realized_sha256", "loaded_model_sha256"):
        with pytest.raises(me.ModelEquivalenceRefused, match="MODEL_EQUIVALENCE_HASH_INVALID"):
            me.verify_proof({**document, key: "ZZ"})
    with pytest.raises(me.ModelEquivalenceRefused, match="MODEL_EQUIVALENCE_SHAPE_INVALID"):
        me.verify_proof({**document, "extra": 1})
    with pytest.raises(me.ModelEquivalenceRefused, match="MODEL_EQUIVALENCE_SHAPE_INVALID"):
        me.verify_proof({**document, "fingerprint_version": 1})


def test_the_proof_is_written_once_and_the_same_proof_again_is_the_same_file(tmp_path):
    path, digest = me.write_proof(tmp_path, proof())
    assert path.name == "p3-001.json" and digest == me.proof_sha256(proof()) and json.loads(path.read_text()) == proof()
    assert me.write_proof(tmp_path, proof()) == (path, digest)
    with pytest.raises(FileExistsError):
        me.write_proof(tmp_path, proof(loaded="ee" * 32))


def test_the_binding_is_read_and_checked_from_the_environment(tmp_path):
    assert me.bound({}) is None
    bound, environ, path, digest = bound_proof(tmp_path)
    assert bound["sha256"] == digest and bound["declared"] == NOMINAL and bound["loaded"] == LOADED
    broken = {me.ENV_PATH: str(path)}
    with pytest.raises(me.ModelEquivalenceRefused, match="MODEL_EQUIVALENCE_BINDING_INCOMPLETE"):
        me.bound(broken)
    with pytest.raises(me.ModelEquivalenceRefused, match="MODEL_EQUIVALENCE_FILE_CHANGED"):
        me.bound({**broken, me.ENV_SHA256: "00" * 32})
    path.write_text(json.dumps({"kind": "x"}))
    with pytest.raises(me.ModelEquivalenceRefused, match="MODEL_EQUIVALENCE_FILE_CHANGED"):
        me.bound(environ)
    me.bind(environ, None, None)
    assert me.bound(environ) is None and environ == {}


def test_a_scene_state_without_an_override_is_accepted_exactly_as_before(tmp_path):
    me.check_message(message(), NOMINAL, None)                                    # an older simulator: none of the three fields
    me.check_message(SimpleNamespace(model_sha256=NOMINAL), NOMINAL, None)         # a message that lacks the attributes altogether
    me.check_message(message(loaded=NOMINAL), NOMINAL, None)                       # a new simulator, no override: loaded is the model
    bound, *_ = bound_proof(tmp_path)
    me.check_message(message(loaded=NOMINAL), NOMINAL, bound)                      # a bound proof does not change a message without an override
    with pytest.raises(me.ModelEquivalenceRefused, match="SCENE_STATE_LOADED_MODEL_DIFFERS_WITHOUT_OVERRIDE"):
        me.check_message(message(loaded=LOADED), NOMINAL, None)


def test_an_override_without_a_bound_proof_is_refused(tmp_path):
    _, _, _, digest = bound_proof(tmp_path)
    declared = message(declared=NOMINAL, loaded=LOADED, digest=digest)
    with pytest.raises(me.ModelEquivalenceRefused, match="SCENE_STATE_OVERRIDE_UNPROVEN"):
        me.check_message(declared, NOMINAL, None)


def test_an_override_is_accepted_only_against_the_proof_with_exactly_its_hashes(tmp_path):
    bound, _, _, digest = bound_proof(tmp_path)
    me.check_message(message(declared=NOMINAL, loaded=LOADED, digest=digest), NOMINAL, bound)
    for changes in ({"loaded": "ee" * 32}, {"digest": "ff" * 32}):
        with pytest.raises(me.ModelEquivalenceRefused, match="SCENE_STATE_OVERRIDE_PROOF_MISMATCH"):
            me.check_message(message(**{"declared": NOMINAL, "loaded": LOADED, "digest": digest, **changes}), NOMINAL, bound)
    for bad in (message(declared="ee" * 32, loaded=LOADED, digest=digest), message(declared=NOMINAL, loaded="", digest=digest),
                message(declared=NOMINAL, loaded=LOADED, digest=""), message(declared=NOMINAL, loaded=NOMINAL, digest=digest),
                message(declared="", loaded=LOADED, digest=digest)):
        with pytest.raises(me.ModelEquivalenceRefused, match="SCENE_STATE_OVERRIDE_INVALID"):
            me.check_message(bad, NOMINAL, bound)


class Node:
    def __init__(self):
        self.callbacks = []

    def create_subscription(self, kind, topic, callback, qos):
        self.callbacks.append(callback)
        return object()


def adapter(environ, monkeypatch):
    from so101_demo.adapters.act.scene_state import RosSceneStateAdapter, SceneStateObserver

    for name in (me.ENV_PATH, me.ENV_SHA256):
        monkeypatch.delenv(name, raising=False)
    for name, value in environ.items():
        monkeypatch.setenv(name, value)
    hazards = []
    observer = SceneStateObserver(model_sha256=NOMINAL, nq=1, nv=1, max_age_s=1.0)
    return RosSceneStateAdapter(Node(), observer, on_hazard=hazards.append), hazards


def ros_message(**fields):
    stamp = SimpleNamespace(sec=1, nanosec=0)
    base = dict(simulation_session_id="session-1", reset_epoch=1, simulation_step=3, paused=False, model_sha256=NOMINAL, qpos=[0.0], qvel=[0.0],
                clock_interval_begin_monotonic_ns=1, clock_interval_end_monotonic_ns=2, header=SimpleNamespace(stamp=stamp))
    return SimpleNamespace(**{**base, **fields})


def test_the_adapter_turns_an_unproved_override_into_a_hazard_and_a_proved_one_into_an_accepted_message(tmp_path, monkeypatch):
    _, environ, _, digest = bound_proof(tmp_path)
    overriding = ros_message(declared_model_sha256=NOMINAL, loaded_model_sha256=LOADED, equivalence_proof_sha256=digest)
    unbound, hazards = adapter({}, monkeypatch)
    unbound.accept_message(overriding)
    assert hazards == ["SCENE_STATE_OVERRIDE_UNPROVEN"]
    bound, hazards = adapter(environ, monkeypatch)
    bound.accept_message(copy.copy(overriding))
    assert not any("OVERRIDE" in str(item) for item in hazards)
    other, hazards = adapter(environ, monkeypatch)
    other.accept_message(ros_message(declared_model_sha256=NOMINAL, loaded_model_sha256="ee" * 32, equivalence_proof_sha256=digest))
    assert hazards == ["SCENE_STATE_OVERRIDE_PROOF_MISMATCH"]


def test_the_adapter_does_not_look_at_the_proof_of_a_message_without_an_override(tmp_path, monkeypatch):
    plain, hazards = adapter({}, monkeypatch)
    plain.accept_message(ros_message())
    plain.accept_message(ros_message(loaded_model_sha256=NOMINAL, declared_model_sha256="", equivalence_proof_sha256=""))
    assert not any("OVERRIDE" in str(item) or "LOADED" in str(item) for item in hazards)


def test_a_binding_that_is_not_a_proof_stops_the_adapter_at_construction(tmp_path, monkeypatch):
    with pytest.raises(me.ModelEquivalenceRefused, match="MODEL_EQUIVALENCE_BINDING_INCOMPLETE"):
        adapter({me.ENV_PATH: str(tmp_path / "missing.json")}, monkeypatch)


def test_the_offline_processor_binds_the_proof_of_its_episode_and_unbinds_it_for_the_next_one(tmp_path, monkeypatch):
    from so101_demo.act.offline.processor import bind_model_equivalence

    document = proof()
    record = {"model_equivalence": {"proof": document, "proof_sha256": me.proof_sha256(document), "declared_model_sha256": NOMINAL,
                                    "loaded_model_sha256": LOADED}}
    monkeypatch.delenv(me.ENV_PATH, raising=False)
    monkeypatch.delenv(me.ENV_SHA256, raising=False)
    bind_model_equivalence(tmp_path, record)
    assert me.bound()["sha256"] == me.proof_sha256(document)
    bind_model_equivalence(tmp_path, record)                                       # the same episode processed again
    bind_model_equivalence(tmp_path, {"source": "camera_rgbd", "model_equivalence": None})
    assert me.bound() is None
    bind_model_equivalence(tmp_path, None)
    assert me.bound() is None
    with pytest.raises(Exception, match="OFFLINE_MODEL_EQUIVALENCE_INVALID"):
        bind_model_equivalence(tmp_path / "x", {"model_equivalence": {**record["model_equivalence"], "proof_sha256": "00" * 32}})
