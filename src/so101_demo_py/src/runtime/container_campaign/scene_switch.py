"""The shard's stack follows the scene of its task (indoor P3, T1).

A collection whose scene list carries an appearance plan gives every task its own appearance. The simulator loads one scene when the stack
starts, so before a task whose appearance differs from the one the stack runs, the shard stops its stack and starts it again with the scene
of the task: the nominal installed scene, or the variant realized into the shard's owned root. Tasks that share the running appearance
(two nominal ones in a row) switch nothing.

What is proved before each start. The variant is realized by `scene_variant_run.realize_into`, which keeps it only if its stripped physics
fingerprint (version 2) equals the nominal scene's, so no collision geom, mass, joint, friction or camera moved. The model identity every
consumer compares is the frozen nominal one (the execution snapshot's `model_sha256`, the compile of the installed nominal scene): the
stack is launched with that identity declared (`ActStackLaunch.declared_model_sha256`), and the shard first compiles the installed nominal
scene itself and refuses unless its hash is the frozen one. The hash of the variant the simulator really loaded is recorded next to it.

Evidence. Every stop writes its stack receipt (`stack/cleanup-receipt.json`, written once); it is renamed to `cleanup-receipt-<n>.json`
before the next start, so the stop at the end of the shard finds its own. Every switch is written to `<owned root>/scene-switches/`
with its timings, and every task to `<owned root>/scene-appearance/<task id>.json`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import threading
import time
from pathlib import Path

from so101_demo.act import appearance_plan as ap
from so101_demo.act import frozen_appearance, model_equivalence, scene_variant, scene_variant_run

SWITCH_DIRECTORY = "scene-switches"
APPEARANCE_DIRECTORY = "scene-appearance"
PROOF_DIRECTORY = "model-equivalence"
RECEIPT = "cleanup-receipt.json"


class SceneSwitchRefused(RuntimeError):
    """The shard cannot give the stack the scene of the task; `args[0]` is the refusal code."""


def _write_once(directory: Path, name: str, document: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(document, sort_keys=True, indent=1, allow_nan=False) + "\n").encode()
    descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return directory / name


def compiled_model_sha256(path) -> str:
    """The sha256 of the compiled model of a scene file: the recipe of the execution snapshot's `model_sha256`."""

    import mujoco
    from so101_demo.adapters.act.physics import model_sha256

    return model_sha256(mujoco.MjModel.from_xml_path(str(path)))


class StackSceneSwitch:
    """Owns the shard's stack scene: `inventory`/`verify` for the rows, `switch` for a task."""

    def __init__(self, *, stack, owned_root, share, new_ready_probe, start_timeout_s, stop_timeout_s=None, clock=time.monotonic,
                 model_sha256=compiled_model_sha256):
        if not callable(new_ready_probe) or not start_timeout_s > 0:
            raise ValueError("SCENE_SWITCH_CONFIG_INVALID")
        self.stack = stack
        self.owned_root = Path(owned_root)
        self.share = Path(share)
        self.new_ready_probe = new_ready_probe
        self.start_timeout_s = float(start_timeout_s)
        self.stop_timeout_s = stack.stop_timeout_s if stop_timeout_s is None else stop_timeout_s
        self.clock = clock
        self._model_sha256 = model_sha256
        self._inventory = None
        #: the realized hash of the variant the stack runs, None for the nominal scene (every stack starts on the nominal one)
        self.current = None
        #: the equivalence proof of the running variant stack (path, sha256, loaded hash), None on the nominal scene
        self.proof = None
        self.switches = 0
        self._lock = threading.Lock()

    @property
    def nominal_dir(self) -> Path:
        return scene_variant_run.nominal_dir(self.share)

    def inventory(self) -> dict:
        if self._inventory is None:
            self._inventory = ap.scene_inventory(self.nominal_dir, verify_files=True)
        return self._inventory

    def entry(self, frozen: dict, manifest_path, scene_id: str):
        """`frozen_appearance.scene_entry` with this host's inventory; None for a list without a plan."""

        return frozen_appearance.scene_entry(frozen, manifest_path, scene_id, inventory=self.inventory)

    def _nominal_identity(self, expected_model_sha256: str) -> str:
        nominal = self._model_sha256(self.nominal_dir / scene_variant.INDOOR_SCENE)
        if nominal != expected_model_sha256:
            raise SceneSwitchRefused("SCENE_SWITCH_NOMINAL_MODEL_MISMATCH: the installed indoor scene does not compile to the frozen model identity")
        return nominal

    def prepare(self, appearance: dict, scene_id: str, *, expected_model_sha256: str) -> dict:
        """The scene the task needs, realized and proved physics-equal: `{"variant": record or None, "declared_model_sha256"}`."""

        if appearance["variant"] is None:
            return {"variant": None, "declared_model_sha256": None}
        nominal = self._nominal_identity(expected_model_sha256)
        try:
            record = scene_variant_run.realize_into(self.owned_root / scene_variant_run.SCENE_DIRECTORY / scene_id, self.share,
                                                    appearance["variant"])
        except scene_variant.SceneVariantRefused as error:
            raise SceneSwitchRefused(f"SCENE_SWITCH_VARIANT_REFUSED: {error}") from error
        if record["variant_sha256"] != appearance["variant_sha256"]:
            raise SceneSwitchRefused("SCENE_SWITCH_VARIANT_HASH_MISMATCH")
        return {"variant": record, "declared_model_sha256": nominal}

    def _prove(self, scene_id: str, prepared: dict):
        """The equivalence proof of a variant (written once under `model-equivalence/`): `(path, sha256, loaded hash)`."""

        record = prepared["variant"]
        loaded = self._model_sha256(record["scene_path"])
        proof = model_equivalence.make_proof(scene_id=scene_id, declared_model_sha256=prepared["declared_model_sha256"],
                                             loaded_model_sha256=loaded, record=record)
        path, digest = model_equivalence.write_proof(self.owned_root / PROOF_DIRECTORY, proof)
        return path, digest, loaded

    def switch(self, appearance: dict, scene_id: str, *, expected_model_sha256: str) -> dict:
        """Give the stack the scene of this task; returns the record of what was done (also written under `scene-switches/`).

        Blocking (it runs on the task builder's thread): it stops the stack and starts it again, only when the scene differs. A variant
        stack is launched with the nominal model identity declared AND the sha256 of its equivalence proof; the proof is bound to this
        process (and so to the Teacher it starts) for as long as that stack runs, and unbound again on the nominal scene."""

        with self._lock:
            prepared = self.prepare(appearance, scene_id, expected_model_sha256=expected_model_sha256)
            variant = prepared["variant"]
            wanted = None if variant is None else variant["realized_sha256"]
            record = {"scene_id": scene_id, "kind": appearance["kind"], "from_realized_sha256": self.current, "to_realized_sha256": wanted,
                      "declared_model_sha256": prepared["declared_model_sha256"], "switched": wanted != self.current,
                      "equivalence_proof": self.proof}
            if wanted == self.current:
                return record
            proof = None
            if variant is not None:
                proof = self._prove(scene_id, prepared)
            began = self.clock()
            record.update(asyncio.run(self._restart(variant, prepared["declared_model_sha256"], None if proof is None else proof[1])))
            record["total_s"] = round(self.clock() - began, 3)
            self.current = wanted
            self.proof = None if proof is None else {"path": str(proof[0]), "sha256": proof[1], "loaded_model_sha256": proof[2]}
            record["equivalence_proof"] = self.proof
            model_equivalence.bind(os.environ, None if proof is None else proof[0], None if proof is None else proof[1])
            self.switches += 1
            record["switch_index"] = self.switches
            _write_once(self.owned_root / SWITCH_DIRECTORY, f"{self.switches:03d}-{scene_id}.json", record)
            return record

    async def _restart(self, variant, declared, proof_sha256) -> dict:
        stack = self.stack
        if stack.process is None:
            raise SceneSwitchRefused("SCENE_SWITCH_STACK_NOT_RUNNING")
        old_owner = stack.owner
        began = self.clock()
        model_equivalence.bind(os.environ, None, None)       # nothing is proved while the stack is down
        await stack.stop(timeout_s=self.stop_timeout_s)
        stopped = self.clock()
        receipt = self.owned_root / "stack" / RECEIPT
        archived = receipt.with_name(f"cleanup-receipt-{self.switches + 1}.json")
        if not receipt.is_file() or archived.exists():
            raise SceneSwitchRefused("SCENE_SWITCH_RECEIPT_MISSING")
        receipt_sha256 = hashlib.sha256(receipt.read_bytes()).hexdigest()
        receipt.rename(archived)
        launch = dataclasses.replace(stack.launch, mujoco_scene=None if variant is None else Path(variant["scene_path"]),
                                     declared_model_sha256=declared, equivalence_proof_sha256=proof_sha256)
        probe = self.new_ready_probe(launch)
        stack.relaunch_with(launch, ready_probe=probe)
        owner = await stack.start(timeout_s=self.start_timeout_s)
        started = self.clock()
        return {"stop_s": round(stopped - began, 3), "start_s": round(started - stopped, 3), "stopped_owner_pid": old_owner.pid,
                "started_owner_pid": owner.pid, "stop_receipt": archived.name, "stop_receipt_sha256": receipt_sha256,
                "readiness_sha256": hashlib.sha256(getattr(probe, "readiness_bytes", b"") or b"").hexdigest()}

    def record_task(self, task_id: str, entry: dict, switch: dict) -> Path:
        """The per-task evidence: the draw, the Teacher source and what the stack was given."""

        appearance = entry["appearance"]
        document = {"task_id": task_id, "scene_id": appearance["scene_id"], "plan_sha256": entry["plan"]["plan_sha256"],
                    "kind": appearance["kind"], "draw_sha256": appearance["draw_sha256"], "variant_sha256": appearance["variant_sha256"],
                    "cup_family": appearance["cup_family"], "teacher_source": entry["teacher_source"], "switch": switch}
        return _write_once(self.owned_root / APPEARANCE_DIRECTORY, f"{task_id}.json", document)
