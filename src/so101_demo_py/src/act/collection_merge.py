"""Merge the sealed frozen indexes of several formal campaigns (one per host) into one index and one export manifest.

A source is one finished, sealed formal campaign: its `collection-index.json`, the run root that holds it (sealed: `SEALED.json` and the
seal manifest), the QUALIFIED report its formal run was admitted with, and a label for the host it ran on. The merged index keeps every
committed episode exactly as its source holds it (each one keeps its own `collection_evidence`, which names the original run root), so
export and training read it like any other frozen index.

Everything that can be refused is refused before anything is written. The refusal codes (each tested) are `MergeRefused` messages. A source owns exactly the scenes of its committed episodes; its uncommitted or INVALID attempts
are listed in the manifest (`non_committed_attempts`) and claim nothing:

  MERGE_SOURCES_TOO_FEW, MERGE_SOURCE_INVALID, MERGE_FORMAL_LIST_INVALID, MERGE_OUTPUT_EXISTS,
  MERGE_INDEX_INVALID, MERGE_INDEX_NOT_FROZEN, MERGE_SOURCE_UNSEALED, MERGE_SOURCE_READBACK_FAILED, MERGE_INDEX_NOT_SEALED,
  MERGE_QUALIFICATION_INVALID, MERGE_QUALIFICATION_NOT_QUALIFIED, MERGE_IDENTITY_MISMATCH,
  MERGE_SCENE_OVERLAP, MERGE_SCENE_NOT_IN_FORMAL_LIST, MERGE_UNION_NOT_FORMAL_LIST, MERGE_EPISODE_DUPLICATE.

The controlled identity compared is the one the qualification report records, without the environment class: `gpu_uuid` (the GPU is
recorded per source, with its model and the host label, and never compared).
"""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

INDEX_KIND = "act_collection_frozen_index"
REPORT_KIND = "ACT_PARALLEL_COLLECTION_QUALIFICATION"
#: the controlled-identity keys that are the environment of a host and so never compared between sources
ENVIRONMENT_IDENTITY_KEYS = frozenset({"gpu_uuid"})
SEAL_FILE = "SEALED.json"
_CHUNK = 8 << 20


class MergeRefused(ValueError):
    """A merge refusal; the message starts with the code."""


@dataclass(frozen=True)
class MergeSource:
    index: Path
    qualification_report: Path
    host: str
    run_root: Path | None = None            # default: the directory that holds the index


def _read_json(path, code):
    try:
        return json.loads(Path(path).read_bytes())
    except (OSError, ValueError) as error:
        raise MergeRefused(f"{code}: {path} cannot be read: {error}") from error


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(document) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


# ---- the seal ----------------------------------------------------------------------------------------------------------------

def read_seal(run_root: Path) -> tuple[dict, list]:
    """The seal record of a run root and its manifest entries; `MERGE_SOURCE_UNSEALED` when there is none or it is not intact."""
    record_path = run_root / SEAL_FILE
    if not record_path.is_file() or record_path.is_symlink():
        raise MergeRefused(f"MERGE_SOURCE_UNSEALED: {run_root} has no {SEAL_FILE}")
    try:
        record = json.loads(record_path.read_bytes())
        manifest = Path(record["manifest"])
        if sha256_file(manifest) != record["manifest_sha256"]:
            raise ValueError("seal manifest hash")
        entries = [json.loads(line) for line in manifest.read_text().splitlines() if line.strip()]
        if not all(isinstance(entry, dict) and isinstance(entry.get("path"), str) for entry in entries):
            raise ValueError("seal manifest entry")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise MergeRefused(f"MERGE_SOURCE_UNSEALED: the seal of {run_root} is not intact: {error}") from error
    return record, entries


def _check_entry(root: Path, entry: dict):
    path = root / entry["path"]
    if "symlink" in entry:
        return None if path.is_symlink() and os.readlink(path) == entry["symlink"] else f"SYMLINK {entry['path']}"
    if entry.get("special"):
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size != entry.get("bytes"):
        return f"SIZE {entry['path']}"
    return None if sha256_file(path) == entry.get("sha256") else f"SHA {entry['path']}"


def verify_seal(run_root: Path, entries: list, *, workers: int = 4) -> list:
    """Every file against its seal entry (size and sha256, symlink targets), no extra and no missing file. Returns the problems."""
    listed = {entry["path"] for entry in entries}
    present = {str(Path(directory, name).relative_to(run_root)) for directory, _, names in os.walk(run_root) for name in names}
    present.discard(SEAL_FILE)
    problems = [f"EXTRA {name}" for name in sorted(present - listed)] + [f"MISSING {name}" for name in sorted(listed - present)]
    with ThreadPoolExecutor(max(1, workers)) as pool:
        problems += [problem for problem in pool.map(lambda entry: _check_entry(run_root, entry), entries) if problem]
    return problems


# ---- the inputs --------------------------------------------------------------------------------------------------------------

def read_formal_list(path) -> dict:
    """scene id -> split of the formal list the campaigns were run on."""
    document = _read_json(path, "MERGE_FORMAL_LIST_INVALID")
    rows = document.get("scenarios") if isinstance(document, dict) else None
    if not isinstance(rows, list) or not rows:
        raise MergeRefused(f"MERGE_FORMAL_LIST_INVALID: {path} has no scenarios")
    splits = {}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("scene_id"), str)
                or not isinstance(row.get("split"), str) or not row["split"]):
            raise MergeRefused(f"MERGE_FORMAL_LIST_INVALID: {path}: a row without scene_id or split")
        if row["scene_id"] in splits:
            raise MergeRefused(f"MERGE_FORMAL_LIST_INVALID: {path}: scene {row['scene_id']} twice")
        splits[row["scene_id"]] = row["split"]
    return splits


def _index_document(path, name):
    document = _read_json(path, "MERGE_INDEX_INVALID")
    if not isinstance(document, dict):
        raise MergeRefused(f"MERGE_INDEX_INVALID: {name} is not a JSON object")
    if document.get("kind") != INDEX_KIND or document.get("qualification") is not False:
        raise MergeRefused(f"MERGE_INDEX_NOT_FROZEN: {name}: kind {document.get('kind')!r}, qualification "
                           f"{document.get('qualification')!r}; need {INDEX_KIND} and false")
    committed = document.get("committed_episodes")
    if not isinstance(committed, list):
        raise MergeRefused(f"MERGE_INDEX_INVALID: {name}: committed_episodes is not a list")
    seen = set()
    for entry in committed:
        if not isinstance(entry, dict) or not isinstance(entry.get("scene_id"), str):
            raise MergeRefused(f"MERGE_INDEX_INVALID: {name}: a committed episode without a string scene_id")
        if entry["scene_id"] in seen:
            raise MergeRefused(f"MERGE_EPISODE_DUPLICATE: {name}: scene {entry['scene_id']} committed twice")
        seen.add(entry["scene_id"])
    return document, committed


def covered_scenes(document, committed) -> set:
    """Every scene the campaign handled: collected, committed or without evidence. Retry attempts name a scene more than once.
    Informational only: a source owns the scenes of its committed episodes (`owned_scenes`), not these."""
    scenes = {entry["scene_id"] for entry in committed}
    for name in ("collected_tasks", "scenes_without_evidence"):
        for item in document.get(name) or ():
            if isinstance(item, dict) and isinstance(item.get("scene_id"), str):
                scenes.add(item["scene_id"])
    return scenes


def owned_scenes(committed) -> set:
    """The scenes a source owns: exactly those of its committed episodes."""
    return {entry["scene_id"] for entry in committed}


def non_committed_attempts(document, committed) -> list:
    """The attempts of the source that did not become a committed episode of their scene, for the merge manifest only (they claim nothing):
    `collected_tasks` rows (status: act_data_status, else result_status, else state; reason: act_data_reason) and `scenes_without_evidence`
    rows (status: state; reason), in index order. Attempts of a scene the source did commit are not listed."""
    owned = owned_scenes(committed)
    rows = []
    for name, status_keys, reason_key in (("collected_tasks", ("act_data_status", "result_status", "state"), "act_data_reason"),
                                          ("scenes_without_evidence", ("state",), "reason")):
        for item in document.get(name) or ():
            if not isinstance(item, dict) or not isinstance(item.get("scene_id"), str) or item["scene_id"] in owned:
                continue
            status = next((item[key] for key in status_keys if item.get(key) is not None), None)
            rows.append(dict(scene_id=item["scene_id"], status=status, reason=item.get(reason_key), **{"from": name}))
    return rows


def _report(path):
    document = _read_json(path, "MERGE_QUALIFICATION_INVALID")
    if (not isinstance(document, dict) or document.get("kind") != REPORT_KIND
            or not isinstance(document.get("controlled_identity"), dict)):
        raise MergeRefused(f"MERGE_QUALIFICATION_INVALID: {path} is not a qualification report")
    if document.get("status") != "QUALIFIED" or document.get("reasons") not in ([], None):
        raise MergeRefused(f"MERGE_QUALIFICATION_NOT_QUALIFIED: {path}: status {document.get('status')!r}")
    return document


def comparable_identity(report: dict) -> dict:
    """The controlled identity of a qualification report without the environment class."""
    return {key: value for key, value in report["controlled_identity"].items() if key not in ENVIRONMENT_IDENTITY_KEYS}


def environment_of(report: dict) -> dict:
    """GPU uuid and model of the host the report qualified on: identity version 2 records `environment`, version 1 the uuid in the identity."""
    environment = report.get("environment")
    if isinstance(environment, dict):
        return dict(gpu_uuid=environment.get("gpu_uuid"), gpu_model=environment.get("gpu_model"))
    return dict(gpu_uuid=report["controlled_identity"].get("gpu_uuid"), gpu_model=None)


def _mount_preflights(parsed, reference):
    """Mount mode (the identity names a mounted build): every source's run holds a passing environment check of that commit against that
    base image, and all of them checked the same base image manifest. Image mode: None, and no source may hold one."""
    from so101_demo.runtime.container_campaign.mount_build import PREFLIGHT_COPY, preflight_problem

    mount = reference.get("mount_build")
    found = {}
    for item in parsed:
        path = Path(item["run_root"]) / "host" / PREFLIGHT_COPY
        if mount is None:
            if path.exists():
                raise MergeRefused(f"MERGE_IDENTITY_MISMATCH: {item['name']} holds a mount preflight but its identity names no mounted build")
            continue
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError) as error:
            raise MergeRefused(f"MERGE_MOUNT_PREFLIGHT_MISSING: {item['name']}: {path}") from error
        problem = preflight_problem(record, mount, reference["image_source_install"]["shard"])
        if problem is not None:
            raise MergeRefused(f"MERGE_MOUNT_PREFLIGHT_REFUSED: {item['name']}: {problem}")
        found[item["name"]] = dict(host_label=record["host"], base_manifest_sha256=record["base_manifest_sha256"],
                                   warnings=record["warnings"], exceptions=record["exceptions"], record_sha256=sha256_file(path))
    if mount is None:
        return None
    manifests = {entry["base_manifest_sha256"] for entry in found.values()}
    if len(manifests) != 1:
        raise MergeRefused(f"MERGE_MOUNT_PREFLIGHT_REFUSED: the sources checked different base image manifests: {sorted(manifests)}")
    return found


# ---- the merge ---------------------------------------------------------------------------------------------------------------

def merge_collections(sources, formal_list, stamp, *, readback_workers: int = 4):
    """`(merged index, manifest)` of the sources, or a `MergeRefused`. Reads every source in full; writes nothing."""
    sources = list(sources)
    if len(sources) < 2:
        raise MergeRefused("MERGE_SOURCES_TOO_FEW: at least two sources are required")
    formal = read_formal_list(formal_list)
    parsed, identities = [], []
    for number, source in enumerate(sources):
        name = f"source {number} ({source.index})"
        if not source.host or not isinstance(source.host, str):
            raise MergeRefused(f"MERGE_SOURCE_INVALID: {name} has no host label")
        index_path = Path(source.index)
        run_root = Path(source.run_root) if source.run_root is not None else index_path.parent
        document, committed = _index_document(index_path, name)
        record, entries = read_seal(run_root)
        try:
            relative = str(index_path.resolve().relative_to(run_root.resolve()))
        except ValueError as error:
            raise MergeRefused(f"MERGE_INDEX_NOT_SEALED: {name} is not inside the sealed run root {run_root}") from error
        sealed = {entry["path"]: entry for entry in entries}
        if relative not in sealed or sealed[relative].get("sha256") != sha256_file(index_path):
            raise MergeRefused(f"MERGE_INDEX_NOT_SEALED: {name} is not an entry of the seal of {run_root}, or differs from it")
        problems = verify_seal(run_root, entries, workers=readback_workers)
        if problems:
            raise MergeRefused(f"MERGE_SOURCE_READBACK_FAILED: {name}: {len(problems)} problem(s), first: {problems[:5]}")
        report = _report(source.qualification_report)
        identities.append(comparable_identity(report))
        scenes = owned_scenes(committed)
        if not scenes:
            raise MergeRefused(f"MERGE_INDEX_INVALID: {name} committed no scene")
        parsed.append(dict(source=source, name=name, document=document, committed=committed, scenes=scenes, report=report,
                           handled=len(covered_scenes(document, committed)), attempts=non_committed_attempts(document, committed),
                           run_root=run_root, seal=record, entries=len(entries)))
    reference = identities[0]
    for number, identity in enumerate(identities[1:], start=1):
        if identity != reference:
            different = sorted(key for key in set(identity) | set(reference) if identity.get(key) != reference.get(key))
            raise MergeRefused(f"MERGE_IDENTITY_MISMATCH: source {number} differs from source 0 in {different}")
    preflights = _mount_preflights(parsed, reference)
    owner = {}
    for item in parsed:
        for scene in sorted(item["scenes"]):
            if scene in owner:
                raise MergeRefused(f"MERGE_SCENE_OVERLAP: scene {scene} is in {owner[scene]} and in {item['name']}")
            owner[scene] = item["name"]
    outside = sorted(set(owner) - set(formal))
    if outside:
        raise MergeRefused(f"MERGE_SCENE_NOT_IN_FORMAL_LIST: {len(outside)} scene(s), first: {outside[:5]}")
    missing = sorted(set(formal) - set(owner))
    if missing:
        raise MergeRefused(f"MERGE_UNION_NOT_FORMAL_LIST: {len(missing)} scene(s) of the formal list are in no source, first: {missing[:5]}")
    merged, manifest, records, versions = [], [], [], []
    for item in parsed:
        merged.extend(item["committed"])                       # byte for byte as the source holds them, in source order
        manifest.extend({"scene_id": entry["scene_id"], "status": "PASSED", "split": formal[entry["scene_id"]]}
                        for entry in item["committed"])
        schema = item["document"].get("schema_version")
        versions.append(schema if isinstance(schema, int) else 0)
        source = item["source"]
        report_path = Path(source.qualification_report)
        records.append(dict(
            index=str(Path(source.index).resolve()), index_sha256=sha256_file(source.index),
            campaign_id=item["document"].get("campaign_id"), index_schema_version=item["document"].get("schema_version"),
            run_root=str(item["run_root"].resolve()), seal_manifest_sha256=item["seal"]["manifest_sha256"], sealed_files=item["entries"],
            host=source.host, **environment_of(item["report"]),
            qualification_report=str(report_path.resolve()), qualification_report_sha256=sha256_file(report_path),
            scenes=item["handled"], committed=len(item["committed"]),
            **({} if preflights is None else dict(mount_preflight=preflights[item["name"]]))))
    index = dict(kind=INDEX_KIND, qualification=False, schema_version=max(versions), campaign_id="merged-" + stamp,
                 scene_count=len(formal), committed_episodes=merged,
                 provenance=dict(created=stamp, formal_list=str(Path(formal_list).resolve()),
                                 formal_list_sha256=sha256_file(formal_list),
                                 controlled_identity_sha256=hashlib.sha256(canonical(reference)).hexdigest(), sources=records))
    skipped = [dict(host=item["source"].host, index_sha256=sha256_file(item["source"].index), attempts=item["attempts"]) for item in parsed]
    return index, {"episodes": manifest, "non_committed_attempts": skipped}
