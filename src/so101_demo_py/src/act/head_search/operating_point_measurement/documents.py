"""Truth centres, frame records, the measurement document and the selection rule documents."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path

from so101_demo.act.head_search.operating_point import (
    CAL_RULE_AFTER_MEASUREMENT,
    check_split_isolation,
    normalise_operating_points,
    record_selection_rule,
)
from so101_demo.act.head_search.operating_point_measurement.planning import (
    CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
    CANDIDATE_IDS,
    DOMAINS,
    HELD_OUT_SPLIT,
    KIND,
    MATCH_RADIUS_PX,
    PHASE,
    RECEIPT_NAME,
    RULE_NAME,
    RULE_RECEIPT_KIND,
    SCHEMA_VERSION,
    SELECTION_SPLITS,
    TASK_RULE_NAME,
    VAL_SPLIT,
    _finite,
    _mapping,
    _refuse,
    operating_point_grid,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256


def polygon_centre(polygon, *, width: float, height: float) -> tuple[float, float]:
    """The area centroid of a published visible-mask polygon, in pixels.

    The polygons the datasets publish are dense contours of the visible mask, so their area centroid is
    the polygon region's own centre - the same quantity the recorder reads off a segmentation by taking
    the mean of the mask's pixel indices. A degenerate polygon (no area) falls back to the vertex mean.
    """

    if isinstance(polygon, (str, bytes)) or not isinstance(polygon, Sequence) or len(polygon) < 3:
        raise ValueError("a visible-mask polygon needs at least three vertices")
    points = []
    for vertex in polygon:
        if (
            isinstance(vertex, (str, bytes))
            or not isinstance(vertex, Sequence)
            or len(vertex) != 2
            or not all(_finite(value) for value in vertex)
        ):
            raise ValueError("every polygon vertex must be a pair of finite coordinates")
        points.append((float(vertex[0]) * float(width), float(vertex[1]) * float(height)))
    twice_area = 0.0
    x_sum = y_sum = 0.0
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        x_sum += (x0 + x1) * cross
        y_sum += (y0 + y1) * cross
    if twice_area == 0.0:
        return (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
    return x_sum / (3.0 * twice_area), y_sum / (3.0 * twice_area)


def truth_from_instances(instances, *, width: float, height: float) -> list[dict]:
    """The published ground-truth centres of one frozen dataset image, one per visible instance.

    The mask the dataset publishes is read first (its pixel mean is the recorder's own convention), and
    an instance that publishes only its visible-mask polygon is read from that polygon instead; the
    frame records which of the two it used, so a domain whose dataset publishes no mask cannot look
    like one that does.
    """

    import numpy as np

    from so101_demo.adapters.perception.mujoco_dataset.render import decode_binary_mask_rle

    centres = []
    for instance in instances or ():
        record = _mapping("a truth instance", instance)
        counts, shape = record.get("visible_mask_rle_counts"), record.get("mask_shape_hw")
        if counts is not None and shape is not None:
            mask = decode_binary_mask_rle(counts, shape)
            rows, columns = np.nonzero(mask)
            if columns.size:
                centres.append(
                    {
                        "instance_id": record.get("body_name") or "instance",
                        "x": float(columns.mean()),
                        "y": float(rows.mean()),
                        "visible_px": int(columns.size),
                        "truth_source": "visible_mask_rle_counts",
                    }
                )
                continue
        polygon = record.get("polygon_xy")
        if polygon is None:
            continue
        x, y = polygon_centre(polygon, width=width, height=height)
        centres.append(
            {
                "instance_id": record.get("body_name") or "instance",
                "x": x,
                "y": y,
                "visible_px": record.get("visible_pixel_count"),
                "truth_source": "polygon_xy",
            }
        )
    return centres


def _centres(name: str, truth) -> list[dict]:
    records = []
    for record in truth or ():
        centre = _mapping(f"a {name} centre", record)
        x, y = centre.get("x"), centre.get("y")
        if not (_finite(x) and _finite(y)):
            raise ValueError(f"a {name} centre declares no finite x/y")
        records.append(
            {
                "x": float(x),
                "y": float(y),
                "visible_px": centre.get("visible_px"),
                "instance_id": centre.get("instance_id"),
                "truth_source": centre.get("truth_source"),
            }
        )
    return records


def _detections_by_candidate(detections) -> dict:
    """One ordered detection list per candidate, with the bbox the geometric floors are applied to."""

    if not isinstance(detections, Mapping):
        raise ValueError("detections must map every candidate to its ordered detection list")
    recorded = {}
    for candidate_id in CANDIDATE_IDS:
        if candidate_id not in detections:
            raise ValueError(
                f"the frame records no measurement for candidate {candidate_id!r}; an absent "
                "measurement is not an empty detection list"
            )
        rows = []
        for row in detections[candidate_id]:
            detection = _mapping("a detection", row)
            if not _finite(detection.get("conf")):
                raise ValueError("every detection declares a finite conf")
            x, y = _centre_of_detection(detection)
            rows.append(
                {
                    "x": x,
                    "y": y,
                    "conf": float(detection["conf"]),
                    "w": detection.get("w"),
                    "h": detection.get("h"),
                }
            )
        recorded[candidate_id] = rows
    return recorded


def _centre_of_detection(detection: Mapping) -> tuple[float, float]:
    """A detection's centre, from `x`/`y` or from the bbox corners a caller recorded instead."""

    if _finite(detection.get("x")) and _finite(detection.get("y")):
        return float(detection["x"]), float(detection["y"])
    bbox = detection.get("bbox")
    if isinstance(bbox, Mapping) and all(
        _finite(bbox.get(corner)) for corner in ("x1", "y1", "x2", "y2")
    ):
        return (
            (float(bbox["x1"]) + float(bbox["x2"])) / 2.0,
            (float(bbox["y1"]) + float(bbox["y2"])) / 2.0,
        )
    raise ValueError("a detection declares no finite x/y")


def _latency_ms(latency_ms) -> dict:
    if not isinstance(latency_ms, Mapping):
        raise ValueError("latency_ms must map every candidate to its measured milliseconds")
    return {candidate_id: float(latency_ms[candidate_id]) for candidate_id in CANDIDATE_IDS}


def _frame(
    *,
    split: str,
    domain: str,
    camera_name: str,
    scenario: str,
    truth,
    detections,
    latency_ms,
    match_radius_px: float,
    scene: dict,
) -> dict:
    if split not in SELECTION_SPLITS:
        raise ValueError(
            f"a frame of the split {split!r} would leak a split the rule does not select on; the "
            f"measurement records only {list(SELECTION_SPLITS)}"
        )
    if domain not in DOMAINS:
        raise ValueError(f"a frame of the domain {domain!r} is not one of {list(DOMAINS)}")
    if type(scenario) is not str or not scenario:
        raise ValueError("every frame declares the scenario it was rendered as")
    return {
        "split": split,
        "domain": domain,
        "camera": camera_name,
        "scenario": scenario,
        "match_radius_px": float(match_radius_px),
        "truth": _centres("ground-truth", truth),
        "detections": _detections_by_candidate(detections),
        "latency_ms": _latency_ms(latency_ms),
        **scene,
    }


def static_frame(
    *,
    domain: str,
    camera_name: str,
    sample: Mapping,
    truth,
    detections,
    latency_ms,
    match_radius_px: float = MATCH_RADIUS_PX,
) -> dict:
    """One frozen dataset image's frame: the val split of one domain, with the dataset's own truth."""

    return _frame(
        split=sample.get("split") or VAL_SPLIT,
        domain=domain,
        camera_name=camera_name,
        scenario=sample.get("scenario"),
        truth=truth,
        detections=detections,
        latency_ms=latency_ms,
        match_radius_px=match_radius_px,
        scene={
            "seed": int(sample["seed"]),
            "scene_group_id": sample.get("scene_group_id"),
            "image": sample.get("image"),
            "image_sha256": sample.get("image_sha256"),
            "neck_rad": sample.get("neck_rad"),
        },
    )


def episode_frame(
    *,
    domain: str,
    camera_name: str,
    seed: int,
    neck_rad: float,
    scenario: str,
    split: str,
    truth,
    detections,
    latency_ms,
    match_radius_px: float = MATCH_RADIUS_PX,
) -> dict:
    """One rendered calibration episode's frame: one seed, one neck angle, one camera's own truth."""

    if type(seed) is not int or isinstance(seed, bool):
        raise ValueError("an episode frame declares an integer seed")
    if not _finite(neck_rad):
        raise ValueError("an episode frame declares a finite neck_rad")
    return _frame(
        split=split,
        domain=domain,
        camera_name=camera_name,
        scenario=scenario,
        truth=truth,
        detections=detections,
        latency_ms=latency_ms,
        match_radius_px=match_radius_px,
        scene={
            "seed": int(seed),
            "neck_rad": float(neck_rad),
            "scene_group_id": f"scene-{int(seed):09d}",
        },
    )


def operating_point_measurement_document(
    *, plan, frames, rules, static_reference=None, provenance=None, path=None
) -> dict:
    """Assemble the document the run declares under `--operating-point-measurements`.

    Its frames are the phase-3 input, and the document records the grid, the two rule records it was
    measured under, the point every detection was recorded at and the gate's own reference cells, so the
    choice can be re-derived from the document alone. `sha256` covers the body without itself, the
    convention the other calibration documents use.
    """

    declared = _mapping("the plan", plan)
    frame_list = [dict(frame) for frame in frames]
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "selection_splits": list(declared["selection_splits"]),
        "held_out_split": declared["held_out_split"],
        "val_split": declared["val_split"],
        "match_radius_px": declared["match_radius_px"],
        "recording": dict(declared["recording"]),
        "grid": [dict(point) for point in declared["grid"]],
        "grid_sha256": declared["grid_sha256"],
        "plan_sha256": declared["plan_sha256"],
        "neck_angles_rad": list(declared["neck_angles_rad"]),
        "episode_scenario_assignment": declared["episode_scenario_assignment"],
        "rule_sha256": {domain: rules[domain]["rule_sha256"] for domain in sorted(rules)},
        "candidates": [
            {
                "candidate_id": candidate["candidate_id"],
                "weights_sha256": candidate["weights_sha256"],
                "weights_name": candidate["weights_name"],
                "operating_points": dict(candidate["operating_points"]),
            }
            for candidate in declared["candidates"]
        ],
        "frames": frame_list,
        "frame_count": len(frame_list),
        "frames_per_split": {
            split: sum(1 for frame in frame_list if frame.get("split") == split)
            for split in declared["selection_splits"]
        },
        "frames_per_domain": {
            domain: sum(1 for frame in frame_list if frame.get("domain") == domain)
            for domain in DOMAINS
        },
        "static_reference": dict(static_reference or {}),
        "provenance": dict(provenance or {}),
    }
    document = {**body, "sha256": canonical_sha256(body)}
    if path is not None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document


def toolchain_identity(module_path) -> dict:
    """The toolchain root and source commit the running module belongs to, or nulls when it is a source tree.

    A build root carries `source-commit.txt` and an `install/` tree; a worktree checkout has neither, and
    then the fields stay None rather than naming a root that was never built.
    """

    path = Path(module_path).resolve()
    for parent in path.parents:
        if (parent / "install").is_dir() and (parent / "source-commit.txt").is_file():
            commit = (parent / "source-commit.txt").read_text(encoding="utf-8").strip()
            return {"toolchain_root": str(parent), "source_commit": commit or None}
    return {"toolchain_root": None, "source_commit": None}


def record_selection_rule_documents(
    *,
    production_config,
    measurements_output_dir,
    output_dir,
    domains=DOMAINS,
    generation=None,
    measurement_plan_sha256=None,
    provenance=None,
    command=None,
) -> dict:
    """Write the rule records **before** any measurement, or refuse to write anything at all.

    The grid comes from the sealed production search configuration and the splits and the tie-break chain
    are phase 3's own declaration, so the rule cannot differ from the rule phase 3 applies. The directory
    the measurement will own must not exist yet: a rule written after its measurement is exactly what
    design section 7.1 forbids, and the phase-3 module refuses such a record a second time from the other
    side. Nothing is written to the measurement directory - this producer owns only its own output.
    """

    grid = operating_point_grid(production_config=production_config)
    measurements = Path(measurements_output_dir)
    output = Path(output_dir)
    if measurements.exists():
        raise _refuse(
            CAL_RULE_AFTER_MEASUREMENT,
            f"{measurements} exists, so this rule record would be written after the measurement it is "
            "supposed to precede; the ordering design section 7.1 fixes cannot be re-established "
            "afterwards",
        )
    try:
        output.mkdir(parents=True)
    except FileExistsError as error:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"{output} exists; a rule record is never resumed or overwritten",
        ) from error
    rules = {}
    for domain in domains:
        rules[domain] = record_selection_rule(
            points=grid,
            selection_splits=list(SELECTION_SPLITS),
            held_out_splits=[HELD_OUT_SPLIT],
            measurements_admitted=0,
            domain=domain,
            generation=generation,
            measurement_plan_sha256=measurement_plan_sha256,
        )
    names = {"head": RULE_NAME, "task": TASK_RULE_NAME}
    for domain, rule in rules.items():
        (output / names[domain]).write_text(
            json.dumps(rule, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RULE_RECEIPT_KIND,
        "phase": PHASE,
        "status": "RECORDED",
        "command": command,
        "domains": sorted(rules),
        "rule_sha256": {domain: rules[domain]["rule_sha256"] for domain in sorted(rules)},
        "rule_paths": {domain: str(output / names[domain]) for domain in sorted(rules)},
        "point_count": len(grid),
        "grid_sha256": canonical_sha256(grid),
        "selection_splits": list(SELECTION_SPLITS),
        "held_out_split": HELD_OUT_SPLIT,
        "tie_break_chain": list(rules[sorted(rules)[0]]["tie_break_chain"]),
        "measurements_admitted": 0,
        "measurements_output_dir": str(measurements),
        "measurements_output_dir_existed": False,
        "generation": generation,
        "measurement_plan_sha256": measurement_plan_sha256,
        "provenance": dict(provenance or {}),
        "motion_commanded": False,
    }
    (output / RECEIPT_NAME).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"rules": rules, "receipt": receipt, "grid": grid}


def _verified_rule(*, rule, domain, grid) -> dict:
    """One declared rule record, validated by phase 3's own reader and checked against this producer's grid."""

    if not isinstance(rule, Mapping):
        raise ValueError(f"the {domain} selection rule must be a rule record phase 3 made")
    # phase 3's own reader refuses a doctored digest, a rule recorded after a measurement, a rule whose
    # splits overlap and a rule whose points are malformed - no second copy of those rules lives here
    check_split_isolation(rule=rule, measurements=[])
    if rule.get("domain") != domain:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"the rule declared for the {domain} domain records the domain {rule.get('domain')!r}",
        )
    if list(rule.get("selection_splits") or ()) != list(SELECTION_SPLITS):
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"the {domain} rule selects on {rule.get('selection_splits')}, not on "
            f"{list(SELECTION_SPLITS)}",
        )
    if list(rule.get("held_out_splits") or ()) != [HELD_OUT_SPLIT]:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"the {domain} rule reports the held-out splits {rule.get('held_out_splits')}, not "
            f"{[HELD_OUT_SPLIT]}",
        )
    if normalise_operating_points(rule.get("points")) != tuple(grid):
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"the {domain} rule declares a different grid than the one this measurement measured, so "
            "the measurement could not have been the rule's",
        )
    return dict(rule)


def _boxes(result) -> list[dict]:
    """One prediction's boxes as the frame records them: centre, confidence and the box's own size."""

    boxes = getattr(result, "boxes", None)
    recorded = []
    for box in boxes if boxes is not None else ():
        xywh = box.xywh[0]
        recorded.append(
            {
                "x": float(xywh[0]),
                "y": float(xywh[1]),
                "conf": float(box.conf),
                "w": float(xywh[2]),
                "h": float(xywh[3]),
            }
        )
    return recorded
