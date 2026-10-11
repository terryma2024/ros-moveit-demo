"""The gate's declared `--episode-records`: the installed phase-3 flight's measured episode frames.

Phase 4's `compare` gate reads the episodes of the declared split as **one document per seed**, each
carrying the frames measured for that seed - with a per-candidate detection list and a per-candidate
latency for every frame, and the domain each frame belongs to (the gate loops the domains separately).
The installed `measure-operating-point` flight measures exactly those frames for the calibration seeds and
records them in one document; this producer re-shapes that measured document into the contract the gate
declares.

It **computes nothing**: every frame is copied verbatim, in its recorded order, and each written document
carries the digest of the frames it holds together with the path and digest of the measurement document it
came from. It refuses - before writing anything - a declared seed the flight never measured, a frame whose
detections or latencies do not cover all three candidates, a frame of an unknown domain, a domain the
split has no frames for (the gate refuses that from the other side with a less specific message),
and a frame whose seed is not the document it would land in.

Nothing here renders, detects, starts ROS or a simulator, and nothing is written unless the caller passes
an explicit `output_dir`; the receipt and the per-seed documents are the only files this module creates.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1
KIND = "head_search_episode_records"
RECEIPT_KIND = "head_search_episode_records_receipt"
PHASE = "frozen_candidate_evaluation"

#: the gate's contract: one document per seed, named so the directory reads as what it is
SEED_NAME = "seed-{seed}.json"
RECEIPT_NAME = "episode-records-receipt.json"
ARTIFACT_NAMES = (RECEIPT_NAME,)

#: the three candidates every frame has to carry a measurement for
CANDIDATE_IDS = ("A", "B", "C")

#: the two domains the gate evaluates separately; a split with no frame for one of them is refused by the
#: gate as an incomplete recording, so it is refused here by name instead
DOMAINS = ("head", "task")

#: the frames of these splits are the installed flight's calibration episodes
DEFAULT_SPLIT = "calibration"

CAL_EPISODE_RECORDS_INCOMPLETE = "CAL_EPISODE_RECORDS_INCOMPLETE"


class CalibrationEpisodeRecordsRefused(CalibrationInputsRefused):
    """A producer refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _refuse(detail: str) -> CalibrationEpisodeRecordsRefused:
    return CalibrationEpisodeRecordsRefused(CAL_EPISODE_RECORDS_INCOMPLETE, detail)


def _digest(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_json(path) -> Mapping:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise _refuse(f"{path} is not a JSON object")
    return document


def _declared_seeds(partitions: Mapping, split: str) -> list[int]:
    declared = partitions.get(split)
    if isinstance(declared, (str, bytes)) or not isinstance(declared, (list, tuple)) or not declared:
        raise _refuse(f"the scenario partitions declare no {split!r} seeds")
    seeds = []
    for item in declared:
        if isinstance(item, Mapping):
            item = item.get("seed")
        if type(item) is not int:
            raise _refuse(f"the {split!r} partition declares a seed that is not an integer: {item!r}")
        seeds.append(item)
    return seeds


def _frame_records(frame, *, where: str, seed: int) -> None:
    """One measured frame, checked against the contract the gate's own loader enforces."""

    if not isinstance(frame, Mapping):
        raise _refuse(f"{where}: a frame is not a document")
    if frame.get("seed") != seed:
        raise _refuse(
            f"{where}: the frame records seed {frame.get('seed')!r} but belongs to the seed {seed} document"
        )
    domain = frame.get("domain")
    if domain not in DOMAINS:
        raise _refuse(
            f"{where}: the frame records domain {domain!r}, which is neither of {list(DOMAINS)}, so the "
            "gate would not count it"
        )
    detections = frame.get("detections")
    if not isinstance(detections, Mapping):
        raise _refuse(f"{where}: the frame records no per-candidate detections")
    absent = sorted(name for name in CANDIDATE_IDS if name not in detections)
    if absent:
        raise _refuse(f"{where}: the frame has no measurement for candidates {absent}")
    latency = frame.get("latency_ms")
    if not isinstance(latency, Mapping) or any(name not in latency for name in CANDIDATE_IDS):
        raise _refuse(
            f"{where}: the frame records no per-candidate latency, so the gate could not measure the budget"
        )


def record_episode_records(
    *,
    measurements,
    partitions,
    output_dir,
    split: str = DEFAULT_SPLIT,
    command=None,
) -> dict:
    """Write one gate-contract document per declared seed, or refuse without writing anything.

    The measurement document is read once, its frames are grouped by seed and copied verbatim, and every
    declared seed of the split has to be covered by both domains before the output directory is created.
    """

    output = Path(output_dir)
    if output.exists():
        raise _refuse(f"{output} exists; the producer's documents are never resumed or overwritten")
    if type(split) is not str or not split:
        raise _refuse("the split must be a non-empty name")
    measured = _read_json(measurements)
    declared = _read_json(partitions)
    seeds = _declared_seeds(declared, split)
    frames = measured.get("frames")
    if isinstance(frames, (str, bytes)) or not isinstance(frames, (list, tuple)) or not frames:
        raise _refuse(f"{measurements} records no measured frames")

    declared_seeds = set(seeds)
    by_seed: dict[int, list] = {}
    for index, frame in enumerate(frames):
        if not isinstance(frame, Mapping) or frame.get("split") != split:
            continue
        seed = frame.get("seed")
        if type(seed) is not int:
            raise _refuse(f"{measurements}: frame {index} records no integer seed")
        if seed not in declared_seeds:
            raise _refuse(
                f"{measurements}: frame {index} records seed {seed}, which the {split!r} partition does "
                "not declare, so the measurement document and the partitions disagree"
            )
        by_seed.setdefault(seed, []).append(dict(frame))

    missing = [seed for seed in seeds if seed not in by_seed]
    if missing:
        raise _refuse(
            f"the {split!r} partition declares seeds {missing} that the measurement document never "
            "measured, so the gate would refuse an incomplete recording"
        )
    domains: list[str] = []
    for seed in seeds:
        for index, frame in enumerate(by_seed[seed]):
            _frame_records(frame, where=f"seed {seed} frame {index}", seed=seed)
            domain = frame["domain"]
            if domain not in domains:
                domains.append(domain)
    absent_domains = [domain for domain in DOMAINS if domain not in domains]
    if absent_domains:
        raise _refuse(
            f"the {split!r} measurements hold no frame for the domains {absent_domains}, so the gate "
            "would refuse the recording as incomplete for them"
        )

    documents = {
        seed: {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "phase": PHASE,
            "split": split,
            "seed": seed,
            "scene_group_id": by_seed[seed][0].get("scene_group_id"),
            "frame_count": len(by_seed[seed]),
            "frames": by_seed[seed],
            "frames_sha256": canonical_sha256(by_seed[seed]),
            "source": {"path": str(measurements), "sha256": _digest(measurements)},
        }
        for seed in seeds
    }
    receipt_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "phase": PHASE,
        "status": "RECORDED",
        "split": split,
        "seed_count": len(seeds),
        "frame_count": sum(len(by_seed[seed]) for seed in seeds),
        "domains": sorted(domains),
        "candidates": list(CANDIDATE_IDS),
        "seeds": [
            {"seed": seed, "frame_count": len(by_seed[seed]),
             "scene_group_id": by_seed[seed][0].get("scene_group_id")}
            for seed in seeds
        ],
        "frames_sha256": {str(seed): documents[seed]["frames_sha256"] for seed in seeds},
        "provenance": {
            "command": command,
            "measurements": {"path": str(measurements), "sha256": _digest(measurements)},
            "partitions": {"path": str(partitions), "sha256": _digest(partitions)},
        },
        "computed": False,
        "motion_commanded": False,
    }

    output.mkdir(parents=True)
    for seed, document in documents.items():
        (output / SEED_NAME.format(seed=seed)).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    receipt = {**receipt_body, "path": str(output / RECEIPT_NAME), "output_dir": str(output)}
    receipt_path = output / RECEIPT_NAME
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "documents": documents,
        "receipt": receipt,
        "receipt_path": receipt_path,
        "measurements_path": Path(measurements),
        "partitions_path": Path(partitions),
    }
