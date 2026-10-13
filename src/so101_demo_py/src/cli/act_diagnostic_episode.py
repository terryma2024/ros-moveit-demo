"""Inspect approved candidates, freeze and preflight inputs, and independently read a finished run's original native QC,
Coordinator commit and diagnostic export refusal. Collection itself runs through `act_collect_parallel`."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
