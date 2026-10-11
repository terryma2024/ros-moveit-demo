"""Phase 5 of the formal head search calibration: the selected perception values, read back.

Design section 7.2 fixes the dependency order: each candidate's perception operating point is calibrated
and frozen, the frozen candidates are evaluated and one is selected, and only then are the selected
perception parameters "carried over verbatim and verified". This phase is that verification, and it is
deliberately the *only* thing it does:

* each of the four perception values the bundle records - `min_confidence`, `tracking_iou`,
  `min_bbox_aspect` and `min_area_px2` - must equal, exactly, the point the phase-3 rule record chose
  and the value the frozen candidate document sealed. Exact means the same JSON number: no tolerance, no
  rounding, no clamping and no substitution, and a value the frozen candidate does not declare although
  the gate applies it (the gate would silently fall back to its own default) is refused as well. Any
  difference refuses with `CAL_VALUE_MUTATED`, naming the parameter and both values;
* the candidate identity the bundle carries must be the one the rule selected. The rule record names the
  candidate and the frozen candidate document seals its weight digest; the bundle's runtime identity has
  to carry that same digest, or the run refuses with `CAL_SELECTION_MISMATCH`;
* a readback document records, per parameter, the selected value, the bundle value, the frozen
  document's value and the verdict, together with the identity digests and the digests of the two
  documents the values were compared against.

Phase 5 consumes documents, never files: it is handed the assembled bundle, and it must not require any
other phase-8 artefact or a digest of one (plan section 2 row 5 - the readback compares against the
candidate document and the rule record, both of phase 3/4, because phase 8 has not produced a digest
yet). Consequently nothing is read and nothing is written unless the caller passes an explicit
`output_path`, which is the only file this module ever creates.

Two inferences this module makes, both deliberately conservative (they can refuse a bundle, never
certify a modified one): the phase-3 record is expected to be a real phase-3 document, so the embedded
rule record's digest must cover its own body and match the record's `rule_sha256`; and the frozen
candidate document is the one `freeze_candidate` writes, so its `operating_points.<domain>` seals
`min_confidence` and `tracker.iou`, while any further declaration it carries (`min_bbox_aspect`,
`min_area_px2`) is compared when present and recorded as not declared when absent.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1
KIND = "head_search_calibration_readback"
PHASE = "selected_perception_readback"

#: the two refusals this phase owns, exactly as the plan fixes their spelling
CAL_VALUE_MUTATED = "CAL_VALUE_MUTATED"
CAL_SELECTION_MISMATCH = "CAL_SELECTION_MISMATCH"
REFUSAL_CODES = (CAL_VALUE_MUTATED, CAL_SELECTION_MISMATCH)

#: the four perception values, in the order design section 7.1 lists them
PERCEPTION_PARAMETERS = (
    "min_confidence",
    "tracking_iou",
    "min_bbox_aspect",
    "min_area_px2",
)

#: the two values the selection gate applies, and therefore the two the frozen candidate document must
#: seal: an undeclared one is not a missing detail, it is the gate's own default (0.25 / 0.5) being
#: substituted for the calibrated value
GATE_APPLIED_VALUES = ("min_confidence", "tracking_iou")

DEFAULT_DOMAIN = "head"

#: every produced row and identity is a certified one: a difference refuses instead of being reported
VERDICT_IDENTICAL = "identical"

#: the readback artefact, named after the phase-3 document it verifies (design section 8.3)
READBACK_NAME = "perception-calibration-readback.json"

#: what the readback was compared against, recorded so the audit trail names its sources
VERIFIED_AGAINST = (
    "operating_point_document",
    "frozen_candidate_document",
    "bundle_document",
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CalibrationReadbackRefused(CalibrationInputsRefused):
    """A phase-5 refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _same_number(left, right) -> bool:
    """Exact equality of two recorded values: the same JSON number, not merely the same quantity.

    Comparing the canonical encodings is what makes the check exact. `0.3` is not `0.1 + 0.2`, and `100`
    is not `100.0`: both pairs are equal as quantities and different as recorded values, and the design
    requires the selected value carried over verbatim. A value that is not a finite JSON number (a
    string, a boolean, NaN or infinity) is never the selected value.
    """

    if type(left) not in (int, float) or type(right) not in (int, float):
        return False
    try:
        return json.dumps(left, allow_nan=False) == json.dumps(right, allow_nan=False)
    except ValueError:
        return False


def _phase3_parts(operating_point) -> dict:
    """Validate the phase-3 document and return the pieces the readback reads from it."""

    if not isinstance(operating_point, Mapping):
        raise ValueError("the operating point must be the document phase 3 produced")
    chosen = operating_point.get("chosen_point")
    if not isinstance(chosen, Mapping) or any(name not in chosen for name in PERCEPTION_PARAMETERS):
        raise ValueError(
            "the operating point records no chosen point of the four perception values, so there is "
            "nothing to read back"
        )
    candidate_id = operating_point.get("candidate_id")
    if type(candidate_id) is not str or not candidate_id:
        raise ValueError("the operating point names no candidate")
    domain = operating_point.get("domain", DEFAULT_DOMAIN)
    if type(domain) is not str or not domain:
        raise ValueError("the operating point's domain must be a non-empty name")
    rule = operating_point.get("rule")
    digest = operating_point.get("rule_sha256")
    if (
        not isinstance(rule, Mapping)
        or type(digest) is not str
        or _SHA256.fullmatch(digest) is None
    ):
        raise ValueError("the operating point carries no rule record with its own digest")
    body = {key: value for key, value in rule.items() if key != "rule_sha256"}
    if rule.get("rule_sha256") != digest or canonical_sha256(body) != digest:
        raise ValueError(
            "the operating point's rule digest does not cover the rule record it carries, so the rule "
            "that selected the point cannot be identified"
        )
    return {
        "chosen_point": dict(chosen),
        "candidate_id": candidate_id,
        "domain": domain,
        "rule_sha256": digest,
    }


def _frozen_parts(frozen_candidate, *, domain: str) -> dict:
    """Validate the frozen candidate document and return the pieces the readback reads from it."""

    if not isinstance(frozen_candidate, Mapping):
        raise ValueError("the frozen candidate must be the document freeze_candidate produced")
    candidate_id = frozen_candidate.get("candidate_id")
    if type(candidate_id) is not str or not candidate_id:
        raise ValueError("the frozen candidate document names no candidate")
    digest = frozen_candidate.get("weight_sha256")
    if type(digest) is not str or _SHA256.fullmatch(digest) is None:
        raise ValueError("the frozen candidate document seals no weight digest")
    points = frozen_candidate.get("operating_points")
    if not isinstance(points, Mapping) or not isinstance(points.get(domain), Mapping):
        raise ValueError(f"the frozen candidate document seals no {domain!r} operating point")
    return {"candidate_id": candidate_id, "weight_sha256": digest, "point": points[domain]}


def _frozen_declaration(point: Mapping, name: str) -> tuple[bool, object]:
    """The value the frozen candidate document declares for one parameter, and whether it declares one.

    The document is the one `freeze_candidate` writes, so `tracking_iou` is sealed as the tracker's
    `{"iou": ...}` - the declaration the gate applies as its NMS threshold. The other values are read
    from the operating point when a document declares them, and reported as not declared when it does
    not; an absent declaration is never invented, and the two the gate applies are refused instead of
    being reported as merely undeclared.
    """

    if name == "tracking_iou":
        tracker = point.get("tracker")
        if isinstance(tracker, Mapping) and set(tracker) == {"iou"}:
            return True, tracker["iou"]
        return False, None
    if name in point:
        return True, point[name]
    return False, None


def _bundle_parts(bundle) -> dict:
    """Validate the bundle phase 8 assembled and return the pieces the readback reads from it."""

    if not isinstance(bundle, Mapping):
        raise ValueError("the bundle must be the document phase 8 assembled")
    parameters = bundle.get("parameters")
    if not isinstance(parameters, Mapping):
        raise ValueError("the bundle declares no parameters")
    runtime_identity = bundle.get("runtime_identity")
    if not isinstance(runtime_identity, Mapping):
        raise ValueError("the bundle records no runtime identity")
    weights = runtime_identity.get("detector_weights_sha256")
    if type(weights) is not str or _SHA256.fullmatch(weights) is None:
        raise ValueError("the bundle records no detector weight digest")
    return {"parameters": parameters, "weights_sha256": weights}


def _bundle_value(parameters: Mapping, name: str):
    """The value the bundle records for one parameter, or None when it records none."""

    block = parameters.get(name)
    if not isinstance(block, Mapping):
        return None
    return block.get("value")


def verify_selected_candidate_identity(*, bundle, operating_point, frozen_candidate) -> dict:
    """Verify the bundle carries the identity the rule selected, and return the identity digests.

    The rule record names the candidate it selected and the frozen candidate document seals that
    candidate's weight digest, so the two together are the selected identity. The bundle has to carry
    the same weights in its runtime identity, because a bundle built from another candidate's weights is
    a different candidate no matter how well its values match. Either difference refuses with
    `CAL_SELECTION_MISMATCH` and never a warning.
    """

    record = _phase3_parts(operating_point)
    frozen = _frozen_parts(frozen_candidate, domain=record["domain"])
    weights = _bundle_parts(bundle)["weights_sha256"]
    if frozen["candidate_id"] != record["candidate_id"]:
        raise CalibrationReadbackRefused(
            CAL_SELECTION_MISMATCH,
            f"the rule selected candidate {record['candidate_id']!r} but the frozen candidate document "
            f"is candidate {frozen['candidate_id']!r}, so the values were frozen for another candidate",
        )
    if weights != frozen["weight_sha256"]:
        raise CalibrationReadbackRefused(
            CAL_SELECTION_MISMATCH,
            f"the bundle's runtime identity records the detector weights {weights} but the rule selected "
            f"candidate {record['candidate_id']!r} with weights {frozen['weight_sha256']}, so the bundle "
            "carries another candidate's weights",
        )
    return {
        "selected_candidate_id": record["candidate_id"],
        "frozen_candidate_id": frozen["candidate_id"],
        "bundle_weights_sha256": weights,
        "frozen_candidate_weights_sha256": frozen["weight_sha256"],
        "rule_sha256": record["rule_sha256"],
        "operating_point_sha256": canonical_sha256(operating_point),
        "frozen_candidate_sha256": canonical_sha256(frozen_candidate),
        "verdict": VERDICT_IDENTICAL,
    }


def compare_selected_perception_values(*, bundle, operating_point, frozen_candidate) -> dict:
    """Compare the four bundle values against the rule's chosen point and the frozen document.

    Every parameter gets one row naming the selected value, the bundle value, the frozen document's
    value and the verdict. A bundle value that is not the selected one - rounded, clamped, rewritten or
    missing altogether - refuses with `CAL_VALUE_MUTATED`, and so does a frozen document that disagrees
    with the rule record or that seals neither of the two values the gate applies. Nothing is repaired,
    coerced or dropped: a refused readback produces no row and no document.
    """

    record = _phase3_parts(operating_point)
    frozen = _frozen_parts(frozen_candidate, domain=record["domain"])
    parameters = _bundle_parts(bundle)["parameters"]
    rows: dict[str, dict] = {}
    for name in PERCEPTION_PARAMETERS:
        selected = record["chosen_point"][name]
        bundle_value = _bundle_value(parameters, name)
        if not _same_number(bundle_value, selected):
            if bundle_value is None:
                raise CalibrationReadbackRefused(
                    CAL_VALUE_MUTATED,
                    f"{name}: the bundle records no value but the rule selected {selected!r}; the "
                    "selected value did not enter the bundle",
                )
            raise CalibrationReadbackRefused(
                CAL_VALUE_MUTATED,
                f"{name}: the bundle records {bundle_value!r} but the rule selected {selected!r}; the "
                "value entered the bundle modified",
            )
        declares, frozen_value = _frozen_declaration(frozen["point"], name)
        if declares:
            if not _same_number(frozen_value, selected):
                raise CalibrationReadbackRefused(
                    CAL_VALUE_MUTATED,
                    f"{name}: the frozen candidate document records {frozen_value!r} but the rule "
                    f"selected {selected!r}; the frozen candidate is not the point the rule chose",
                )
        elif name in GATE_APPLIED_VALUES:
            raise CalibrationReadbackRefused(
                CAL_VALUE_MUTATED,
                f"{name}: the frozen candidate document records no {name} but the rule selected "
                f"{selected!r}, so the gate would apply its own default instead of the selected value",
            )
        rows[name] = {
            "selected_value": selected,
            "bundle_value": bundle_value,
            "frozen_candidate_value": frozen_value,
            "frozen_candidate_declares_value": declares,
            "verdict": VERDICT_IDENTICAL,
        }
    return rows


def readback_selected_perception_values(
    *, bundle, operating_point, frozen_candidate, output_path=None
) -> dict:
    """Produce phase 5's document: the selected values the bundle carries, and the identity it carries.

    The selection identity is verified first (a bundle of another candidate is not read back value by
    value), then the four values. Both refusals are the phase's own, and neither is ever reported
    instead of raised: a document exists only for a bundle whose values are the selected ones,
    unmodified. When `output_path` is given the document is written there and nowhere else; without it
    nothing is written.
    """

    record = _phase3_parts(operating_point)
    identity = verify_selected_candidate_identity(
        bundle=bundle, operating_point=operating_point, frozen_candidate=frozen_candidate
    )
    rows = compare_selected_perception_values(
        bundle=bundle, operating_point=operating_point, frozen_candidate=frozen_candidate
    )
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "domain": record["domain"],
        "candidate_id": identity["selected_candidate_id"],
        "parameter_names": list(PERCEPTION_PARAMETERS),
        "parameters": rows,
        "identity": identity,
        "values_unmodified": True,
        "selection_identity_matches": True,
        "verified_against": list(VERIFIED_AGAINST),
    }
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document
