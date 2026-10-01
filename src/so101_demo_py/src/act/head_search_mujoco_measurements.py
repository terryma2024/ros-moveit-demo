"""The MuJoCo measurement document phase 7 consumes: one simulation timestep of the sealed scene.

`submit_lead_s` is `min(first_target_sim_s - submit_snapshot_sim_s) + one MuJoCo simulation timestep`
(design section 7.1), so phase 7 needs one number it cannot measure itself: the timestep of the MuJoCo
model the runtime actually steps. That number is a **declaration of the sealed model**, not a
distribution: the head-search scene carries it as `<option timestep="...">`, and the scene's bytes are
pinned by every sealed artefact of this calibration - the geometry seal's `source_digests.scene_sha256`,
the head dataset manifest's `mjcf_sha256` and the geometry contract's `accepted_scene_sha256` all name
the same digest.

This module turns that declaration into the document the run declares under `--mujoco-measurements`:

* :func:`read_mujoco_timestep` reads the scene's own `<option timestep="...">`, follows an
  `<include file="...">` when the including file declares none, and refuses a scene whose declaration is
  absent (`CAL_MUJOCO_EVIDENCE_MISSING`) or whose declarations disagree
  (`CAL_MUJOCO_EVIDENCE_CONTRADICTORY`). Two differing declarations are refused rather than resolved by
  MuJoCo's own last-one-wins merge rule: this document has to be the declaration the sealed model makes,
  not the one a reader happened to keep.
* :func:`validate_head_search_mujoco_measurements` cross-checks the scene's bytes against every declared
  sealed identity and builds the document, whose `path` and `sha256` are the convention the run's other
  measurement documents already use (`sha256 = canonical_sha256(body without the sha256 field)`, ledger
  HS-298). Without at least one sealed identity the document would be an anonymous XML reading, so it is
  refused rather than written.
* :func:`write_mujoco_measurements` is the producer: it claims a brand-new output directory, writes the
  document and the receipt into it, and records what ran. It never imports a detector, never touches a
  GPU, starts no ROS node and commands no motion; the receipt says so.

The document is honest about what it is: `measured_here` is `false` and `declared_by` names the sealed
declaration, because nothing here is a measured distribution - it is the sealed model's own timestep.
When `--mujoco-readback` is asked for, the producer additionally loads the scene in MuJoCo and records
`model.opt.timestep` as `mujoco_model_timestep_s`; a readback that disagrees with the declaration refuses
the document instead of preferring either number.
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
import xml.etree.ElementTree as ElementTree
from collections.abc import Mapping
from pathlib import Path

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1
KIND = "head_search_calibration_mujoco_measurements"
RECEIPT_KIND = "head_search_calibration_mujoco_measurements_receipt"
PHASE = "mujoco_measurements"

#: the artefact the run declares under `--mujoco-measurements`, and the one field phase 7 reads from it
ARTIFACT_NAME = "mujoco-measurements.json"
FIELD = "simulation_timestep_s"
UNIT = "s"

#: the sealed identities that pin the scene's bytes, and the key each records it under
IDENTITY_KEYS = {
    "geometry_seal": ("source_digests", "scene_sha256"),
    "dataset_manifest": (None, "mjcf_sha256"),
    "geometry_contract": (None, "accepted_scene_sha256"),
}

CAL_MUJOCO_EVIDENCE_MISSING = "CAL_MUJOCO_EVIDENCE_MISSING"
CAL_MUJOCO_EVIDENCE_CONTRADICTORY = "CAL_MUJOCO_EVIDENCE_CONTRADICTORY"
REFUSAL_CODES = (
    CAL_MUJOCO_EVIDENCE_MISSING,
    CAL_MUJOCO_EVIDENCE_CONTRADICTORY,
)

#: what the document's own digest covers: its whole body, its `path` included
DIGEST_CONVENTION = "sha256 = canonical_sha256(body without the sha256 field)"

DECLARED_BY = (
    "the sealed head-search MuJoCo scene's own <option timestep>: submit_lead_s adds one simulation "
    "timestep to the minimum controller goal-admission lead (design section 7.1), and the scene the "
    "runtime steps is the one this document's identity cross-checks pin"
)
SELECTION_FORMULA = (
    "simulation_timestep_s = the <option timestep> attribute of the sealed scene, or of the file it "
    "includes when the scene declares none; the scene's sha256 must equal the digest recorded by every "
    "declared sealed identity, and two differing declarations are refused rather than resolved"
)

#: how deep the include chain is followed, and the largest scene this reader will parse at all
MAX_INCLUDE_DEPTH = 8

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CalibrationMujocoMeasurementsRefused(CalibrationInputsRefused):
    """A MuJoCo-measurement refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _refuse(code: str, detail: str) -> CalibrationMujocoMeasurementsRefused:
    return CalibrationMujocoMeasurementsRefused(code, detail)


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _timestep_attribute(path: Path) -> list[tuple[float, str, Path]]:
    """Every `<option timestep>` declaration one scene file makes, in document order."""

    try:
        root = ElementTree.fromstring(Path(path).read_text(encoding="utf-8"))
    except (OSError, ElementTree.ParseError) as error:
        raise _refuse(
            CAL_MUJOCO_EVIDENCE_MISSING,
            f"the scene {path} cannot be read as a MuJoCo XML document, so its simulation timestep "
            f"cannot be declared: {error}",
        ) from error
    declarations = []
    for element in root.iter("option"):
        attribute = element.get("timestep")
        if attribute is None:
            continue
        try:
            value = float(attribute)
        except ValueError as error:
            raise _refuse(
                CAL_MUJOCO_EVIDENCE_MISSING,
                f"the scene {path} declares the non-numeric simulation timestep {attribute!r}",
            ) from error
        if not _finite(value) or value <= 0.0:
            raise _refuse(
                CAL_MUJOCO_EVIDENCE_MISSING,
                f"the scene {path} declares the non-positive simulation timestep {attribute!r}; a "
                f"model that steps no time cannot bound a submission lead",
            )
        declarations.append((value, attribute, Path(path)))
    return declarations


def _include_paths(path: Path) -> list[Path]:
    """The files one scene includes, resolved next to the including file."""

    try:
        root = ElementTree.fromstring(Path(path).read_text(encoding="utf-8"))
    except (OSError, ElementTree.ParseError):  # pragma: no cover - _timestep_attribute read it
        return []
    included = []
    for element in root.iter("include"):
        name = element.get("file")
        if not name:
            continue
        candidate = (Path(path).parent / name).resolve()
        included.append(candidate)
    return included


def _declarations(scene: Path, depth: int = 0, seen: set | None = None) -> list[tuple[float, str, Path]]:
    """Every declaration the scene makes, its own first and then the ones its includes make.

    The includes are read even when the scene declares a timestep itself: two differing declarations
    anywhere in the chain would force the reader to emulate MuJoCo's own override rule to know which one
    the model steps, and that emulation is not evidence.
    """

    seen = set() if seen is None else seen
    resolved = Path(scene).resolve()
    if resolved in seen or depth > MAX_INCLUDE_DEPTH:
        return []
    seen.add(resolved)
    declarations = _timestep_attribute(scene)
    for included in _include_paths(scene):
        declarations.extend(_declarations(included, depth + 1, seen))
    return declarations


def read_mujoco_timestep(scene_path) -> dict:
    """The sealed scene's declared simulation timestep, or the refusal that says why there is none."""

    scene = Path(scene_path)
    if not scene.is_file():
        raise _refuse(
            CAL_MUJOCO_EVIDENCE_MISSING,
            f"the scene {scene} does not exist, so no simulation timestep is declared anywhere",
        )
    declarations = _declarations(scene)
    if not declarations:
        raise _refuse(
            CAL_MUJOCO_EVIDENCE_MISSING,
            f"the scene {scene} declares no <option timestep> and neither does anything it includes, so "
            f"the MuJoCo simulation timestep is not declared by the sealed model",
        )
    values = {value for value, _attribute, _file in declarations}
    if len(values) > 1:
        raise _refuse(
            CAL_MUJOCO_EVIDENCE_CONTRADICTORY,
            f"the scene {scene} and its includes declare {len(values)} different simulation timesteps "
            f"{sorted(values)}; this document records the sealed model's declaration, so it refuses to "
            f"pick the one a merge rule would keep",
        )
    value, attribute, declaration_file = declarations[0]
    return {
        FIELD: value,
        "scene_path": str(scene),
        "scene_sha256": _digest(scene),
        "declaration_file": str(declaration_file),
        "declaration_sha256": _digest(declaration_file),
        "attribute": attribute,
    }


def _identity_scene_digest(name: str, document) -> str:
    """The scene digest one sealed identity records, or the refusal that says it records none."""

    if not isinstance(document, Mapping):
        raise ValueError(f"the declared {name} is not a JSON object")
    outer, key = IDENTITY_KEYS[name]
    section = document if outer is None else document.get(outer)
    digest = section.get(key) if isinstance(section, Mapping) else None
    if type(digest) is not str or _SHA256.fullmatch(digest) is None:
        where = key if outer is None else f"{outer}.{key}"
        raise _refuse(
            CAL_MUJOCO_EVIDENCE_MISSING,
            f"the declared {name} records no scene digest under {where}, so it cannot pin the scene this "
            f"document reads its simulation timestep from",
        )
    return digest


def sealed_identities(
    *,
    scene_sha256: str,
    geometry_seal_path=None,
    dataset_manifest_path=None,
    geometry_contract_path=None,
) -> list[dict]:
    """Every declared sealed identity, checked against the scene's own bytes."""

    declared = (
        ("geometry_seal", geometry_seal_path),
        ("dataset_manifest", dataset_manifest_path),
        ("geometry_contract", geometry_contract_path),
    )
    identities = []
    for name, path in declared:
        if path is None:
            continue
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        digest = _identity_scene_digest(name, document)
        if digest != scene_sha256:
            raise _refuse(
                CAL_MUJOCO_EVIDENCE_CONTRADICTORY,
                f"the declared {name} {path} pins the scene {digest}, but the scene this document read "
                f"digests to {scene_sha256}: the timestep would belong to a model the calibration did not "
                f"seal",
            )
        identities.append(
            {
                "name": name,
                "path": str(path),
                "sha256": _digest(Path(path)),
                "scene_sha256": digest,
                "agrees": True,
            }
        )
    if not identities:
        raise _refuse(
            CAL_MUJOCO_EVIDENCE_MISSING,
            "no sealed identity was declared, so nothing pins the scene this document reads: a timestep "
            "out of an anonymous XML file is not the sealed model's declaration",
        )
    return identities


def _readback(name: str, declared: float, observed) -> dict:
    """The document's record of the MuJoCo readback: taken and agreeing, or not taken at all."""

    if observed is None:
        return {
            "mujoco_model_timestep_s": None,
            "mujoco_readback": False,
            "readback_detail": (
                "no MuJoCo readback was requested; the value recorded here is the sealed scene's own "
                "declaration, and the startup readback that proves the running system uses it belongs to "
                "the run"
            ),
        }
    if not _finite(observed) or float(observed) <= 0.0:
        raise ValueError(f"a MuJoCo readback of {name} reports the non-positive timestep {observed!r}")
    if not math.isclose(float(observed), declared, rel_tol=0.0, abs_tol=1e-12):
        raise _refuse(
            CAL_MUJOCO_EVIDENCE_CONTRADICTORY,
            f"the sealed scene declares the simulation timestep {declared} but loading it in MuJoCo "
            f"reports {float(observed)}: the declaration and the model that steps time disagree",
        )
    return {
        "mujoco_model_timestep_s": float(observed),
        "mujoco_readback": True,
        "readback_detail": "the scene was loaded in MuJoCo and model.opt.timestep agrees with it",
    }


def validate_head_search_mujoco_measurements(
    *,
    scene_path,
    geometry_seal_path=None,
    dataset_manifest_path=None,
    geometry_contract_path=None,
    document_path=None,
    model_timestep_s=None,
    command=None,
) -> dict:
    """Build the document phase 7 declares: the sealed scene's timestep and the identities that pin it.

    The scene is read first, then every declared sealed identity has to agree with its bytes; only then
    is a value produced. `document_path` is the path the document will carry in its own body (the run
    cites the document by path and sha256), and `model_timestep_s` is a MuJoCo readback when one was
    taken - `None` records that none was.
    """

    declaration = read_mujoco_timestep(scene_path)
    identities = sealed_identities(
        scene_sha256=declaration["scene_sha256"],
        geometry_seal_path=geometry_seal_path,
        dataset_manifest_path=dataset_manifest_path,
        geometry_contract_path=geometry_contract_path,
    )
    value = declaration[FIELD]
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "path": None if document_path is None else str(document_path),
        "command": command,
        "unit": UNIT,
        "scene_path": declaration["scene_path"],
        "scene_sha256": declaration["scene_sha256"],
        "declaration_file": declaration["declaration_file"],
        "declaration_sha256": declaration["declaration_sha256"],
        "declared_attribute": declaration["attribute"],
        "declared_because": DECLARED_BY,
        "selection_formula": SELECTION_FORMULA,
        "sealed_identities": identities,
        "measured_here": False,
        "motion_commanded": False,
        "ros_nodes_started": False,
        "digest_convention": DIGEST_CONVENTION,
        FIELD: value,
        **_readback(FIELD, value, model_timestep_s),
    }
    document["sha256"] = canonical_sha256(
        {key: item for key, item in document.items() if key != "sha256"}
    )
    return document


def mujoco_model_timestep_s(scene_path) -> float:
    """Load the scene in MuJoCo and report the timestep the model would actually step.

    This is the only heavy import of this module, and it happens inside the call so the document layer
    stays a pure, independently testable library.
    """

    import mujoco

    model = mujoco.MjModel.from_xml_path(str(Path(scene_path)))
    return float(model.opt.timestep)


def runtime_identity(*, output_dir, mujoco_readback: bool) -> dict:
    """What the producer ran as: the interpreter, the module it loaded and the tools it did not load."""

    import so101_demo

    version = None
    try:
        import mujoco

        version = mujoco.__version__
    except ImportError:  # pragma: no cover - this environment ships MuJoCo
        version = None
    return {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "so101_demo_module_path": str(Path(so101_demo.__file__).resolve()),
        "mujoco_version": version,
        "mujoco_model_loaded": bool(mujoco_readback),
        "output_dir": str(output_dir),
        "mujoco_only": True,
        "detector_loaded": False,
        "cuda_used": False,
        "ros_nodes_started": False,
        "motion_commanded": False,
    }


def write_mujoco_measurements(
    *,
    scene_path,
    geometry_seal_path=None,
    dataset_manifest_path=None,
    geometry_contract_path=None,
    output_dir,
    mujoco_readback: bool = False,
    command=None,
) -> dict:
    """Produce the MuJoCo measurement document and its receipt into a brand-new directory.

    Nothing is measured here beyond reading a declaration, and nothing is fabricated: the caller's
    directory is claimed before anything is read, the readback is taken only when it was asked for, and
    the receipt says which of the two happened.
    """

    started = time.time()
    scene = Path(scene_path)
    if not scene.is_file():
        raise FileNotFoundError(f"the MuJoCo measurements need {scene}")
    output = Path(output_dir)
    output.mkdir(parents=True)
    observed = mujoco_model_timestep_s(scene) if mujoco_readback else None
    document = validate_head_search_mujoco_measurements(
        scene_path=scene,
        geometry_seal_path=geometry_seal_path,
        dataset_manifest_path=dataset_manifest_path,
        geometry_contract_path=geometry_contract_path,
        document_path=output / ARTIFACT_NAME,
        model_timestep_s=observed,
        command=command,
    )
    path = output / ARTIFACT_NAME
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "phase": PHASE,
        "status": "SUCCEEDED",
        "command": command,
        FIELD: document[FIELD],
        "unit": UNIT,
        "scene_path": document["scene_path"],
        "scene_sha256": document["scene_sha256"],
        "declaration_file": document["declaration_file"],
        "sealed_identities": [identity["name"] for identity in document["sealed_identities"]],
        "mujoco_readback": document["mujoco_readback"],
        "mujoco_model_timestep_s": document["mujoco_model_timestep_s"],
        "measurement_path": str(path),
        "measurement_sha256": document["sha256"],
        "elapsed_s": time.time() - started,
        "runtime_identity": runtime_identity(output_dir=output, mujoco_readback=mujoco_readback),
        "motion_commanded": False,
    }
    (output / "measurement-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"measurement": document, "receipt": receipt}
