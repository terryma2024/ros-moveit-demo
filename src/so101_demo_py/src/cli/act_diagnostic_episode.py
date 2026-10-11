"""Inspect approved candidates, freeze and preflight inputs, collect one non-Head episode,
and independently read its original native QC, Coordinator commit and diagnostic export refusal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

from so101_demo.act.endpoint_pose_acceptance import load_development_runtime
from so101_demo.act.diagnostic_episode_inputs import (
    freeze_inputs, inspect_inputs, read_inputs_manifest, verify_frozen_inputs,
)

MODES = ("formal", "preselected_target_diagnostic")


class _Parser(argparse.ArgumentParser):
    """The house parser: a refused argument is rc 2, never a traceback."""

    def error(self, message):                                        # noqa: D102 - argparse contract
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="act_diagnostic_episode", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", help="discover approved input candidates without selecting by recency")
    inspect.add_argument("--source-root", required=True)
    inspect.add_argument("--ledger", required=True)
    inspect.add_argument("--output", required=True)

    prepare = subparsers.add_parser("prepare", help="freeze a candidate registry into immutable inputs")
    prepare.add_argument("--candidates", required=True)
    prepare.add_argument("--mode", default="formal", choices=MODES)
    prepare.add_argument("--teacher-endpoint", required=True,
                         help="teacher_endpoint policy file, frozen with its sha256 and full effective values")
    prepare.add_argument("--teacher-execution-policy", required=True,
                         help="teacher_execution_policy file (tilt-compensated place height), frozen with its sha256 and full effective values")
    prepare.add_argument("--episode-recorder-policy", required=True,
                         help="episode_recorder file, frozen with its sha256 and full effective values")
    prepare.add_argument("--runtime-policy", required=True)
    prepare.add_argument("--output", required=True)

    run = subparsers.add_parser("run", help="execute one non-Head episode from a frozen input set")
    run.add_argument("--inputs", required=True)
    run.add_argument("--root", required=True)
    run.add_argument("--mode", default="preselected_target_diagnostic", choices=MODES)
    run.add_argument("--lifecycle", default="FULL_RESTART",
                     choices=("FULL_RESTART", "REUSE_STACK", "RESET_WORLD"))
    # the final cup target the endpoint rule compares against: it is the scenario's frozen quantity, and this CLI
    # refuses rather than inventing one, because an invented target would make every later PASS meaningless
    run.add_argument("--collection", default="on", choices=("on", "off"),
                     help="on: a record-only `ros2 bag record` process records the run (raw/bag) and the offline processor builds "
                          "the episode from it after the Teacher ended; off: no recorder, no processing, no QC")
    run.add_argument("--raw-pilot", default=None, choices=("on", "off"),
                     help="retired: the bag recorder is the only data path. `on` is accepted and does nothing; `off` "
                          "with --collection on is refused")
    run.add_argument("--collection-fault", default="none",
                     choices=("none", "recorder_absent", "recorder_late", "queue_overflow", "source_gap",
                              "output_write_failure"),
                     help="sandbox fault injection (preselected_target_diagnostic mode only, outputs under "
                          "<run>/fault-sandbox/)")
    run.add_argument("--teacher-inject-failure-at", default=None,
                     help="Diagnostic only (preselected_target_diagnostic mode, collection on, policy v3): inject one "
                          "Teacher execution failure at the execute boundary of this state (LIFT). Off by default; refused by name "
                          "otherwise. Recorded in <run>/injected-failure.json and run.log")
    run.add_argument("--final-cup-pose",
                     help="seven numbers: the frozen final cup pose as xyz plus an xyzw quaternion")

    preflight = subparsers.add_parser("preflight", help="re-read a frozen input set")
    preflight.add_argument("--inputs", required=True)
    preflight.add_argument("--mode", default="formal", choices=MODES)
    preflight.add_argument("--output", required=True)
    qc = subparsers.add_parser('qc', help='independently recompute sealed native episode QC without live ports')
    qc_source=qc.add_mutually_exclusive_group(required=True)
    qc_source.add_argument('--run')
    qc_source.add_argument('--episode')
    qc.add_argument('--scope')
    qc.add_argument('--inputs')
    qc.add_argument('--output', required=True)
    commit=subparsers.add_parser('verify-commit',help='re-read the actual Coordinator journal, index and QC-bound receipt')
    commit.add_argument('--run',required=True)
    commit.add_argument('--output',required=True)
    export=subparsers.add_parser('check-export',help='verify both common export boundaries refuse the committed diagnostic')
    export.add_argument('--run',required=True)
    export.add_argument('--output',required=True)
    readback=subparsers.add_parser('readback',help='one independent readback of a finished run: the QC recomputation once, then the '
        'commit proof and the diagnostic export refusals against it; writes qc.json, verify-commit.json, check-export.json and '
        'readback-receipt.json')
    readback.add_argument('--run',required=True)
    readback.add_argument('--output-dir',required=True)
    return parser


def _prepare(arguments) -> int:
    # the policies and runtime are parsed before the freeze so a bad document refuses before anything is written
    load_development_runtime(Path(arguments.runtime_policy))
    target = freeze_inputs(Path(arguments.candidates), Path(arguments.output), mode=arguments.mode,
                           teacher_endpoint=Path(arguments.teacher_endpoint),
                           teacher_execution_policy=Path(arguments.teacher_execution_policy),
                           episode_recorder_policy=Path(arguments.episode_recorder_policy),
                           runtime_policy=Path(arguments.runtime_policy), execution_inputs=True)
    print(target)
    return 0


def _preflight(arguments) -> int:
    inputs = Path(arguments.inputs)
    manifest_path = inputs / "inputs-manifest.json"
    try:
        manifest = verify_frozen_inputs(manifest_path)
        if manifest.get("mode") != arguments.mode:
            raise ValueError("INPUT_MODE_MISMATCH")
    except (OSError, ValueError) as error:
        print(f"act_diagnostic_episode: {error}", file=sys.stderr)
        return 2
    report = {
        "mode": arguments.mode,
        "inputs_sha256": manifest["inputs_sha256"],
        "teacher_endpoint": manifest.get("teacher_endpoint"),
        "teacher_execution_policy": manifest.get("teacher_execution_policy"),
        "episode_recorder": manifest.get("episode_recorder"),
        "runtime_policy": manifest.get("runtime_policy"),
        "roles": sorted(manifest["roles"]),
        "prepared_mode": manifest.get("mode"),
    }
    Path(arguments.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(arguments.output)
    return 0


def _qc(arguments) -> int:
    from ..act.episode_qc import recompute_native_qc, write_qc_report
    try:
        if arguments.run is not None:
            from ..act.result_store import resolve_native_run
            if arguments.scope is not None or arguments.inputs is not None:
                raise ValueError('QC_RUN_ORIGINAL_BINDINGS_REQUIRED')
            context=resolve_native_run(Path(arguments.run))
            root,scope,inputs_manifest=context['episode'],context['scope'],context['inputs_manifest']
        else:
            if arguments.scope is None or arguments.inputs is None:
                raise ValueError('QC_ORIGINAL_BINDINGS_REQUIRED')
            root,scope,inputs_manifest=Path(arguments.episode),Path(arguments.scope),Path(arguments.inputs)/'inputs-manifest.json'
        report = recompute_native_qc(root, scope=scope, inputs_manifest=inputs_manifest)
        digest = write_qc_report(report, Path(arguments.output))
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'act_diagnostic_episode: {error}', file=sys.stderr)
        return 4 if arguments.run is not None else 2
    print(json.dumps(dict(status=report['status'], output=arguments.output, sha256=digest), sort_keys=True))
    return 0 if report['status'] == 'PASS' else (3 if arguments.run is not None else 1)


def _verify_commit(arguments) -> int:
    from ..act.result_store import resolve_native_run,verify_coordinator_commit,write_commit_proof
    try:
        context=resolve_native_run(Path(arguments.run))
        proof=verify_coordinator_commit(context['coordinator_root'],location=context['location'],
            scope=context['scope'],inputs_manifest=context['inputs_manifest'])
        digest=write_commit_proof(proof,Path(arguments.output))
    except (OSError,ValueError,TypeError,KeyError) as error:
        print(f'act_diagnostic_episode: {error}',file=sys.stderr)
        return 3
    print(json.dumps(dict(status=proof['status'],output=arguments.output,sha256=digest),sort_keys=True))
    return 0


def _check_export(arguments) -> int:
    from ..act.result_store import resolve_native_run,verify_coordinator_commit,write_export_rejection_proof
    from ..act.collection_scope import read_collection_scope
    from ..act.bundle import resolve_committed_episodes,export_dataset
    try:
        context=resolve_native_run(Path(arguments.run))
        scope=read_collection_scope(context['scope'])
        if scope['mode']!='preselected_target_diagnostic':
            raise ValueError('DIAGNOSTIC_EXPORT_CHECK_MODE_REQUIRED')
        commit=verify_coordinator_commit(context['coordinator_root'],location=context['location'],
            scope=context['scope'],inputs_manifest=context['inputs_manifest'])
        index=context['coordinator_root']/'aggregate_results.json'
        entry=dict(kind='ACT_COMMITTED_EPISODE',schema_version=2,scene_id=scope['scene_id'],split='train',
            status=commit['result_status'],journal_sha256=commit['commit_frame_sha256'],verifier_sha256=commit['result_sha256'],
            collection_evidence=dict(coordinator_root=str(context['coordinator_root']),result_location=str(context['location']),
                scope_path=str(context['scope']),inputs_manifest=str(context['inputs_manifest']),receipt=commit['receipt']))
        dataset=Path(arguments.output).with_name(Path(arguments.output).name+'.dataset')
        checks={}
        calls={'resolver':lambda:resolve_committed_episodes(manifest=dict(episodes=[entry]),campaign_index=index),
            'direct_export':lambda:export_dataset((entry,),dataset,source_manifest_sha256=scope['inputs_sha256'],
                campaign_index_sha256=hashlib.sha256(index.read_bytes()).hexdigest())}
        # A committed INVALID result that never produced a QC report has no episode a dataset entry could resolve to: when
        # the entry does resolve it must be refused; when it does not resolve there is nothing to refuse and the check does not apply.
        no_qc=_committed_invalid_without_qc(commit)
        for name,call in calls.items():
            try:call()
            except (OSError,ValueError,TypeError,KeyError) as error:
                if str(error)=='DIAGNOSTIC_EPISODE_NOT_TRAINABLE':
                    checks[name]=str(error)
                    continue
                if not no_qc:raise
                checks[name]='UNRESOLVABLE: '+str(error)[:200]
            else:raise ValueError('DIAGNOSTIC_EXPORT_UNEXPECTEDLY_ELIGIBLE')
        if dataset.exists() or dataset.is_symlink():raise ValueError('DIAGNOSTIC_EXPORT_DATASET_PRODUCED')
        if no_qc and not any(value=='DIAGNOSTIC_EPISODE_NOT_TRAINABLE' for value in checks.values()):
            arguments.not_applicable_reason='COMMITTED_INVALID_WITHOUT_QC: no dataset entry resolves ('+'; '.join(
                f'{name}: {value}' for name,value in sorted(checks.items()))+')'
            print(json.dumps(dict(status='NOT_APPLICABLE',reason=arguments.not_applicable_reason),sort_keys=True))
            return 0
        proof=dict(kind='ACT_DIAGNOSTIC_EXPORT_REJECTION',schema_version=1,status='PASS',checks=checks,
            identity=commit['identity'],result_status=commit['result_status'],collection_mode=scope['mode'],
            qc_report_sha256=commit['qc_report_sha256'],scope_sha256=commit['scope_sha256'],
            commit_frame_sha256=commit['commit_frame_sha256'],result_sha256=commit['result_sha256'],
            dataset_produced=False,perception_or_policy_models_loaded=False)
        digest=write_export_rejection_proof(proof,Path(arguments.output))
    except (OSError,ValueError,TypeError,KeyError) as error:
        print(f'act_diagnostic_episode: {error}',file=sys.stderr)
        return 3
    print(json.dumps(dict(status=proof['status'],output=arguments.output,sha256=digest),sort_keys=True))
    return 0


def _committed_invalid_without_qc(proof) -> bool:
    """The verified commit proof says the data is INVALID and no QC report was ever bound: there is nothing to recompute."""
    return (type(proof) is dict and proof.get('act_data_status')=='INVALID' and proof.get('act_data_qc')=='NOT_RUN'
            and proof.get('qc_report_sha256') is None)


_STAGES = {'qc': '_qc', 'verify-commit': '_verify_commit', 'check-export': '_check_export'}


def _readback_entry(arguments) -> int:
    """The entry points of an independent readback. Each one is a process that never trusts the QC memo (guarded: it refuses if the
    process holds memo state or built a memo-trusting gate, and any memo access raises), holds one session in which the QC is
    recomputed once and shared by its stages, and decides every stage from the files afresh."""
    from ..act import qc_memo
    from ..act.qc_session import qc_session

    command = arguments.command
    try:
        with qc_memo.readback_guard(), qc_session(owner=f'readback:{command}') as session:
            if command == 'readback':
                return _readback(arguments, session)
            return globals()[_STAGES[command]](arguments)
    except qc_memo.ReadbackMemoForbidden as error:
        print(f'act_diagnostic_episode: {error}', file=sys.stderr)
        return 4


# Exit codes. A stage keeps its standalone code; `readback` returns the first non-zero stage code in the order qc, verify-commit,
# check-export, and 4 when the stages passed but the receipt's own checks did not.
#   qc            0 PASS   3 FAIL verdict (report written, run mode)   4 error (run mode; 2 with --episode, 1 FAIL with --episode)
#   verify-commit 0 proof written   3 refused or error
#   check-export  0 both boundaries refused the diagnostic, proof written   3 refused, not diagnostic, or error
#   readback      the stage codes above; check-export is NOT_APPLICABLE (0) for a run that is not a diagnostic
READBACK_RECEIPT = 'readback-receipt.json'


def _readback(arguments, session) -> int:
    import types

    from ..act.result_store import resolve_native_run, write_readback_receipt

    out = Path(arguments.output_dir)
    try:
        out.mkdir(parents=True, exist_ok=False)
        context = resolve_native_run(Path(arguments.run))
        mode = _run_mode(context)
        episode = context['episode']
        session.watch = dict(episode_root=episode, scope=context['scope'], inputs_manifest=context['inputs_manifest'])
        _guard_inputs(session, 'begin')
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'act_diagnostic_episode: {error}', file=sys.stderr)
        return 4
    done = {}

    def run_stage(name, function):
        target = out / f'{name}.json'
        namespace = types.SimpleNamespace(command=name, run=arguments.run, episode=None, scope=None, inputs=None,
                                          output=str(target), not_applicable_reason=None)
        try:
            _guard_inputs(session, f'before {name}')
            rc = function(namespace)
            _guard_inputs(session, f'after {name}')
        except ValueError as error:
            print(f'act_diagnostic_episode: {error}', file=sys.stderr)
            rc, namespace.not_applicable_reason = 4, None
        if rc == 0 and namespace.not_applicable_reason and not target.is_file():
            return dict(status='NOT_APPLICABLE', rc=0, output=None, sha256=None, reason=namespace.not_applicable_reason)
        return dict(status='PASS' if rc == 0 else 'FAIL', rc=rc, output=target.name if target.is_file() else None,
                    sha256=hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None, reason=None)

    # The commit proof comes first: it says whether the data was ever graded. A committed INVALID result without a QC report has no
    # recomputation to make; every other result is recomputed exactly once, as before.
    done['verify-commit'] = run_stage('verify-commit', _verify_commit)
    proof = {}
    if done['verify-commit']['output']:
        proof = json.loads((out / done['verify-commit']['output']).read_bytes())
    if done['verify-commit']['rc'] == 0 and _committed_invalid_without_qc(proof):
        if (Path(context['location']) / 'qc-report.json').is_file():
            done['qc'] = dict(status='FAIL', rc=4, output=None, sha256=None,
                              reason='READBACK_QC_REPORT_UNEXPECTED: the commit proof binds none but the result holds one')
        else:
            done['qc'] = dict(status='NOT_APPLICABLE', rc=0, output=None, sha256=None,
                              reason='COMMITTED_INVALID_WITHOUT_QC: the commit proof binds no QC report (act_data_qc NOT_RUN, '
                                     'act_data_status INVALID), so there is nothing to recompute')
    else:
        done['qc'] = run_stage('qc', _qc)
    if mode != 'preselected_target_diagnostic':
        done['check-export'] = dict(status='NOT_APPLICABLE', rc=0, output=None, sha256=None,
            reason='DIAGNOSTIC_EXPORT_CHECK_MODE_REQUIRED: the export refusal check applies to diagnostic runs only')
    else:
        done['check-export'] = run_stage('check-export', _check_export)
    stages = {name: done[name] for name in ('qc', 'verify-commit', 'check-export')}
    receipt = _receipt(arguments, session, context, stages, mode)
    try:
        write_readback_receipt(receipt, out / READBACK_RECEIPT)
    except ValueError as error:
        print(f'act_diagnostic_episode: {error}', file=sys.stderr)
        return 4
    print(json.dumps(dict(status=receipt['status'], output=str(out / READBACK_RECEIPT), failures=receipt['failures']),
                     sort_keys=True))
    first = next((item['rc'] for item in stages.values() if item['rc'] != 0), 0)
    return first if first else (0 if receipt['status'] == 'PASS' else 4)


def _run_mode(context) -> str:
    from ..act.collection_scope import read_collection_scope

    return read_collection_scope(context['scope'])['mode']


def _guard_inputs(session, label) -> None:
    """The content fingerprint of everything the QC reads, hashed fresh; it must equal the one taken at the beginning."""
    from ..act import qc_memo

    watch = session.watch
    fingerprint = qc_memo.fingerprint(**watch, use_cache=False)
    if session.input_fingerprint is None:
        session.input_fingerprint = fingerprint
    elif fingerprint != session.input_fingerprint:
        raise ValueError(f'READBACK_INPUT_CHANGED ({label})')


def _receipt(arguments, session, context, stages, mode) -> dict:
    from ..act import qc_memo

    out = Path(arguments.output_dir)
    recomputations = session.computations.get('recompute_native_qc', 0)
    stored_path = Path(context['location']) / 'qc-report.json'
    applicable = stages['qc']['status'] != 'NOT_APPLICABLE'
    recomputed = stages['qc']['sha256']
    stored = hashlib.sha256(stored_path.read_bytes()).hexdigest() if stored_path.is_file() else None
    proof = {}
    if stages['verify-commit']['output']:
        proof = json.loads((out / stages['verify-commit']['output']).read_bytes())
    bound = proof.get('qc_report_sha256')
    failures = []
    # a QC FAIL (rc 3) is a verdict about the data, recorded as `qc_verdict`; the receipt fails only for a stage that did not complete
    if stages['qc']['rc'] not in (0, 3) or stages['verify-commit']['rc'] != 0 or stages['check-export']['rc'] != 0:
        failures.append('STAGE_FAILED')
    if applicable:
        if recomputations != 1 and stages['qc']['rc'] in (0, 3) and stages['verify-commit']['rc'] == 0:
            failures.append(f'READBACK_RECOMPUTE_COUNT: {recomputations}')
        if stages['qc']['output'] and stages['verify-commit']['output'] and not (recomputed == stored == bound):
            failures.append('READBACK_QC_DIGESTS_DISAGREE')
    else:
        # no recomputation is allowed only where the QC stage does not apply, and then none may have been made
        if recomputations != 0:
            failures.append(f'READBACK_RECOMPUTE_COUNT: {recomputations}')
        if not _committed_invalid_without_qc(proof) or stored is not None or bound is not None:
            failures.append('READBACK_QC_NOT_APPLICABLE_UNSUPPORTED')
    return dict(kind='ACT_READBACK_RECEIPT', schema_version=1, status='FAIL' if failures else 'PASS', failures=failures,
                run=str(arguments.run), collection_mode=mode, pid=os.getpid(), code_digest=qc_memo.code_digest(),
                input_fingerprint=session.input_fingerprint, journal_terminal_sha256=proof.get('journal_terminal_sha256'),
                qc_applicability='APPLICABLE' if applicable else 'NOT_APPLICABLE',
                qc_report_sha256=dict(recomputed=recomputed, stored=stored, commit_proof=bound,
                                      agree=bool(recomputed and recomputed == stored == bound)),
                qc_verdict=None if not stages['qc']['output'] else json.loads((out / stages['qc']['output']).read_bytes())['status'],
                qc_recomputations=recomputations, qc_reuse_hits=session.qc_hits, stages=stages)


def judge_readback_receipt(receipt, *, pid, live_root, expect) -> list:
    """The problems with an independent readback receipt, as the live wrapper judges it (empty when it is acceptable).

    `expect` is the data outcome the wrapper observed: "VALID" (the run exited 0) needs one QC recomputation whose three digests
    agree; "INVALID" (the Teacher passed, the data did not) accepts the same, or a receipt whose QC stage is NOT_APPLICABLE with no
    recomputation (a committed result that never produced a QC report). The commit proof is verified in both."""
    problems = []
    if type(receipt) is not dict:
        return ['receipt']
    if receipt.get('kind') != 'ACT_READBACK_RECEIPT' or receipt.get('schema_version') != 1:
        problems.append('kind')
    if receipt.get('pid') != pid:
        problems.append(f"pid {receipt.get('pid')} is not the readback process {pid}")
    if receipt.get('run') != live_root:
        problems.append('run')
    if receipt.get('status') != 'PASS' or receipt.get('failures'):
        problems.append(f"status {receipt.get('status')} {receipt.get('failures')}")
    stages = receipt.get('stages') or {}
    if receipt.get('qc_applicability') == 'NOT_APPLICABLE':
        if expect != 'INVALID':
            problems.append('qc not applicable for a VALID run')
        if receipt.get('qc_recomputations') != 0:
            problems.append(f"qc_recomputations {receipt.get('qc_recomputations')}")
        if stages.get('qc', {}).get('status') != 'NOT_APPLICABLE' or not stages.get('qc', {}).get('reason'):
            problems.append('qc stage')
    else:
        if receipt.get('qc_recomputations') != 1:
            problems.append(f"qc_recomputations {receipt.get('qc_recomputations')}")
        digests = receipt.get('qc_report_sha256') or {}
        if not (digests.get('agree') is True and digests.get('recomputed') == digests.get('stored') == digests.get('commit_proof')):
            problems.append('qc digests')
    if stages.get('verify-commit', {}).get('rc') != 0:
        problems.append('verify-commit')
    if stages.get('check-export', {}).get('status') not in ('PASS', 'NOT_APPLICABLE'):
        problems.append('check-export')
    if len(receipt.get('input_fingerprint') or '') != 64 or len(receipt.get('code_digest') or '') != 64:
        problems.append('fingerprint')
    return problems


#: the reason prefix a worker input refusal is committed under (worker.py, design 2026-10-10 section 1.2)
INPUT_REFUSAL_REASON_PREFIX = 'TEACHER_FENCED_BEFORE_MOTION:INPUT_UNAVAILABLE'


def _is_committed_input_refusal(proof) -> bool:
    """All of: the D8f Teacher pair, data INVALID with QC NOT_RUN and not exportable, and the INPUT_UNAVAILABLE reason prefix.
    (The cleanup verification has already passed when this is asked.) Anything else falls through to the existing exit codes."""
    receipt = proof.get('receipt')
    reason = receipt.get('act_data_reason') if isinstance(receipt, dict) else proof.get('act_data_reason')
    return (proof.get('teacher_execution_status') == 'INDETERMINATE' and proof.get('teacher_task_result') == 'UNCONFIRMED'
            and proof.get('act_data_status') == 'INVALID' and proof.get('act_data_qc') == 'NOT_RUN'
            and proof.get('export_eligible') is False
            and isinstance(reason, str) and reason.startswith(INPUT_REFUSAL_REASON_PREFIX))


def _verified_run_completion(run_root):
    """Return success only after original native QC, commit and cleanup readback."""
    from ..act.result_store import (resolve_native_run, verify_coordinator_commit,
                                   verify_coordinator_cleanup, write_commit_proof)
    try:
        context = resolve_native_run(Path(run_root))
        proof = verify_coordinator_commit(context['coordinator_root'],
            location=context['location'], scope=context['scope'],
            inputs_manifest=context['inputs_manifest'])
        cleanup = verify_coordinator_cleanup(context['coordinator_root'], commit_proof=proof)
        # The Teacher result and the data QC are reported separately: a Teacher success with failing data still
        # exits non-zero, and the report keeps the Teacher status so that is never read as a task failure.
        report = dict(teacher_result_status=proof['result_status'],
            teacher_task_result=proof.get('teacher_task_result'), act_data_qc=proof.get('act_data_qc'),
            export_eligible=proof['export_eligible'], result_location=str(context['location']))
        if _is_committed_input_refusal(proof):
            # exit 5 (design 2026-10-10 section 1.2): a worker input refusal before any motion, committed in the manifest-free D8f
            # form. Not a Teacher failure (rc 1) and not an unsealed run (rc 4); the commit proof is kept for the readback.
            receipt_path = Path(run_root) / 'commit-proof.json'
            digest = write_commit_proof(proof, receipt_path)
            report.update(receipt_path=str(receipt_path), receipt_sha256=digest,
                          cleanup_proof_path=cleanup['cleanup_proof_path'])
            return 5, dict(status='FAIL', reason='INPUT_UNAVAILABLE_BEFORE_MOTION', **report)
        if proof['result_status'] != 'PASSED':
            # exit 1: the Teacher itself did not pass; the data verdict stays in the report beside it
            return 1, dict(status='FAIL', reason='TEACHER_TASK_NOT_PASSED', **report)
        # A passed Teacher attempt keeps its verified commit proof even when its data failed QC.
        receipt_path = Path(run_root) / 'commit-proof.json'
        digest = write_commit_proof(proof, receipt_path)
        report.update(receipt_path=str(receipt_path), receipt_sha256=digest,
                      cleanup_proof_path=cleanup['cleanup_proof_path'])
        if proof.get('act_data_status') == 'DISABLED':
            # collection off: the Teacher passed and no data was asked for, so there is nothing to grade
            return 0, dict(status='PASS', **report)
        if proof.get('act_data_qc') != 'PASS':
            # exit 3: the Teacher passed but the data is INVALID or its independent QC did not pass. The gate reads the
            # QC verdict itself: export eligibility also needs a trainable mode, which a diagnostic run never has
            return 3, dict(status='FAIL', reason='ACT_DATA_QC_NOT_PASSED', **report)
        return 0, dict(status='PASS', **report)
    except (OSError, ValueError, TypeError, KeyError) as error:
        return 4, dict(status='FAIL', reason=str(error))


def _nonhead_provenance(inputs: dict) -> dict:
    """Read the actual approved image/model identities for the existing deployment."""
    manifest_path = Path(inputs["inputs_manifest"])
    raw_manifest = manifest_path.read_bytes()
    document = json.loads(raw_manifest)
    if document["inputs_sha256"] != inputs["expected_inputs_sha256"]:
        raise ValueError("NONHEAD_PROVENANCE_INPUTS_IDENTITY_MISMATCH")
    if hashlib.sha256(raw_manifest).hexdigest() != inputs["inputs_manifest_sha256"]:
        raise ValueError("NONHEAD_PROVENANCE_MANIFEST_MISMATCH")
    scene = Path(inputs["scene_model"])
    scene_sha = hashlib.sha256(scene.read_bytes()).hexdigest()
    if scene_sha != document["roles"]["scene_model"]["sha256"]:
        raise ValueError("NONHEAD_PROVENANCE_SCENE_MISMATCH")
    yolo, grounded = Path(inputs["yolo_weights"]), Path(inputs["grounded_root"])
    if (not yolo.is_absolute() or not yolo.is_file() or yolo.is_symlink()
            or not grounded.is_absolute() or not grounded.is_dir() or grounded.is_symlink()
            or not (grounded / "manifest.json").is_file()
            or (grounded / "manifest.json").is_symlink()):
        raise ValueError("NONHEAD_PROVENANCE_MODEL_PATH")
    yolo_sha = hashlib.sha256(yolo.read_bytes()).hexdigest()
    grounded_sha = hashlib.sha256((grounded / "manifest.json").read_bytes()).hexdigest()
    if (yolo_sha != inputs["yolo_weights_sha256"]
            or grounded_sha != inputs["grounded_manifest_sha256"]):
        raise ValueError("NONHEAD_PROVENANCE_MODEL_MISMATCH")
    if inputs["broker_image"] != BROKER_IMAGE:
        raise ValueError("NONHEAD_PROVENANCE_IMAGE_MISMATCH")
    from .parallel_perception_broker import image_record
    image = image_record(BROKER_IMAGE)
    if image.get("image_id") != BROKER_IMAGE_ID:
        raise ValueError("NONHEAD_PROVENANCE_IMAGE_MISMATCH")
    return {
        "kind": "ACT_NONHEAD_DEPLOYMENT_PROVENANCE", "schema_version": 1,
        "inputs_manifest": str(manifest_path),
        "inputs_manifest_sha256": inputs["inputs_manifest_sha256"],
        "inputs_sha256": document["inputs_sha256"],
        "scene_model": str(scene), "scene_model_sha256": scene_sha,
        "broker_image": BROKER_IMAGE, **image,
        "yolo_weights": str(yolo), "yolo_weights_sha256": yolo_sha,
        "grounded_root": str(grounded), "grounded_manifest_sha256": grounded_sha,
    }

#: the broker image the coordinator approved for this milestone: the perception stack and torch
#: live inside it, which is what the host lacks - and reusing it is the decision that supersedes the
#: container-free route this path was written under
BROKER_IMAGE = "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1"
BROKER_IMAGE_ID = "sha256:010dca70ce3ce995367793642c2e5515718986253cecacc032e9f7f7ec6c5457"
YOLO_WEIGHTS = Path("/data/work/models/so101-perception/yolo11n-seg-plastic-cup/best.pt")
GROUNDED_ROOT = Path("/data/work/models/so101-perception/grounded-sam-cup-pickplace/bundle")


def _broker_command(composition):
    """The deployment's container-free broker command.

    The broker parses the flags `broker_argv()` freezes, but the default route runs them **inside the image**, where
    `/runtime`, `/inputs` and `/models` are mounted. On the host those have to name this run's own paths, so the frozen
    flags are taken as-is and the flag values that describe locations are substituted with the composition's - the
    perception endpoint on its IPC root, the broker's input root, its ready receipt and the spec document it prepared.
    Everything the broker *verifies* (the frozen detector identity and its digest) is left untouched.
    """

    from so101_demo.cli.parallel_perception_broker import broker_argv

    flags = [str(item) for item in broker_argv()]
    # three of the composition's locations are always populated and the fourth falls back to the same authority IPC
    # root the composition itself builds its broker runtime root from
    ipc_root = composition.runtime_ipc_root or composition.authority.ipc_root
    substitutions = {
        "--endpoint": str(ipc_root / "perception.sock"),
        "--input-root": str(composition.broker_input_root),
        "--ready-receipt": str(composition.broker_runtime_root / "ready.json"),
        "--runtime-spec": str(composition.broker_spec_path),
        # the transport checks a declared digest against the file this flag names, so it too must point at the
        # file whose digest the specification declares
        "--yolo-weights": str(composition.spec.yolo_weights),
    }
    for index, flag in enumerate(flags):
        if flag in substitutions and index + 1 < len(flags):
            flags[index + 1] = substitutions[flag]
    return [sys.executable, "-m", "so101_demo.cli.parallel_perception_broker", *flags]


def _run(arguments) -> int:
    """One episode: the production pieces composed around a single-point request.

    Every value comes from the frozen set or from the caller; nothing is invented, and a missing frozen quantity is a
    refusal rather than a default.
    """

    inputs = Path(arguments.inputs)
    try:
        manifest_bytes = (inputs / "inputs-manifest.json").read_bytes()
        manifest = verify_frozen_inputs(inputs / "inputs-manifest.json")
        if json.loads(manifest_bytes) != manifest:
            raise ValueError("EPISODE_INPUTS_IDENTITY_CHANGED")
    except (OSError, ValueError) as error:
        print(f"act_diagnostic_episode: {error}", file=sys.stderr)
        return 2
    if manifest.get("mode") != arguments.mode:
        print(f"act_diagnostic_episode: the frozen set was prepared for {manifest.get('mode')!r}, "
              f"not {arguments.mode!r}", file=sys.stderr)
        return 2
    try:
        from ..act.execution_snapshot import verify_execution_snapshot
        binding = manifest.get("execution_snapshot")
        if binding is None:
            raise ValueError("EPISODE_EXECUTION_INPUTS_REQUIRED")
        snapshot = verify_execution_snapshot(inputs / binding["path"], expected_sha256=binding["sha256"])
        endpoint_targets = snapshot["targets"]
        target = tuple(endpoint_targets["final_target"])
        if arguments.final_cup_pose is not None:
            supplied = tuple(float(part) for part in arguments.final_cup_pose.split(","))
            if len(supplied) != 7 or any(not math.isfinite(value) for value in supplied):
                raise ValueError("EPISODE_FINAL_TARGET_INVALID")
            norm = math.sqrt(sum(value * value for value in supplied[3:]))
            if norm == 0 or abs(norm - 1) > 1e-3:
                raise ValueError("EPISODE_FINAL_TARGET_INVALID")
            if (any(abs(a - b) > 1e-12 for a, b in zip(supplied[:3], target[:3]))
                    or abs(sum(a / norm * b for a, b in zip(supplied[3:], target[3:]))) < 1 - 1e-12):
                raise ValueError("EPISODE_FINAL_TARGET_FROZEN_MISMATCH")
    except (OSError, ValueError) as error:
        print(f"act_diagnostic_episode: {error}", file=sys.stderr)
        return 2

    # The collection request is refused here, before any Teacher start (and before the run root exists): an unknown
    # value, or a fault outside the diagnostic mode. Every fault output is additionally checked by the worker.
    from ..act.collection_orchestration import CollectionRefused, validate_collection_request
    try:
        collection = validate_collection_request(arguments.collection, arguments.collection_fault,
                                                 run_mode=arguments.mode, run_root=Path(arguments.root).resolve(),
                                                 raw_pilot=None if getattr(arguments, "raw_pilot", None) is None else arguments.raw_pilot == "on",
                                                 inject_failure_at=getattr(arguments, "teacher_inject_failure_at", None))
        from ..act.frozen_runtime_inputs import load_recorder_frozen_policy, load_teacher_frozen_inputs
        load_teacher_frozen_inputs(inputs / "inputs-manifest.json")
        if collection.enabled:
            load_recorder_frozen_policy(inputs / "inputs-manifest.json")
    except (CollectionRefused, OSError, ValueError) as error:
        print(f"act_diagnostic_episode: {error}", file=sys.stderr)
        return 2
    from so101_demo.core.task_points import TaskPoint
    from so101_demo.parallel_batch.contracts.common import RunMode
    from so101_demo.parallel_batch.contracts.linux_cuda import BatchKind, BatchRequest

    root = Path(arguments.root)
    if root.exists():
        print(f"act_diagnostic_episode: {root} already exists; a run is a new evidence root", file=sys.stderr)
        return 2
    root.mkdir(parents=True, mode=0o700)
    batch_id = f"nonhead-{arguments.mode}-{int(time.time())}"
    # the point must be one the approved catalogue actually names: task_start is the episode's start, and the
    # request selects exactly that one id, so the sweep vehicle runs a single episode
    point = TaskPoint(id="task_start", label=arguments.mode,
                      cup_position_world_m=tuple(endpoint_targets["initial_target"][:3]))
    # the composition reads selected_point_ids off this request, so it is the versioned contract rather than the
    # application-layer one: one point, one worker, an execute run and a fresh first pass
    request = BatchRequest(batch_id=batch_id, run_mode=RunMode.EXECUTE, selected_point_ids=(point.id,),
                             worker_count=1, evidence_root=(root / "run").resolve(),
                             batch_kind=BatchKind.FIRST_PASS)
    # ProductionBatchComposition owns the run's journal and Coordinator.
    from so101_demo.parallel_batch.contracts.macos_single_worker import (
        load_runtime_config_any_schema,
    )

    config_path = inputs / manifest["roles"]["runtime_config"]["path"]
    config = load_runtime_config_any_schema(config_path)
    # the collection mode (diagnostic or formal) is not the run mode: driving the approved stack is an execute run,
    # and the mode stays recorded in the run's own log and in the frozen manifest

    # the frozen set is re-read once more before the composition is built
    try:
        if ((inputs / "inputs-manifest.json").read_bytes() != manifest_bytes
                or verify_frozen_inputs(inputs / "inputs-manifest.json") != manifest):
            raise ValueError("EPISODE_INPUTS_IDENTITY_CHANGED")
    except (OSError, ValueError) as error:
        print(f"act_diagnostic_episode: {error}", file=sys.stderr)
        return 2
    # the two artefacts the specification needs, both written under this run's own root: a one-point TaskPointList
    # (the sweep catalogue reduced to this episode) and a copy of the frozen provenance inputs, so the composition
    # verifies what was frozen rather than what is on disk now
    points_document = {"schema_version": 1,
                       "points": [{"id": point.id, "label": point.label,
                                   "cup_position_world_m": list(point.cup_position_world_m)}]}
    points_path = root / "points.json"
    points_path.write_text(json.dumps(points_document, indent=2, sort_keys=True) + "\n")
    provenance_paths = {}
    for name in ("inputs-manifest.json",):
        source = inputs / name
        if source.is_file():
            payload = manifest_bytes
            destination = root / name
            destination.write_bytes(payload)
            provenance_paths[name] = str(destination)
    log = root / "run.log"
    with log.open("w") as stream:
        stream.write(f"batch_id={batch_id}\nmode={arguments.mode}\nlifecycle={arguments.lifecycle}\n"
                     f"final_cup_pose={target}\ninputs={inputs.resolve()}\n"
                     f"config={type(config).__name__}\ncomposition=ProductionBatchComposition\n"
                     f"points={points_path}\nprovenance={sorted(provenance_paths)}\n"
                     f"broker_image={BROKER_IMAGE} (reused)\n")
        if collection.inject_failure_at is not None:
            stream.write(f"teacher_injected_failure_at={collection.inject_failure_at}\n")
        stream.flush()
        os.fsync(stream.fileno())
    if collection.inject_failure_at is not None:
        # the evidence that this was an injected run, beside (not inside) the closed episode-scope document
        (root / "injected-failure.json").write_text(json.dumps(
            {"kind": "teacher_injected_failure", "schema_version": 1, "state": collection.inject_failure_at,
             "mode": arguments.mode, "code": "TEACHER_INJECTED_EXECUTION_FAILURE", "batch_id": batch_id}, sort_keys=True) + "\n")
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import PreparedBatch
    from so101_demo.parallel_batch.start_guard import StartGuardPolicy
    from so101_demo.parallel_batch.start_guard_probe import compose_default_start_guard

    catalog = {point.id: points_document["points"][0]}
    catalog_sha = hashlib.sha256(points_path.read_bytes()).hexdigest()
    selection_sha = hashlib.sha256(json.dumps([point.id], separators=(",", ":")).encode()).hexdigest()
    manifest_path = root / "inputs-manifest.json"
    scene_path = inputs / manifest["roles"]["scene_model"]["path"]
    provenance_inputs = {"inputs_manifest": str(manifest_path),
                         "inputs_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                         "expected_inputs_sha256": manifest["inputs_sha256"],
                         "scene_model": str(scene_path), "yolo_weights": str(YOLO_WEIGHTS),
                         "yolo_weights_sha256": config.yolo_weights_sha256,
                         "grounded_root": str(GROUNDED_ROOT),
                         "grounded_manifest_sha256": config.grounded_sam_manifest_sha256,
                         "broker_image": BROKER_IMAGE}
    provenance = _nonhead_provenance(provenance_inputs)
    spec = PreparedBatch(
        start_guard=compose_default_start_guard(StartGuardPolicy(),
                                               state_root=root / "start-guard"),
        request=request, adaptive_request=None, config=config,
        config_path=config_path, adaptive_config_path=None,
        points_path=points_path, catalog=catalog, expected_final_cup_pose_world=tuple(target),
        catalog_sha256=catalog_sha, selection_sha256=selection_sha, broker_image=BROKER_IMAGE,
        # the broker spec takes these four from the specification itself, so they name the frozen documents that
        # really participate here - the development runtime and the scene model - with the same digests the
        # provenance states
        # the transport checks each declared digest against the file beside it, so both names point at one real
        # file and carry that file's own digest: the frozen scene model, whose copy is byte-identical to the source
        # the transport compares these against the frozen runtime configuration's own fields, so the run declares
        # exactly what that configuration carries rather than a digest of its own choosing
        yolo_weights=YOLO_WEIGHTS,
        yolo_weights_sha256=config.yolo_weights_sha256,
        grounded_root=GROUNDED_ROOT,
        grounded_manifest_sha256=config.grounded_sam_manifest_sha256,
        provenance=provenance, manifest=manifest,
        provenance_inputs=provenance_inputs, provenance_verifier=_nonhead_provenance,
        start_guard_evidence=None, resume=False)
    # this route runs the broker as a host process beside the run, so its spec names the host copy of the runtime
    # config rather than the container mount
    # the composition builds the ACT result port when it is given the episode scope below, so the coordinator's ACT gate
    # fires on a real ACT episode
    # the broker runs in its image, which is the route the coordinator approved: the composition's
    # own default builds that command from the spec, so the container-free builder is not passed here
    # The episodes of this run share one scope document: its values - mode, scene, seed, inputs digest - are the
    # same for every episode, while each episode's own audit source is a different path under that episode's
    # root. It is written here because this is the process that holds the frozen set; the composition only
    # carries the path into the worker specifications.
    from so101_demo.act.collection_scope import build_collection_scope, write_collection_scope

    _scope_path = root / "episode-scope.json"
    write_collection_scope(build_collection_scope(
        str(manifest["mode"]), scene_id=str(manifest["roles"]["anchor_scene"]["identity"]["scene_id"]),
        seed=int(manifest["roles"]["anchor_scene"]["identity"]["seed"]),
        inputs_sha256=str(manifest["inputs_sha256"])), _scope_path)
    composition = ProductionBatchComposition(spec, collection=collection,
        episode_scope_path=str(_scope_path),
        episode_inputs_manifest=str((inputs / "inputs-manifest.json").resolve()))
    # the drive, exactly as the batch path does it: the composition runs itself, its summary becomes an outcome
    # document, and the document is written as the aggregate beside the run's own evidence
    from so101_demo.cli.mujoco_batch.common import _write_json
    from so101_demo.cli.mujoco_batch.outcome import outcome_document
    from so101_demo.cli.mujoco_parallel_batch import _run_with_shutdown_signals

    evidence_root = request.evidence_root
    if not evidence_root.exists():
        evidence_root.mkdir(parents=True, mode=0o700)
    if not spec.resume:
        _write_json(evidence_root / "batch_manifest.json", dict(spec.manifest))
    summary = _run_with_shutdown_signals(composition.run)
    _summary_code, document = outcome_document(summary)
    _write_json(evidence_root / "aggregate_results.json", document)
    code, document = _verified_run_completion(root)
    print(json.dumps(document, sort_keys=True))
    return code


def main(argv=None) -> int:
    arguments = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if arguments.command == "inspect":
        # the discovery already exists in the inputs module and is read-only: it selects nothing by recency and
        # defaults nothing, reporting a blocker for every role without an approved, identity-matching candidate
        document = inspect_inputs(Path(arguments.source_root), Path(arguments.ledger))
        Path(arguments.output).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
        print(arguments.output)
        return 0
    if arguments.command == "prepare":
        return _prepare(arguments)
    if arguments.command == "preflight":
        return _preflight(arguments)
    if arguments.command in ('qc', 'verify-commit', 'check-export', 'readback'):
        return _readback_entry(arguments)
    if arguments.command == "run":
        return _run(arguments)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
