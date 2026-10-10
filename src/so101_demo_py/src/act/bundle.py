"""Task 12: decide which episodes a training bundle may contain.

Two rules carry the weight here. Normalisation statistics may be computed from the train split only, so
`training_rows` is the only sanctioned way to select rows for them. And an episode directory is not an
episode: it counts only when the coordinator committed it and a verifier receipt agrees with the journal
hash, so a seal that nobody committed — or two receipts that disagree — never reaches a dataset.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

_EPISODE_KEYS = ("scene_id", "journal_sha256", "verifier_sha256")
_COLLECTION_EVIDENCE_KEYS=frozenset({'coordinator_root','result_location','scope_path','inputs_manifest','receipt'})


def _verify_collection_for_export(episode):
    """The collection mode of a committed episode that may be exported (see `_verified_collection`)."""
    return _verified_collection(episode)[0]


def _verified_collection(episode):
    """(mode, commit proof) of a committed episode that may be exported. Trace retained originals on every call; caller flags and cached proofs grant no eligibility.

    A readback entry point may hold a session that shares one QC *recomputation* between its calls (a computation, not a proof): the
    commit proof, the mode, the result status, the QC verdict and `export_eligible` are read and decided here afresh each time."""
    from .collection_scope import read_collection_scope
    from .result_store import verify_coordinator_commit,_safe
    evidence=episode.get('collection_evidence')
    if (episode.get('kind')!='ACT_COMMITTED_EPISODE' or type(episode.get('schema_version')) is not int
            or episode['schema_version']!=2 or type(evidence) is not dict or set(evidence)!=_COLLECTION_EVIDENCE_KEYS):
        raise ValueError('EPISODE_COLLECTION_EVIDENCE_REQUIRED')
    if any(not isinstance(episode.get(key),str) or len(episode[key])!=64
            or any(character not in '0123456789abcdef' for character in episode[key]) for key in _EPISODE_KEYS[1:]):
        raise ValueError('EPISODE_RECEIPT_INVALID')
    try:
        paths={key:_safe(Path(evidence[key])) for key in _COLLECTION_EVIDENCE_KEYS-{'receipt'}}
        scope=read_collection_scope(paths['scope_path'])
        proof=verify_coordinator_commit(paths['coordinator_root'],location=paths['result_location'],
            scope=paths['scope_path'],inputs_manifest=paths['inputs_manifest'])
    except (OSError,ValueError,TypeError,KeyError) as error:
        raise ValueError('EPISODE_COLLECTION_IDENTITY_INVALID') from error
    if (episode.get('journal_sha256')!=proof['commit_frame_sha256']
            or episode.get('verifier_sha256')!=proof['result_sha256']
            or evidence['receipt']!=proof['receipt']):
        raise ValueError('EPISODE_RECEIPT_CONFLICT')
    if (episode['scene_id']!=scope['scene_id'] or proof['collection_mode']!=scope['mode']
            or ('collection_mode' in episode and episode['collection_mode']!=scope['mode'])):
        raise ValueError('EPISODE_COLLECTION_IDENTITY_INVALID')
    if scope['mode']=='preselected_target_diagnostic':
        raise ValueError('DIAGNOSTIC_EPISODE_NOT_TRAINABLE')
    if scope['mode']!='formal':
        raise ValueError('EPISODE_COLLECTION_IDENTITY_INVALID')
    if proof['status']!='PASS' or proof.get('result_schema_version')!=3:
        # only a verified schema 3 result commit is exportable
        raise ValueError('EXPORT_EPISODE_RESULT_SCHEMA_INVALID')
    if proof['result_status']!='PASSED':
        raise ValueError('EXPORT_EPISODE_NOT_PASSED')
    if proof.get('act_data_qc')!='PASS' or proof.get('export_eligible') is not True:
        # the Teacher passed, but only an independent data QC PASS makes the episode training data
        raise ValueError('EXPORT_EPISODE_DATA_QC_NOT_PASSED')
    exclusion=_teacher_oracle_exclusion(evidence)
    if exclusion is not None:
        # design 2026-10-10 section 7: an offline data-selection rule. The episode stays sealed and committed with its data verdict.
        raise ValueError(f'EXPORT_EPISODE_ORACLE_EXCLUDED: {exclusion[0]} {exclusion[1]}')
    return scope['mode'],proof


def _teacher_oracle_exclusion(evidence):
    """(flag, phase) when the Teacher manifest of the sealed result makes the episode not training-eligible, else None.

    The manifest is the one the QC bound (its sha256 is in the QC reference check), so neither a replaced manifest nor a summary
    edited to hide a flag reaches this rule. A Teacher manifest without a process summary (policy v1/v2) is not judged here."""
    import hashlib

    from .episode_qc import REFERENCE_CHECK, read_qc_report
    from .result_store import _read_regular, _safe
    from .teacher_process import exclusion_of_manifest
    try:
        location=_safe(Path(evidence['result_location']))
        bound=read_qc_report(location/'qc-report.json')['checks'][REFERENCE_CHECK]['details']['teacher_manifest_sha256']
        raw=_read_regular(location/'dynamic'/'dynamic-execute-manifest.json')
    except (OSError,ValueError,TypeError,KeyError) as error:
        raise ValueError('EXPORT_EPISODE_TEACHER_MANIFEST_UNREADABLE') from error
    if hashlib.sha256(raw).hexdigest()!=bound:
        raise ValueError('EXPORT_EPISODE_TEACHER_MANIFEST_UNBOUND')
    return exclusion_of_manifest(raw)


_SCENE_ID=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*')
_FRAME_NAME=re.compile(r'frames/[0-9]{6}-(?:head|wrist)\.png')
_SHA256_HEX=re.compile(r'[0-9a-f]{64}')


def sealed_episode(evidence,proof):
    """(recorder directory, seal) of a committed episode, the seal being the very file the coordinator commit proof bound.

    The commit proof carries the sha256 of the sealed episode that the independent data QC verified end to end. Nothing in the
    recorder directory is trusted before that digest agrees: the rows and every frame are then bound by the seal `files` map."""
    from .result_store import _read_regular,_safe
    try:
        root=_safe(Path(evidence['result_location']))/'episode'
        raw=_read_regular(root/'seal.json')
        seal=json.loads(raw)
    except (OSError,ValueError,TypeError,KeyError) as error:
        raise ValueError('EXPORT_EPISODE_SEAL_UNBOUND') from error
    if hashlib.sha256(raw).hexdigest()!=proof.get('episode_seal_sha256'):
        raise ValueError('EXPORT_EPISODE_SEAL_UNBOUND')
    files=seal.get('files') if isinstance(seal,dict) else None
    if (seal.get('kind')!='ACT_EPISODE_SEAL' or seal.get('status')!='PASSED' or type(seal.get('record_count')) is not int
            or not isinstance(files,dict) or 'records.jsonl' not in files):
        raise ValueError('EXPORT_EPISODE_SEAL_UNBOUND')
    return root,seal


def _seal_digest(entry):
    digest=entry.get('sha256') if isinstance(entry,dict) else None
    if not isinstance(digest,str) or not _SHA256_HEX.fullmatch(digest):
        raise ValueError('EXPORT_EPISODE_SEAL_UNBOUND')
    return digest


def sealed_episode_content(episode):
    """The training content of a committed episode, read from its sealed recorder rows (design 2026-10-10 section 3.2).

    The commit is re-verified, the seal is the one the commit bound, and `records.jsonl` must hash to the seal `files` entry. The
    whitelist (`training_content`) then drops the per-record audit and every non-whitelisted key."""
    from .qc_session import assert_export_path_allowed
    from .result_store import _read_regular
    assert_export_path_allowed()
    _,proof=_verified_collection(episode)
    root,seal=sealed_episode(episode['collection_evidence'],proof)
    try:
        raw=_read_regular(root/'records.jsonl')
    except (OSError,ValueError) as error:
        raise ValueError('TRAINING_EPISODE_CONTENT_MISSING') from error
    if hashlib.sha256(raw).hexdigest()!=_seal_digest(seal['files']['records.jsonl']):
        raise ValueError('TRAINING_EPISODE_CONTENT_DIGEST_MISMATCH')
    try:
        rows=[json.loads(line) for line in raw.splitlines() if line.strip()]
    except ValueError as error:
        raise ValueError('TRAINING_EPISODE_CONTENT_INVALID') from error
    if len(rows)!=seal['record_count']:
        raise ValueError('TRAINING_EPISODE_CONTENT_INVALID')
    return training_content({'frames':len(rows),'rows':rows})


def _content_observations(content):
    """The observations of a whitelisted content, in order."""
    if 'rows' in content:
        return [row['observation'] for row in content['rows']]
    return [content['observation']]


def _content_actions(content):
    if 'rows' in content:
        return [row['action'] for row in content['rows']]
    return [content['action']]


def _check_dimensions(content):
    """State width 8 and action width 6 (act/training_config.py), refused at export rather than at the first training batch."""
    from .training_config import ACTION_DIM,STATE_DIM
    observations=_content_observations(content)
    if not observations:
        raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
    if (any(len(observation.get('state',())) != STATE_DIM for observation in observations)
            or any(len(action) != ACTION_DIM for action in _content_actions(content))):
        raise ValueError('EXPORT_EPISODE_DIMENSION_INVALID')


def _frame_plan(scene_id,content,files):
    """[(source name, dataset-relative path, sha256)] for every frame the content references; refuses what the seal does not bind."""
    plan=[]
    for observation in _content_observations(content):
        for key in ('head_png','wrist_png'):
            name=observation.get(key)
            if not isinstance(name,str) or not _FRAME_NAME.fullmatch(name) or name not in files:
                raise ValueError('EXPORT_EPISODE_FRAME_MISSING')
            plan.append((name,f'episodes/{scene_id}/{name}',_seal_digest(files[name])))
    return plan


#: What a training sample may contain (user, 2026-10-10: collision and force data do not enter training): the observation (joint state,
#: head and wrist image) and the action. The per-record audit (contact lists, normal forces), the Teacher process summary, the
#: oracle flags and every other contact, force or collision field stay in the sealed episode and its metadata.
TRAINING_OBSERVATION_KEYS=('sim_time_s','state','head_png','wrist_png')
TRAINING_CONTENT_KEYS=('frames','rows','state','observation','action')


def _numbers(value):
    import math
    if (not isinstance(value,(list,tuple)) or not value
            or any(isinstance(item,bool) or not isinstance(item,(int,float)) or not math.isfinite(item) for item in value)):
        raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
    return list(value)


def _training_observation(observation):
    if not isinstance(observation,dict):
        raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
    kept={}
    for key in TRAINING_OBSERVATION_KEYS:
        if key not in observation:
            continue
        value=observation[key]
        if key=='state':
            kept[key]=_numbers(value)
        elif key=='sim_time_s':
            kept[key]=_numbers([value])[0]
        elif not isinstance(value,str):
            raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
        else:
            kept[key]=value
    return kept


def training_content(content) -> dict:
    """The whitelisted view of an episode's content: only ``rows`` of ``observation`` and ``action`` (or a single ``observation`` and
    ``action``), plus the plain ``frames``/``state`` counters, survive; everything else, however it is named, is dropped. A row without an observation and a numeric action, or
    a value that hides a mapping in a numeric field, is refused."""
    if not isinstance(content,dict):
        raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
    kept={}
    for key in TRAINING_CONTENT_KEYS:
        if key not in content:
            continue
        value=content[key]
        if key=='frames':
            if type(value) is not int:
                raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
            kept[key]=value
        elif key in ('state','action'):
            kept[key]=_numbers(value)
        elif key=='observation':
            kept[key]=_training_observation(value)
        else:
            if not isinstance(value,list):
                raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
            rows=[]
            for row in value:
                if not isinstance(row,dict) or 'observation' not in row or 'action' not in row:
                    raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
                rows.append({'observation':_training_observation(row['observation']),'action':_numbers(row['action'])})
            kept[key]=rows
    if not kept:
        raise ValueError('EXPORT_EPISODE_CONTENT_MISSING')
    if 'rows' not in kept and not ('observation' in kept and 'action' in kept):
        # a content with neither rows nor an observation and an action holds nothing a trainer may learn from
        raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
    return kept


def training_rows(rows) -> list:
    """The rows normalisation may use: the train split, and nothing else."""

    if not isinstance(rows, (list, tuple)):
        raise ValueError("TRAINING_ROWS_INVALID")
    selected = []
    for row in rows:
        if not isinstance(row, dict) or "split" not in row:
            raise ValueError("TRAINING_ROWS_INVALID")
        if row["split"] == "train":
            selected.append(row)
    return selected


def _index(path) -> dict:
    target = Path(path)
    if not target.is_file():
        return {}                      # nothing was committed, so nothing may be exported
    try:
        document = json.loads(target.read_bytes())
    except ValueError as error:
        raise ValueError("CAMPAIGN_INDEX_INVALID") from error
    if not isinstance(document, dict):
        raise ValueError("CAMPAIGN_INDEX_INVALID")
    committed = document.get("committed_episodes", [])
    if not isinstance(committed, list):
        raise ValueError("CAMPAIGN_INDEX_INVALID")
    entries={}
    for entry in committed:
        if not isinstance(entry,dict) or not isinstance(entry.get('scene_id'),str):
            raise ValueError('CAMPAIGN_INDEX_INVALID')
        if entry['scene_id'] in entries:
            raise ValueError('EPISODE_RECEIPT_CONFLICT')
        entries[entry['scene_id']]=entry
    return entries


def resolve_committed_episodes(*, manifest: dict, campaign_index) -> tuple:
    """Episodes the coordinator committed, with a verifier receipt that agrees with the journal."""

    from .qc_session import assert_export_path_allowed

    assert_export_path_allowed()        # a cached proof grants no eligibility: only a readback entry point may hold a session here
    if not isinstance(manifest, dict) or not isinstance(manifest.get("episodes"), list):
        raise ValueError("MANIFEST_INVALID")
    committed = _index(campaign_index)
    resolved = []
    for episode in manifest["episodes"]:
        if not isinstance(episode, dict) or not isinstance(episode.get("scene_id"), str):
            raise ValueError("MANIFEST_INVALID")
        entry = committed.get(episode["scene_id"])
        if entry is None and type(episode.get('collection_evidence')) is dict:
            from .result_store import _safe
            evidence=episode['collection_evidence']
            try:
                actual_index=_safe(Path(evidence['coordinator_root']))/'aggregate_results.json'
                if _safe(Path(campaign_index))==actual_index:
                    entry=episode  # The verifier replays this exact original index and journal below.
            except (OSError,ValueError,TypeError,KeyError) as error:
                raise ValueError('EPISODE_COLLECTION_IDENTITY_INVALID') from error
        if entry is None:
            continue                                   # a directory without a coordinator commit
        if episode.get('status')!='PASSED' and entry.get('kind')!='ACT_COMMITTED_EPISODE':
            continue                                   # archival business failures are retained
        mode=_verify_collection_for_export(entry)
        # carry the content locator through: a resolved episode that forgets where its content lives
        # forces the exporter to guess, and guessing is what this module exists to prevent
        resolved.append({"kind":'ACT_COMMITTED_EPISODE',"schema_version":2,
                         "collection_evidence":entry['collection_evidence'],"collection_mode":mode,"status":'PASSED',
                         "scene_id": episode["scene_id"],
                         "split": episode.get("split"),
                         "journal_sha256": entry["journal_sha256"],
                         "verifier_sha256": entry["verifier_sha256"],
                         **{key: entry[key] for key in ("content_path", "content_sha256")
                            if isinstance(entry.get(key), str)}})
    return tuple(resolved)


BUNDLE_KEYS = frozenset({"schema_version", "kind", "model_source", "dataset_sha256", "config_sha256",
                         "policy_path", "policy_sha256", "normalization", "action"})
# the runner applies the frozen prefix and de-normalises with the frozen statistics, so a bundle that did
# not carry them would leave both to be guessed at run time
_ACTION_KEYS = frozenset({"chunk_size", "execution_prefix", "temporal_ensembling", "tail_padding_mask"})


def _bundle_digest(value, code: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(code)
    return value


def load_bundle(path) -> dict:
    """Load a bundle document and confirm the policy it names is the policy it carries.

    A bundle is the only thing a runner is allowed to trust, so the document has to be closed, its policy
    has to live inside the bundle directory, and its digest has to match the bytes on disk. The
    normalisation provenance is checked too: statistics computed from anything but the train split would
    silently invalidate every later evaluation.
    """

    import hashlib

    target = Path(path)
    if not target.is_file() or target.is_symlink():
        raise ValueError("BUNDLE_MISSING")
    try:
        document = json.loads(target.read_bytes())
    except ValueError as error:
        raise ValueError("BUNDLE_INVALID") from error
    if (not isinstance(document, dict) or set(document) != BUNDLE_KEYS
            or document["schema_version"] != 1 or document["kind"] != "act_bundle"):
        raise ValueError("BUNDLE_INVALID")
    model_source = document["model_source"]
    if (not isinstance(model_source, dict) or set(model_source) != {"name", "sha256"}
            or not isinstance(model_source["name"], str) or not model_source["name"]):
        raise ValueError("BUNDLE_INVALID")
    _bundle_digest(model_source["sha256"], "BUNDLE_INVALID")
    _bundle_digest(document["dataset_sha256"], "BUNDLE_INVALID")
    _bundle_digest(document["config_sha256"], "BUNDLE_INVALID")
    normalization = document["normalization"]
    if not isinstance(normalization, dict) or normalization.get("split") != "train":
        raise ValueError("BUNDLE_NORMALIZATION_NOT_TRAIN_ONLY")
    action = document["action"]
    if not isinstance(action, dict) or set(action) != _ACTION_KEYS:
        raise ValueError("BUNDLE_INVALID")
    if type(action["execution_prefix"]) is not int or action["execution_prefix"] < 1:
        raise ValueError("BUNDLE_INVALID")
    if action["temporal_ensembling"] is not False or type(action["chunk_size"]) is not int:
        raise ValueError("BUNDLE_INVALID")
    policy_name = document["policy_path"]
    if (not isinstance(policy_name, str) or not policy_name or policy_name.startswith("/")
            or ".." in Path(policy_name).parts):
        raise ValueError("BUNDLE_POLICY_PATH_INVALID")
    policy = target.parent / policy_name
    if not policy.is_file() or policy.is_symlink():
        raise ValueError("BUNDLE_POLICY_MISSING")
    if hashlib.sha256(policy.read_bytes()).hexdigest() != document["policy_sha256"]:
        raise ValueError("BUNDLE_POLICY_DIGEST_MISMATCH")
    return document


def require_policy_interface(model) -> object:
    """A policy must offer `infer(observation) -> tuple[tuple[float, ...], ...]` and `reset()`."""

    if not callable(getattr(model, "infer", None)) or not callable(getattr(model, "reset", None)):
        raise ValueError("POLICY_INTERFACE_INVALID")
    return model


def load_policy(bundle_path, *, loader) -> object:
    """Load the policy a bundle names through an injected loader — never by import path."""

    bundle = load_bundle(bundle_path)
    if not callable(loader):
        raise ValueError("POLICY_LOADER_REQUIRED")
    return require_policy_interface(loader(bundle))


EXPORT_KEYS = frozenset({"schema_version", "kind", "episodes", "scene_count",
                         "source_manifest_sha256", "campaign_index_sha256"})
_STALE_DATASET_IDS = ("0917a",)
_COLLECTION_SPLITS = ("train", "validation", "offline_test")
_NEWLINE = bytes((10,))


def export_dataset(committed, output, *, source_manifest_sha256: str,
                   campaign_index_sha256: str) -> dict:
    """Write the immutable export: one document per committed episode plus a digest manifest.

    The export is written once. An existing output directory is a refusal rather than a place to append,
    because a dataset that grows underneath a training run invalidates every metric computed from it. The
    episode order is the order the caller resolved -- the frozen manifest order -- and each episode's bytes
    are hashed into the manifest so a later edit is detectable.
    """

    from .qc_session import assert_export_path_allowed

    assert_export_path_allowed()
    _bundle_digest(source_manifest_sha256, "EXPORT_SOURCE_DIGEST_INVALID")
    _bundle_digest(campaign_index_sha256, "EXPORT_INDEX_DIGEST_INVALID")
    if not isinstance(committed, (list, tuple)):
        raise ValueError("EXPORT_EPISODES_INVALID")
    episodes = list(committed)
    if not episodes:
        raise ValueError("EXPORT_EMPTY")
    target = Path(output)
    partial = target.with_name(target.name + ".partial")
    if target.exists() or target.is_symlink() or partial.exists() or partial.is_symlink():
        raise ValueError("EXPORT_OUTPUT_EXISTS")

    records, seen = [], set()
    for episode in episodes:
        if not isinstance(episode, dict) or not isinstance(episode.get("scene_id"), str):
            raise ValueError("EXPORT_EPISODES_INVALID")
        scene_id = episode["scene_id"]
        if not _SCENE_ID.fullmatch(scene_id):
            # the scene id becomes a directory name inside the export
            raise ValueError("EXPORT_EPISODES_INVALID")
        if scene_id in seen:
            raise ValueError("EXPORT_DUPLICATE_SCENE")
        seen.add(scene_id)
        split = episode.get("split")
        if split is not None and split not in _COLLECTION_SPLITS:
            raise ValueError("EXPORT_SPLIT_FORBIDDEN")
        if any(stale in scene_id or stale in str(episode.get("dataset_id", ""))
               for stale in _STALE_DATASET_IDS):
            raise ValueError("EXPORT_STALE_DATASET_ID")
        proof = None
        if episode.get('kind')=='ACT_COMMITTED_EPISODE':
            _, proof = _verified_collection(episode)
        if episode.get("status", "PASSED") != "PASSED":
            raise ValueError("EXPORT_EPISODE_NOT_PASSED")
        content = episode.get("content")
        if not isinstance(content, dict) or not content:
            raise ValueError("EXPORT_EPISODE_CONTENT_MISSING")
        content = training_content(content)
        if proof is None:
            _, proof = _verified_collection(episode)
        _check_dimensions(content)
        # the frames are bound by the seal the commit proof named, never by anything the caller passed in
        root, seal = sealed_episode(episode['collection_evidence'], proof)
        plan = _frame_plan(scene_id, content, seal['files'])
        for name, _, digest in plan:
            if _file_sha256(root / name, 'EXPORT_EPISODE_FRAME_MISSING') != digest:
                raise ValueError("EXPORT_EPISODE_FRAME_DIGEST_MISMATCH")
        relative = {name: destination for name, destination, _ in plan}
        content = _with_frame_paths(content, relative)
        payload = json.dumps(content, sort_keys=True, indent=2).encode() + _NEWLINE
        records.append({"scene_id": scene_id, "split": split,
                        "content_sha256": hashlib.sha256(payload).hexdigest(),
                        "payload": payload, "root": root,
                        "frames": {destination: (name, digest) for name, destination, digest in plan}})

    try:
        _write_export(partial, records, source_manifest_sha256, campaign_index_sha256)
        partial.rename(target)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)       # our own half-written export, never a finished one
        raise
    manifest_path = target / "export-manifest.json"
    document = json.loads(manifest_path.read_bytes())
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return {**document, "manifest_path": str(manifest_path), "export_sha256": digest}


def _file_sha256(path, missing):
    """Streaming sha256 of a regular, non-symlink file; ``missing`` is the refusal for anything else."""
    import os
    import stat
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError(missing)
            digest = hashlib.sha256()
            for block in iter(lambda: stream.read(1 << 20), b""):
                digest.update(block)
            return digest.hexdigest()
    except OSError as error:
        raise ValueError(missing) from error


def _with_frame_paths(content, relative):
    """The content with every frame name replaced by its dataset-relative path."""
    def observation(item):
        return {key: (relative[value] if key in ('head_png', 'wrist_png') else value) for key, value in item.items()}
    rewritten = dict(content)
    if 'rows' in content:
        rewritten['rows'] = [{'observation': observation(row['observation']), 'action': row['action']} for row in content['rows']]
    else:
        rewritten['observation'] = observation(content['observation'])
    return rewritten


def _write_export(target, records, source_manifest_sha256, campaign_index_sha256):
    import os

    target.mkdir(parents=True)
    episodes_dir = target / "episodes"
    episodes_dir.mkdir()
    manifest_episodes = []
    for record in records:
        path = episodes_dir / (record["scene_id"] + ".json")
        temporary = path.with_name(path.name + ".partial")
        with open(temporary, "wb") as handle:
            handle.write(record["payload"])
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        (episodes_dir / record["scene_id"] / "frames").mkdir(parents=True)
        for destination, (name, digest) in record["frames"].items():
            # read once: the bytes that are hashed are the bytes that are written
            fd = os.open(record["root"] / name, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                data = stream.read()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError("EXPORT_EPISODE_FRAME_DIGEST_MISMATCH")
            with open(target / destination, "xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        manifest_episodes.append({"scene_id": record["scene_id"], "split": record["split"],
                                  "content_sha256": record["content_sha256"],
                                  "frames": {destination: digest for destination, (_, digest) in sorted(record["frames"].items())}})
    document = {"schema_version": 1, "kind": "act_dataset_export", "scene_count": len(records),
                "source_manifest_sha256": source_manifest_sha256,
                "campaign_index_sha256": campaign_index_sha256, "episodes": manifest_episodes}
    manifest_path = target / "export-manifest.json"
    with open(manifest_path, "w") as handle:
        handle.write(json.dumps(document, sort_keys=True, indent=2) + chr(10))
        handle.flush()
        os.fsync(handle.fileno())
