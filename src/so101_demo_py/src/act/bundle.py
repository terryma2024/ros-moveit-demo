"""Decide which episodes a training bundle may contain.

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
_TASK_EVIDENCE_KEYS=frozenset({'registration','owner_root','task_id','result_location','scope_path','inputs_manifest'})
_PROCESSED_EVIDENCE_KEYS=_TASK_EVIDENCE_KEYS|{'processing_output'}
_PROCESSED_DATA_FIELDS=('act_data_status','act_data_reason','act_data_qc','export_eligible','episode_seal_sha256','qc_report_sha256',
    'inputs_sha256','scope_sha256','audit_manifest_sha256','collection_mode')
_FROZEN_INDEX_KIND='act_collection_frozen_index'


def _verify_collection_for_export(episode, trust_memo=False):
    """The collection mode of a committed episode that may be exported (see `_verified_collection`)."""
    return _verified_collection(episode, trust_memo)[0]


_WORKERS_ENV = 'SO101_ACT_EXPORT_WORKERS'
#: 'spawn' keeps the workers free of the parent's threads; the tests switch it to 'fork' so that their in-process seams reach the workers
_POOL_START_METHOD = 'spawn'
#: the episode fields `_verified_collection` reads; the memo key is their canonical JSON (never `content`, `split` or `status`).
#: `collection_mode` is read too, but resolve adds it after the first verification: a hit compares it with the remembered mode instead.
_MEMO_KEY_FIELDS = ('kind', 'schema_version', 'scene_id', 'journal_sha256', 'verifier_sha256', 'task_result_sha256',
                    'processed_result_sha256', 'collection_evidence')
_VERIFICATION_MEMO: dict = {}


def resolve_workers(workers=None, *, default=1) -> int:
    """The worker count: the argument, else `SO101_ACT_EXPORT_WORKERS`, else ``default``. 1 is the serial path."""
    import os
    value = workers
    if value is None:
        raw = os.environ.get(_WORKERS_ENV, '').strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError as error:
            raise ValueError('EXPORT_WORKERS_INVALID') from error
    if type(value) is not int or value < 1:
        raise ValueError('EXPORT_WORKERS_INVALID')
    return value


def default_cli_workers() -> int:
    import os
    return max(1, min(8, os.cpu_count() or 1))


def clear_verification_memo() -> None:
    """Forget every remembered collection verification (the tests; a long-lived process after its evidence is rewritten)."""
    _VERIFICATION_MEMO.clear()


def _memo_enabled() -> bool:
    # an open readback session shares one QC recomputation between its calls; its calls are decided afresh and never memoised here
    from .qc_session import active
    return active() is None


def _memo_key(episode):
    if not isinstance(episode, dict):
        return None
    try:
        return json.dumps({name: episode[name] for name in _MEMO_KEY_FIELDS if name in episode}, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        return None


def _evidence_signature(episode) -> tuple:
    """Signatures (path, size, inode, mtime_ns) of the files and trees a verification of this episode reads: the scope, the inputs
    manifest, the registration and its journal directory, the task output, the sealed result and the phase-2 output directory."""
    from .qc_session import file_signature, tree_signature
    evidence = episode.get('collection_evidence')
    if not isinstance(evidence, dict):
        return ()
    files = [evidence.get(name) for name in ('scope_path', 'inputs_manifest', 'registration')]
    trees = [evidence.get(name) for name in ('result_location', 'processing_output', 'coordinator_root')]
    if isinstance(evidence.get('registration'), str):
        trees.append(str(Path(evidence['registration']).parent))
    if isinstance(evidence.get('owner_root'), str) and isinstance(evidence.get('task_id'), str):
        try:
            from so101_demo.runtime.container_campaign.paths import host_task_output
            trees.append(str(host_task_output(evidence['owner_root'], evidence['task_id'])))
        except Exception:                                  # noqa: BLE001 - the verification itself refuses a bad locator
            pass
    return (tuple(file_signature(path) for path in files if isinstance(path, str)),
            tuple(tree_signature(path) for path in trees if isinstance(path, str)))


def _memo_lookup(episode, trust_memo=False):
    """A deep copy of the remembered (mode, proof), or None: a changed file or an unknown identity is a miss.

    A pass that trusted the QC memo never answers a caller that did not ask to trust it; a full recomputation answers both."""
    import copy
    key = _memo_key(episode)
    if key is None or not _memo_enabled():
        return None
    held = _VERIFICATION_MEMO.get(key)
    if held is None:
        return None
    if held[3] and not trust_memo:
        return None
    if 'collection_mode' in episode and episode['collection_mode'] != held[0]:
        return None                                    # the verification itself refuses it
    if _evidence_signature(episode) != held[2]:
        _VERIFICATION_MEMO.pop(key, None)
        return None
    return copy.deepcopy((held[0], held[1]))


def _memo_store(key, mode, proof, signature, trusted=False) -> None:
    import copy
    if key is not None and _memo_enabled():
        _VERIFICATION_MEMO[key] = (mode, copy.deepcopy(proof), signature, bool(trusted))


def _verified_collection(episode, trust_memo=False):
    """(mode, commit proof) of a committed episode that may be exported; see `_verified_collection_uncached`.

    ``trust_memo`` lets a schema 4 episode's data grading accept the offline processor's content-bound QC memo where the memo covers
    exactly the files on disk now (`qc_memo.memo_matches`); otherwise the QC is recomputed in full. Only the callers a human approved
    pass it (export, the pre-training re-checks); the default recomputes.

    The only thing remembered is the result of that function, computed in this process or by `_verify_in_worker` (our own code),
    together with the signature of every file the verification reads: a hit re-checks the signature and any difference verifies
    again. The memo is filled here and by the pool only; no argument, episode field or proof a caller holds can enter it. A
    failure is never remembered."""
    hit = _memo_lookup(episode, trust_memo)
    if hit is not None:
        return hit
    key = _memo_key(episode) if _memo_enabled() else None
    before = _evidence_signature(episode) if key is not None else None
    mode, proof = _verified_collection_uncached(episode, trust_memo)
    if key is not None and _evidence_signature(episode) == before:
        _memo_store(key, mode, proof, before, trust_memo)
    return mode, proof


def _verified_collection_uncached(episode, trust_memo=False):
    """(mode, commit proof) of a committed episode that may be exported. Trace retained originals on every call; caller flags and cached proofs grant no eligibility.

    A readback entry point may hold a session that shares one QC *recomputation* between its calls (a computation, not a proof): the
    commit proof, the mode, the result status, the QC verdict and `export_eligible` are read and decided here afresh each time."""
    from .collection_scope import read_collection_scope
    from .result_store import verify_coordinator_commit,_safe
    evidence=episode.get('collection_evidence')
    if episode.get('kind')=='ACT_COMMITTED_EPISODE' and episode.get('schema_version')==3:
        return _verified_container_collection(episode)
    if episode.get('kind')=='ACT_COMMITTED_EPISODE' and episode.get('schema_version')==4:
        return _verified_processed_collection(episode, trust_memo)
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
    return _export_gates(scope,proof,evidence)


def _verified_container_collection(episode):
    """(mode, readback proof) of a schema 3 episode from the frozen index: the registered container task is read back afresh."""
    from .collection_scope import read_collection_scope
    from .result_store import verify_container_task_registration,_safe
    evidence=episode.get('collection_evidence')
    if type(evidence) is not dict or set(evidence)!=_TASK_EVIDENCE_KEYS:
        raise ValueError('EPISODE_COLLECTION_EVIDENCE_REQUIRED')
    if any(not isinstance(episode.get(key),str) or _SHA256_HEX.fullmatch(episode[key]) is None
           for key in ('verifier_sha256','task_result_sha256')):
        raise ValueError('EPISODE_RECEIPT_INVALID')
    try:
        paths={key:_safe(Path(evidence[key])) for key in _TASK_EVIDENCE_KEYS-{'task_id'}}
        scope=read_collection_scope(paths['scope_path'])
        proof=verify_container_task_registration(paths['registration'],scope=paths['scope_path'],
            inputs_manifest=paths['inputs_manifest'])
        if (proof['task_id']!=evidence['task_id'] or paths['registration'].name!='collected.json'
                or Path(proof['location'])!=paths['result_location']
                or not paths['result_location'].is_relative_to(paths['owner_root'])):
            raise ValueError('registration locator')
    except (OSError,ValueError,TypeError,KeyError) as error:
        raise ValueError('EPISODE_COLLECTION_IDENTITY_INVALID') from error
    if (episode.get('verifier_sha256')!=proof['result_sha256'] or episode.get('task_result_sha256')!=proof['task_result_sha256']):
        raise ValueError('EPISODE_RECEIPT_CONFLICT')
    if (episode['scene_id']!=scope['scene_id'] or proof['scene_id']!=scope['scene_id'] or proof['collection_mode']!=scope['mode']
            or ('collection_mode' in episode and episode['collection_mode']!=scope['mode'])):
        raise ValueError('EPISODE_COLLECTION_IDENTITY_INVALID')
    return _export_gates(scope,proof,evidence)


_DETAIL_CHARS = 300
_ORACLE_REASON = re.compile(r'TEACHER_ORACLE_EXCLUDED: (\S+ \S+)')


def _identity_refusal(error) -> str:
    """The refusal text of a schema 4 readback that failed: `EPISODE_COLLECTION_IDENTITY_INVALID` (the code every caller matches), then
    the cause found in the exception chain. A Teacher oracle that the export rule excludes (the phase-2 regrade says
    `TEACHER_ORACLE_EXCLUDED: <flag> <phase>`) is named with the export code `EXPORT_EPISODE_ORACLE_EXCLUDED`, as the export gate does."""
    messages, cursor = [], error
    while cursor is not None and len(messages) < 8:
        messages.append(str(cursor) or type(cursor).__name__)
        cursor = cursor.__cause__
    for message in messages:
        found = _ORACLE_REASON.search(message)
        if found:
            return f'EPISODE_COLLECTION_IDENTITY_INVALID: EXPORT_EPISODE_ORACLE_EXCLUDED: {found.group(1)}'
    cause = next((message for message in reversed(messages) if message != 'EPISODE_COLLECTION_IDENTITY_INVALID'), None)
    return 'EPISODE_COLLECTION_IDENTITY_INVALID' + ('' if cause is None else ': ' + cause[:_DETAIL_CHARS])


def _verified_processed_collection(episode, trust_memo=False):
    """(mode, combined proof) of a schema 4 episode from the frozen index of a two-phase campaign.

    Both phases are read back afresh: the registered container task (the Teacher half, `PENDING` at phase 1) and the processed result
    in the phase-2 output directory, bound to that task's result and receipt hashes. The combined proof carries the Teacher fields of
    phase 1 and the data fields of phase 2, and passes the same export gates as a schema 3 proof."""
    from . import processed_result
    from .collection_scope import read_collection_scope
    from .result_store import verify_container_task_registration,_safe
    evidence=episode.get('collection_evidence')
    if type(evidence) is not dict or set(evidence)!=_PROCESSED_EVIDENCE_KEYS:
        raise ValueError('EPISODE_COLLECTION_EVIDENCE_REQUIRED')
    if any(not isinstance(episode.get(key),str) or _SHA256_HEX.fullmatch(episode[key]) is None
           for key in ('verifier_sha256','task_result_sha256','processed_result_sha256')):
        raise ValueError('EPISODE_RECEIPT_INVALID')
    try:
        paths={key:_safe(Path(evidence[key])) for key in _PROCESSED_EVIDENCE_KEYS-{'task_id'}}
        scope=read_collection_scope(paths['scope_path'])
        proof=verify_container_task_registration(paths['registration'],scope=paths['scope_path'],
            inputs_manifest=paths['inputs_manifest'])
        output=paths['processing_output']
        if (proof['task_id']!=evidence['task_id'] or paths['registration'].name!='collected.json'
                or Path(proof['location'])!=paths['result_location']
                or not paths['result_location'].is_relative_to(paths['owner_root'])
                or proof.get('processing')!='PENDING' or output.parent.name!=proof['scene_id']
                or output.parent.parent.name!='processing'):
            raise ValueError('registration locator')
        memo_trust={'trust_memo':True} if trust_memo else {}
        processed=processed_result.verify_processed_result(output,sealed=Path(proof['location']),scene_id=proof['scene_id'],
            result_sha256=proof['result_sha256'],receipt_sha256=proof['receipt_sha256'],scope=paths['scope_path'],
            inputs_manifest=paths['inputs_manifest'],**memo_trust)
        if (processed['status']!='PASS' or processed['output_dir']!=str(output) or processed['scene_id']!=proof['scene_id']
                or processed['phase1_result_sha256']!=proof['result_sha256'] or processed['diagnostic_fault']!='none'):
            raise ValueError('processed readback')
    except (OSError,ValueError,TypeError,KeyError) as error:
        raise ValueError(_identity_refusal(error)) from error
    if (episode.get('verifier_sha256')!=proof['result_sha256'] or episode.get('task_result_sha256')!=proof['task_result_sha256']
            or episode.get('processed_result_sha256')!=processed['processed_result']['sha256']):
        raise ValueError('EPISODE_RECEIPT_CONFLICT')
    combined=dict(proof,processing='PROCESSED',processed_result_sha256=episode['processed_result_sha256'],
        **{name:processed[name] for name in _PROCESSED_DATA_FIELDS})
    if (episode['scene_id']!=scope['scene_id'] or proof['scene_id']!=scope['scene_id'] or combined['collection_mode']!=scope['mode']
            or ('collection_mode' in episode and episode['collection_mode']!=scope['mode'])):
        raise ValueError('EPISODE_COLLECTION_IDENTITY_INVALID')
    return _export_gates(scope,combined,evidence)


def _export_gates(scope,proof,evidence):
    """Collection mode, result status, data QC and oracle exclusion: the gates every exportable episode passes."""
    if scope['mode']=='preselected_target_diagnostic':
        raise ValueError('DIAGNOSTIC_EPISODE_NOT_TRAINABLE')
    if scope['mode']!='formal':
        raise ValueError('EPISODE_COLLECTION_IDENTITY_INVALID')
    if proof['status']!='PASS' or proof.get('result_schema_version')!=3:
        # only a verified schema 3 result commit is exportable
        raise ValueError('EXPORT_EPISODE_RESULT_SCHEMA_INVALID')
    if proof['result_status']!='PASSED':
        raise ValueError('EXPORT_EPISODE_NOT_PASSED')
    if proof.get('processing')=='PENDING':
        # phase 1 only: the Teacher half is proven, the episode and the QC do not exist yet
        raise ValueError('EXPORT_EPISODE_PROCESSING_PENDING')
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
    from .result_store import _safe
    from .teacher_process import bound_teacher_oracle_exclusion
    try:
        location=_safe(Path(evidence['result_location']))
        # the QC report is phase 2's (schema 4), the Teacher manifest phase 1's
        data=_safe(Path(evidence['processing_output'])) if 'processing_output' in evidence else location
    except (OSError,ValueError,TypeError,KeyError) as error:
        raise ValueError('EXPORT_EPISODE_TEACHER_MANIFEST_UNREADABLE') from error
    # the one rule, shared with the phase-2 data verdict (`teacher_process.bound_teacher_oracle_exclusion`)
    return bound_teacher_oracle_exclusion(data/'qc-report.json',location/'dynamic'/'dynamic-execute-manifest.json')


def _make_pool(workers: int):
    import concurrent.futures
    import multiprocessing
    return concurrent.futures.ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context(_POOL_START_METHOD))


def _map_in_pool(function, arguments, workers):
    """``[function(a) for a in arguments]`` in a process pool, in argument order. ``function`` must not raise per item."""
    with _make_pool(min(workers, len(arguments))) as pool:
        futures = [pool.submit(function, argument) for argument in arguments]
        return [future.result() for future in futures]


def _verify_in_worker(task):
    """Worker body: (key, mode, proof, signature) of one verified episode, or None when it does not verify (or its files moved).

    A failure is not reported from here: the parent verifies that episode again at its own position in manifest order, so the
    exception type and message, and which of several failures is raised, are those of the serial path."""
    from .qc_session import assert_export_path_allowed
    assert_export_path_allowed()
    episode, trust_memo = task
    key = _memo_key(episode)
    if key is None:
        return None
    before = _evidence_signature(episode)
    try:
        mode, proof = _verified_collection_uncached(episode, trust_memo)
    except Exception:                                     # noqa: BLE001
        return None
    return (key, mode, proof, before, trust_memo) if _evidence_signature(episode) == before else None


def _prime_verification_memo(episodes, workers, trust_memo=False) -> None:
    """Verify, across a process pool, the episodes that have no valid memo entry, and remember the passes in this process.

    Never raises for an episode: the serial code that follows asks `_verified_collection` for each episode in manifest order,
    hits the memo for a pass and verifies a failure itself, so the first failure in manifest order is raised unchanged."""
    if workers <= 1 or not _memo_enabled():
        return
    pending, seen = [], set()
    for episode in episodes:
        key = _memo_key(episode)
        if key is None or key in seen or _memo_lookup(episode, trust_memo) is not None:
            continue
        seen.add(key)
        pending.append(({name: episode[name] for name in _MEMO_KEY_FIELDS if name in episode}, bool(trust_memo)))
    if len(pending) < 2:
        return
    for outcome in _map_in_pool(_verify_in_worker, pending, workers):
        if outcome is not None:
            _memo_store(*outcome)


def _verification_report_worker(task):
    """Worker body: (scene_id, None) when the episode verifies, else (scene_id, the refusal text). Always the uncached verification."""
    from .qc_session import assert_export_path_allowed
    assert_export_path_allowed()
    episode, trust_memo = task
    try:
        _verified_collection_uncached(episode, trust_memo)
    except Exception as error:                            # noqa: BLE001 - the report carries every refusal
        return (episode.get('scene_id'), str(error) or type(error).__name__)
    return (episode.get('scene_id'), None)


def verification_report(episodes, *, workers=None, trust_qc_memo=False) -> list:
    """``[(scene_id, None | refusal text)]`` in episode order: the committed-episode gate the post-run template runs, in parallel.

    Every episode goes through `_verified_collection_uncached` (never the memo), in a process pool of ``workers`` (argument, else
    `SO101_ACT_EXPORT_WORKERS`, else min(8, CPUs); 1 is the serial loop). The list equals the serial loop's, a failing episode is
    reported with its own refusal and the others are still verified."""
    from .qc_session import assert_export_path_allowed
    assert_export_path_allowed()
    workers = resolve_workers(workers, default=default_cli_workers())
    tasks = [(dict(episode), bool(trust_qc_memo)) for episode in episodes]
    if workers > 1 and len(tasks) > 1:
        return _map_in_pool(_verification_report_worker, tasks, workers)
    return [_verification_report_worker(task) for task in tasks]


def _frame_failure(task):
    """Worker body: the refusal code for the first frame of (root, [(name, digest)]) that is missing or differs, else None."""
    root, pairs = task
    for name, digest in pairs:
        try:
            if _file_sha256(Path(root) / name, 'EXPORT_EPISODE_FRAME_MISSING') != digest:
                return 'EXPORT_EPISODE_FRAME_DIGEST_MISMATCH'
        except ValueError as error:
            return str(error)
    return None


def _check_frames(jobs, workers) -> None:
    """Raise the frame refusal of the first episode (in order) whose frames are missing or differ from the seal digests."""
    if not jobs:
        return
    tasks = [(root, [(name, digest) for name, _, digest in plan]) for root, plan in jobs]
    if workers > 1 and len(tasks) > 1:
        failures = _map_in_pool(_frame_failure, tasks, workers)
    else:
        failures = (_frame_failure(task) for task in tasks)
    for failure in failures:
        if failure is not None:
            raise ValueError(failure)


_SCENE_ID=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*')
_FRAME_NAME=re.compile(r'frames/[0-9]{6}-([a-z][a-z0-9_]*)\.png')
_SHA256_HEX=re.compile(r'[0-9a-f]{64}')


def sealed_episode(evidence,proof):
    """(recorder directory, seal) of a committed episode, the seal being the very file the coordinator commit proof bound.

    The commit proof carries the sha256 of the sealed episode that the independent data QC verified end to end. Nothing in the
    recorder directory is trusted before that digest agrees: the rows and every frame are then bound by the seal `files` map."""
    from .result_store import _read_regular,_safe
    try:
        root=_safe(Path(evidence.get('processing_output') or evidence['result_location']))/'episode'
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


def sealed_episode_content(episode, trust_memo=False):
    """The training content of a committed episode, read from its sealed recorder rows (design 2026-10-10 section 3.2).

    The commit is re-verified, the seal is the one the commit bound, and `records.jsonl` must hash to the seal `files` entry. The
    whitelist (`training_content`) then drops the per-record audit and every non-whitelisted key."""
    from .qc_session import assert_export_path_allowed
    from .result_store import _read_regular
    assert_export_path_allowed()
    _,proof=_verified_collection(episode,trust_memo)
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
    return training_content({'frames':len(rows),'rows':rows},episode_rig(episode))


def episode_rig(episode):
    """The rig of a committed episode: the profile its frozen inputs bind, rig v1 for a set sealed before profiles existed.

    The episode's collection evidence names its frozen inputs manifest; the commit verification that precedes every caller has
    already proven that manifest, so it is only read here."""
    from .rig_profile import DEFAULT_RIG,rig_from_frozen
    evidence=episode.get('collection_evidence') if isinstance(episode,dict) else None
    try:
        document=json.loads(Path(evidence['inputs_manifest']).read_bytes())
    except (OSError,ValueError,TypeError,KeyError):
        return DEFAULT_RIG
    return rig_from_frozen(document) if isinstance(document,dict) else DEFAULT_RIG


def _content_observations(content):
    """The observations of a whitelisted content, in order."""
    if 'rows' in content:
        return [row['observation'] for row in content['rows']]
    return [content['observation']]


def _content_actions(content):
    if 'rows' in content:
        return [row['action'] for row in content['rows']]
    return [content['action']]


def _check_dimensions(content,rig=None):
    """The rig's state width (8 for rig v1) and action width 6 (act/training_config.py), refused at export rather than at the first training batch."""
    from .training_config import ACTION_DIM
    from .rig_profile import DEFAULT_RIG
    state_dim=(DEFAULT_RIG if rig is None else rig).state_dim
    observations=_content_observations(content)
    if not observations:
        raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
    if (any(len(observation.get('state',())) != state_dim for observation in observations)
            or any(len(action) != ACTION_DIM for action in _content_actions(content))):
        raise ValueError('EXPORT_EPISODE_DIMENSION_INVALID')


def _frame_plan(scene_id,content,files,rig=None):
    """[(source name, dataset-relative path, sha256)] for every frame the content references; refuses what the seal does not bind."""
    from .rig_profile import DEFAULT_RIG
    rig=DEFAULT_RIG if rig is None else rig
    plan=[]
    for observation in _content_observations(content):
        for camera in rig.camera_names:
            key=rig.frame_key(camera)
            name=observation.get(key)
            match=_FRAME_NAME.fullmatch(name) if isinstance(name,str) else None
            if match is None or match.group(1)!=camera or name not in files:
                raise ValueError('EXPORT_EPISODE_FRAME_MISSING')
            plan.append((name,f'episodes/{scene_id}/{name}',_seal_digest(files[name])))
    return plan


#: What a training sample may contain (user, 2026-10-10: collision and force data do not enter training): the observation (joint state,
#: head and wrist image) and the action. The per-record audit (contact lists, normal forces), the Teacher process summary, the
#: oracle flags and every other contact, force or collision field stay in the sealed episode and its metadata.
def _all_frame_keys():
    from .rig_profile import KNOWN_RIGS
    return tuple(dict.fromkeys(key for rig in KNOWN_RIGS.values() for key in rig.frame_keys))


#: the union over the known rigs (head_png, wrist_png, side_png): a reader that does not know the rig keeps the frame keys of
#: any of them; an exporter knows the rig of the episode and restricts the whitelist to its own (`training_content(content, rig)`).
TRAINING_OBSERVATION_KEYS=('sim_time_s','state',*_all_frame_keys())
TRAINING_CONTENT_KEYS=('frames','rows','state','observation','action')


def _numbers(value):
    import math
    if (not isinstance(value,(list,tuple)) or not value
            or any(isinstance(item,bool) or not isinstance(item,(int,float)) or not math.isfinite(item) for item in value)):
        raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
    return list(value)


def _training_observation(observation,rig=None):
    if not isinstance(observation,dict):
        raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
    kept={}
    for key in TRAINING_OBSERVATION_KEYS if rig is None else ('sim_time_s','state',*rig.frame_keys):
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


def training_content(content,rig=None) -> dict:
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
            kept[key]=_training_observation(value,rig)
        else:
            if not isinstance(value,list):
                raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
            rows=[]
            for row in value:
                if not isinstance(row,dict) or 'observation' not in row or 'action' not in row:
                    raise ValueError('EXPORT_EPISODE_CONTENT_INVALID')
                rows.append({'observation':_training_observation(row['observation'],rig),'action':_numbers(row['action'])})
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
        if entry.get('schema_version') in (3,4) and (document.get('kind')!=_FROZEN_INDEX_KIND or document.get('qualification') is not False):
            # container task episodes come only from a frozen, non-qualification campaign index
            raise ValueError('EPISODE_FROZEN_INDEX_REQUIRED')
        entries[entry['scene_id']]=entry
    return entries


def _committed_entry(episode, committed, campaign_index):
    """The index entry whose commit a manifest episode is verified against, or None when the episode is skipped."""
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
        return None                                    # a directory without a coordinator commit
    if episode.get('status')!='PASSED' and entry.get('kind')!='ACT_COMMITTED_EPISODE':
        return None                                    # archival business failures are retained
    return entry


def resolve_committed_episodes(*, manifest: dict, campaign_index, workers=None, trust_qc_memo=False) -> tuple:
    """Episodes the coordinator committed, with a verifier receipt that agrees with the journal.

    ``workers`` > 1 verifies the episodes across a process pool first (`_prime_verification_memo`); the loop below is the serial
    path in every case and decides the result, the order and the first refusal.

    ``trust_qc_memo`` (human-approved for the pre-training export, 2026-10-19) lets the data grading of a schema 4 episode accept the
    offline processor's content-bound QC memo where it covers exactly the files on disk now; any other case recomputes in full."""

    from .qc_session import assert_export_path_allowed

    assert_export_path_allowed()        # a cached proof grants no eligibility: only a readback entry point may hold a session here
    workers = resolve_workers(workers, default=default_cli_workers())
    if not isinstance(manifest, dict) or not isinstance(manifest.get("episodes"), list):
        raise ValueError("MANIFEST_INVALID")
    committed = _index(campaign_index)
    if workers > 1:
        entries = []
        for episode in manifest["episodes"]:
            try:
                entry = _committed_entry(episode, committed, campaign_index)
            except Exception:                          # noqa: BLE001 - the loop below raises it at its own position
                break
            if entry is not None:
                entries.append(entry)
        _prime_verification_memo(entries, workers, trust_qc_memo)
    resolved = []
    for episode in manifest["episodes"]:
        entry = _committed_entry(episode, committed, campaign_index)
        if entry is None:
            continue
        mode=_verify_collection_for_export(entry, trust_qc_memo)
        # carry the content locator through: a resolved episode that forgets where its content lives
        # forces the exporter to guess, and guessing is what this module exists to prevent
        if entry.get('schema_version')==4:
            resolved.append({"kind":'ACT_COMMITTED_EPISODE',"schema_version":4,
                             "collection_evidence":entry['collection_evidence'],"collection_mode":mode,"status":'PASSED',
                             "scene_id":episode["scene_id"],"split":episode.get("split"),
                             "task_result_sha256":entry["task_result_sha256"],"verifier_sha256":entry["verifier_sha256"],
                             "processed_result_sha256":entry["processed_result_sha256"],
                             **{key: entry[key] for key in ("content_path", "content_sha256")
                                if isinstance(entry.get(key), str)}})
            continue
        if entry.get('schema_version')==3:
            resolved.append({"kind":'ACT_COMMITTED_EPISODE',"schema_version":3,
                             "collection_evidence":entry['collection_evidence'],"collection_mode":mode,"status":'PASSED',
                             "scene_id":episode["scene_id"],"split":episode.get("split"),
                             "task_result_sha256":entry["task_result_sha256"],"verifier_sha256":entry["verifier_sha256"],
                             **{key: entry[key] for key in ("content_path", "content_sha256")
                                if isinstance(entry.get(key), str)}})
            continue
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
    if (not isinstance(model_source, dict) or set(model_source) not in ({"name", "sha256"}, {"name", "sha256", "source_commit"})
            or not isinstance(model_source["name"], str) or not model_source["name"]):
        raise ValueError("BUNDLE_INVALID")
    _bundle_digest(model_source["sha256"], "BUNDLE_INVALID")
    if "source_commit" in model_source and (not isinstance(model_source["source_commit"], str)
                                            or re.fullmatch(r"[0-9a-f]{40}", model_source["source_commit"]) is None):
        raise ValueError("BUNDLE_INVALID")
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
                   campaign_index_sha256: str, workers=None, trust_qc_memo=False) -> dict:
    """Write the immutable export: one document per committed episode plus a digest manifest.

    The export is written once. An existing output directory is a refusal rather than a place to append,
    because a dataset that grows underneath a training run invalidates every metric computed from it. The
    episode order is the order the caller resolved -- the frozen manifest order -- and each episode's bytes
    are hashed into the manifest so a later edit is detectable.

    ``workers`` > 1 verifies the commits and hashes the frames across a process pool. The loop stays the serial path: a commit
    verification is a memo hit after the pool, and the frame digests are checked after the loop (or after the refusal that stops
    it), episodes in order, so the first refusal in manifest order is the serial one.

    The frames are read once: the write threads hash the bytes they copy against the seal digest, and the first refusal in
    manifest order is raised (a separate frame check runs only when an episode record is refused, to keep that order).
    ``trust_qc_memo`` is `resolve_committed_episodes`'s.
    """

    from .qc_session import assert_export_path_allowed

    assert_export_path_allowed()
    workers = resolve_workers(workers, default=default_cli_workers())
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

    if workers > 1:
        _prime_verification_memo([episode for episode in episodes
                                  if isinstance(episode, dict) and episode.get('kind') == 'ACT_COMMITTED_EPISODE'], workers,
                                 trust_qc_memo)
    records, seen, frame_jobs = [], set(), []
    try:
        records = _export_records(episodes, seen, frame_jobs, trust_qc_memo)
    except Exception:
        # an earlier episode whose frames differ is the first refusal in manifest order
        _check_frames(frame_jobs, workers)
        raise

    try:
        _write_export(partial, records, source_manifest_sha256, campaign_index_sha256, workers)
        partial.rename(target)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)       # our own half-written export, never a finished one
        raise
    manifest_path = target / "export-manifest.json"
    document = json.loads(manifest_path.read_bytes())
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return {**document, "manifest_path": str(manifest_path), "export_sha256": digest}


def _manifest_episodes(records):
    """The per-episode entries of the export manifest. An episode that ran under a schema 6 Teacher policy also carries the diversity
    values it was applied (R3-a); every other episode has the entry it always had."""
    return [{"scene_id": record["scene_id"], "split": record["split"], "content_sha256": record["content_sha256"],
             "frames": {destination: digest for destination, (_, digest) in sorted(record["frames"].items())},
             **({"teacher_diversity": record["teacher_diversity"]} if record.get("teacher_diversity") is not None else {})}
            for record in records]


def episode_diversity_record(root, scene_id):
    """The diversity values applied to a sealed episode (R3-a): `teacher_diversity` of its audit identity (`audit/episode.json`, the file the
    data QC verified), or None for an episode without them. Values that name another scene are refused."""
    try:
        document = json.loads((Path(root) / "audit" / "episode.json").read_bytes())
    except (OSError, ValueError):
        return None
    values = document.get("teacher_diversity") if isinstance(document, dict) else None
    if values is None:
        return None
    if document.get("scene_id") != scene_id or not isinstance(values, dict) or values.get("scene_id") != scene_id:
        raise ValueError("EXPORT_EPISODE_DIVERSITY_UNBOUND")
    return values


def _export_records(episodes, seen, frame_jobs, trust_qc_memo=False):
    """The export records of every episode, in order; the frame checks of each go to ``frame_jobs`` for `_check_frames`."""
    records = []
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
            _, proof = _verified_collection(episode, trust_qc_memo)
        if episode.get("status", "PASSED") != "PASSED":
            raise ValueError("EXPORT_EPISODE_NOT_PASSED")
        content = episode.get("content")
        if not isinstance(content, dict) or not content:
            raise ValueError("EXPORT_EPISODE_CONTENT_MISSING")
        # the rig is the profile the verified episode's frozen inputs bind; an unverified one is refused just below
        rig = episode_rig(episode) if proof is not None else None
        content = training_content(content, rig)
        if proof is None:
            _, proof = _verified_collection(episode, trust_qc_memo)
            rig = episode_rig(episode)
        _check_dimensions(content, rig)
        # the frames are bound by the seal the commit proof named, never by anything the caller passed in
        root, seal = sealed_episode(episode['collection_evidence'], proof)
        plan = _frame_plan(scene_id, content, seal['files'], rig)
        frame_jobs.append((root, plan))
        relative = {name: destination for name, destination, _ in plan}
        content = _with_frame_paths(content, relative, rig)
        payload = json.dumps(content, sort_keys=True, indent=2).encode() + _NEWLINE
        records.append({"scene_id": scene_id, "split": split,
                        "content_sha256": hashlib.sha256(payload).hexdigest(),
                        "payload": payload, "root": root, "teacher_diversity": episode_diversity_record(root, scene_id),
                        "frames": {destination: (name, digest) for name, destination, digest in plan}})
    return records


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


def _with_frame_paths(content, relative, rig=None):
    """The content with every frame name replaced by its dataset-relative path."""
    from .rig_profile import DEFAULT_RIG
    frame_keys = (DEFAULT_RIG if rig is None else rig).frame_keys

    def observation(item):
        return {key: (relative[value] if key in frame_keys else value) for key, value in item.items()}
    rewritten = dict(content)
    if 'rows' in content:
        rewritten['rows'] = [{'observation': observation(row['observation']), 'action': row['action']} for row in content['rows']]
    else:
        rewritten['observation'] = observation(content['observation'])
    return rewritten


def _syncfs(path) -> bool:
    """``syncfs(2)`` on the filesystem that holds ``path``; False when this platform has none (the caller then fsyncs each file)."""
    import ctypes
    import os
    try:
        call = ctypes.CDLL(None, use_errno=True).syncfs
    except (AttributeError, OSError):
        return False
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        if call(descriptor) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(path))
    finally:
        os.close(descriptor)
    return True


def _read_frame(path, digest):
    """The bytes of a regular, non-symlink frame whose sha256 is ``digest``; the refusals are `_file_sha256`'s."""
    import os
    import stat
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("EXPORT_EPISODE_FRAME_MISSING")
            data = stream.read()
    except OSError as error:
        raise ValueError("EXPORT_EPISODE_FRAME_MISSING") from error
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("EXPORT_EPISODE_FRAME_DIGEST_MISMATCH")
    return data


def _write_episode(target, episodes_dir, record, fsync_each) -> None:
    """One episode's document and frames. Each frame is read once: the bytes that are hashed are the bytes that are written."""
    import os

    def durable(handle):
        handle.flush()
        if fsync_each:
            os.fsync(handle.fileno())

    path = episodes_dir / (record["scene_id"] + ".json")
    temporary = path.with_name(path.name + ".partial")
    with open(temporary, "wb") as handle:
        handle.write(record["payload"])
        durable(handle)
    temporary.replace(path)
    (episodes_dir / record["scene_id"] / "frames").mkdir(parents=True)
    for destination, (name, digest) in record["frames"].items():
        data = _read_frame(record["root"] / name, digest)
        with open(target / destination, "xb") as handle:
            handle.write(data)
            durable(handle)


def _write_export(target, records, source_manifest_sha256, campaign_index_sha256, workers=1):
    """Write the export tree into ``target`` (the ``.partial`` directory), then make it durable.

    The episodes are written by ``workers`` threads (file reads, writes and sha256 release the GIL). Nothing is fsynced per file where
    ``syncfs`` exists: one ``syncfs`` of the filesystem before the caller renames ``.partial`` into place gives the same guarantee,
    because the final name appears only after every byte is on disk. Elsewhere each file is fsynced as before. The first refusal in
    record order is raised, whichever thread met a refusal first."""
    import concurrent.futures
    import os
    import platform

    fsync_each = platform.system() != "Linux"
    target.mkdir(parents=True)
    episodes_dir = target / "episodes"
    episodes_dir.mkdir()
    if workers > 1 and len(records) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, len(records))) as pool:
            futures = [pool.submit(_write_episode, target, episodes_dir, record, fsync_each) for record in records]
            for future in futures:
                future.result()
    else:
        for record in records:
            _write_episode(target, episodes_dir, record, fsync_each)
    manifest_episodes = _manifest_episodes(records)
    document = {"schema_version": 1, "kind": "act_dataset_export", "scene_count": len(records),
                "source_manifest_sha256": source_manifest_sha256,
                "campaign_index_sha256": campaign_index_sha256, "episodes": manifest_episodes}
    manifest_path = target / "export-manifest.json"
    with open(manifest_path, "w") as handle:
        handle.write(json.dumps(document, sort_keys=True, indent=2) + chr(10))
        handle.flush()
        if fsync_each:
            os.fsync(handle.fileno())
    if not fsync_each and not _syncfs(target):
        os.sync()                       # no syncfs(2) in this libc: the global sync is stronger and as late
