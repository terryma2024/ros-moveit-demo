"""Independent Host readback of every frozen scene's registered container task result."""

from dataclasses import asdict
from pathlib import Path

from so101_demo.act.result_store import verify_container_task_registration
from so101_demo.runtime.container_campaign.readback_pool import DEFAULT_TIMEOUT_S, resolve_readback_workers, run_readbacks
from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.task_journal import read_task_journal
from so101_demo.runtime.inference.config import validate_file_ref

_ROW = {'scene_id', 'worker_id', 'location', 'task_id', 'launch_id'}


def check_wave_scheduling(plan, by_scene, roots, qualification, faulted_workers=frozenset()):
    """The qualification scheduling rule over collected records: two tasks per instance, reserved scenes before surplus.

    A worker in `faulted_workers` had a task fault: it owes nothing further, its later scenes are missing, and it takes no surplus.

    Refusals carry a coded message (`INSTANCE_SHORT:<worker>`, `RESERVED_COLLECTED_ELSEWHERE:<scene>`,
    `SURPLUS_BEFORE_RESERVED:<scene>`) so a report can name the exact failure."""
    assignment = plan.get('assignment')
    if qualification and plan.get('plane') != 'spot_check':
        counts = {worker: 0 for worker in roots}
        for collected in by_scene.values():
            counts[collected['worker_id']] += 1
        for worker in sorted(counts):
            if worker in faulted_workers:
                continue
            # a reserved slot owes exactly its own reserved cases (two on the gate plane, one or two on a functional wave)
            owed = len(assignment['reserved_by_worker'][worker]) if assignment is not None else 2
            if counts[worker] < owed:
                raise ValueError('INSTANCE_SHORT:'+worker)
    if assignment is None:
        return
    done = {}
    for worker, reserved in assignment['reserved_by_worker'].items():
        for scene in reserved:
            if scene in by_scene and by_scene[scene]['worker_id'] != worker:
                raise ValueError('RESERVED_COLLECTED_ELSEWHERE:'+scene)
        if worker not in faulted_workers:
            done[worker] = max(by_scene[scene]['collected_monotonic_s'] for scene in reserved)
    for scene in assignment['surplus']:
        collected = by_scene.get(scene)
        if collected is None:
            continue   # never recorded: it is in the wave's missing list
        if collected['worker_id'] not in done or collected['assigned_monotonic_s'] < done[collected['worker_id']]:
            raise ValueError('SURPLUS_BEFORE_RESERVED:'+scene)


def verify_wave_records(root, plan, launch_records, case_inputs, qualification, *, case_rows=None, readback_workers=1,
                        readback_timeout_s=DEFAULT_TIMEOUT_S, partial=False):
    """Recompute one wave's verified record from registry records and the task journal alone; no live owner is involved.

    `launch_records` are the registry records of the wave's shard launches. Without `case_rows` the rows are the collected
    journal records, which is what an independent verifier has; with them (the live verifier passes the coordinator's rows) each
    row must equal its collected record. Every task is read back through `verify_container_task_registration` against the
    scene's own scope and inputs manifest; FAILED Teacher and INVALID/QC-failed data stay in the denominator.

    A task whose failure the journal records is a FAULT entry, not a refusal: the wave record then lists it under `faults`
    (scene, worker, task, launch and reason) and lists the plan's scenes without any record under `missing`; both keys are present
    only when non-empty, so a fault-free wave record is unchanged. A task that was assigned and neither collected nor failed is
    still refused.

    `partial` is for a wave that phase 1 ended on its deadline: `plan` then names only the scenes collected, and the scheduling rule
    (two tasks per qualification instance, reserved before surplus) is the one check that is skipped; the scenes that were never
    collected are the campaign's missing evidence, recorded by the owner."""
    try:
        root = Path(root)
        wave_index = plan['wave_index']
        if type(plan) is not dict or type(wave_index) is not int or not root.is_absolute():
            raise ValueError('shape')
        wave_id = 'wave-'+str(wave_index)
        journal_root = root/'host'/wave_id/'task-journal'
        roots, instances = {}, {}
        for record in launch_records:
            launch = record['launch']
            if (launch['role'] != 'shard' or launch['wave_id'] != wave_id or record['owner'] is None
                    or record['binding'] is None or launch['worker_id'] in roots):
                raise ValueError('unregistered instance')
            owned = Path(launch['owned_root'])
            if owned != root/wave_id/launch['worker_id']/('g'+str(launch['launch_generation'])):
                raise ValueError('private root')
            roots[launch['worker_id']] = owned
            instances[launch['launch_id']] = dict(owner_root=str(owned), worker_id=launch['worker_id'],
                launch_generation=launch['launch_generation'], wave_id=wave_id)
        scene_order = plan['scene_ids']
        if not roots or type(scene_order) is not list or not scene_order or len(set(scene_order)) != len(scene_order):
            raise ValueError('denominator')
        journal = read_task_journal(journal_root, instances)
        if any(item['failed'] is None and item['collected'] is None for item in journal.values()):
            raise ValueError('unfinished task')
        done_tasks = {task_id: item for task_id, item in journal.items() if item['collected'] is not None}
        failed_tasks = {task_id: item['failed'] for task_id, item in journal.items() if item['failed'] is not None}
        rows = case_rows
        if rows is None:
            rows = [dict(scene_id=item['collected']['scene_id'], worker_id=item['collected']['worker_id'],
                         location=item['collected']['host_output'], task_id=task_id,
                         launch_id=item['collected']['instance_id']) for task_id, item in done_tasks.items()]
        if (type(rows) is not list or (not rows and not failed_tasks) or len(rows) + len(failed_tasks) > len(scene_order)
                or len(done_tasks) != len(rows)):
            raise ValueError('denominator')
        faults, faulted_workers, seen_scenes = [], set(), set()
        for task_id, failed in failed_tasks.items():
            if (failed['scene_id'] not in scene_order or failed['owner_root'] != str(roots.get(failed['worker_id']))
                    or failed['scene_id'] in seen_scenes or type(failed['reason']) is not str):
                raise ValueError('failed identity')
            seen_scenes.add(failed['scene_id'])
            faulted_workers.add(failed['worker_id'])
            faults.append(dict(scene_id=failed['scene_id'], worker_id=failed['worker_id'], task_id=task_id,
                               launch_id=failed['instance_id'], reason=failed['reason']))
        by_scene = {}
        for task_id, item in done_tasks.items():
            collected = item['collected']
            if (collected['scene_id'] in by_scene or collected['scene_id'] not in scene_order
                    or collected['scene_id'] in seen_scenes
                    or collected['owner_root'] != str(roots.get(collected['worker_id']))):
                raise ValueError('journal identity')
            by_scene[collected['scene_id']] = collected
        verified = {}
        readback_workers = resolve_readback_workers(readback_workers)
        pooled = readback_workers > 1 and len(rows) > 1
        prepared, early = [], None

        def prepare(row):
            if type(row) is not dict or set(row) != _ROW or row['scene_id'] in verified:
                raise ValueError('case identity')
            collected = by_scene.get(row['scene_id'])
            if (collected is None or row['worker_id'] != collected['worker_id']
                    or row['location'] != collected['host_output'] or row['task_id'] != collected['task_id']
                    or row['launch_id'] != collected['instance_id']):
                raise ValueError('row differs from the collected record')
            refs = case_inputs[row['scene_id']]
            return {name: validate_file_ref(ref) for name, ref in refs.items()}

        def finish(row, paths, proof):
            if proof['task_id'] != row['task_id'] or proof['worker_id'] != row['worker_id']:
                raise ValueError('readback identity')
            # Keep FAILED Teacher and INVALID/QC-failed data in the frozen denominator.
            verified[row['scene_id']] = dict(row, proof=proof, registration=str(journal_root/row['task_id']/'collected.json'),
                owner_root=str(roots[row['worker_id']]), scope_path=str(paths['scope']),
                inputs_manifest=str(paths['inputs_manifest']))

        if not pooled:
            for row in rows:
                paths = prepare(row)
                finish(row, paths, verify_container_task_registration(journal_root/row['task_id']/'collected.json',
                    scope=paths['scope'], inputs_manifest=paths['inputs_manifest']))
        else:
            # The cheap identity checks run first, in row order. A row that fails one ends the list, so the scenes before it are
            # still read back (and may fail first, as they would serially); workers only compute, this thread decides and records.
            seen = set()
            for row in rows:
                try:
                    if type(row) is dict and row.get('scene_id') in seen:
                        raise ValueError('case identity')
                    prepared.append((row, prepare(row)))
                    seen.add(row['scene_id'])
                except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
                    early = error
                    break
            answers = run_readbacks([dict(scene_id=row['scene_id'], registration=str(journal_root/row['task_id']/'collected.json'),
                scope=str(paths['scope']), inputs_manifest=str(paths['inputs_manifest'])) for row, paths in prepared],
                workers=readback_workers, timeout_s=readback_timeout_s)
            for (row, paths), answer in zip(prepared, answers, strict=True):
                if isinstance(answer, Exception):
                    raise answer
                finish(row, paths, answer)
            if early is not None:
                raise early
        faults.sort(key=lambda item: scene_order.index(item['scene_id']))
        missing = [name for name in scene_order if name not in verified and name not in seen_scenes]
        if missing and not faults:
            raise ValueError('missing scene')
        if not set(verified) <= set(scene_order):
            raise ValueError('missing scene')
        if not partial:
            check_wave_scheduling(plan, by_scene, roots, qualification, faulted_workers)
        record = dict(wave_index=wave_index, scene_count=len(scene_order),
            coordinator_root=str(journal_root), case_results=[verified[name] for name in scene_order if name in verified])
        if faults:
            record['faults'] = faults
        if missing:
            record['missing'] = missing
        return record
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise ValueError('CONTAINER_WAVE_COMMIT_READBACK_INVALID') from error


class ContainerWaveResultVerifier:
    def __init__(self, *, root, registry, case_inputs, qualification=False, readback_workers=None,
                 readback_timeout_s=DEFAULT_TIMEOUT_S, finalize_readback_workers=None):
        root = Path(root)
        if (not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir()
                or type(registry) is not ContainerLaunchRegistry or type(case_inputs) is not dict
                or not case_inputs or type(qualification) is not bool):
            raise ValueError('CONTAINER_WAVE_VERIFIER_INVALID')
        resolve_readback_workers(readback_workers)
        resolve_readback_workers(finalize_readback_workers)
        self.readback_workers, self.readback_timeout_s = readback_workers, readback_timeout_s
        #: the pool of the end-of-campaign readbacks (`verify_processing`, `verify_rounds`): explicit, else the larger finalize default
        self.finalize_readback_workers = finalize_readback_workers if finalize_readback_workers is not None else readback_workers
        self._round_cache = {}
        inputs = {}
        for scene_id, refs in case_inputs.items():
            if (type(scene_id) is not str or not scene_id or type(refs) is not dict
                    or set(refs) != {'scope', 'inputs_manifest'}):
                raise ValueError('CONTAINER_WAVE_VERIFIER_INVALID')
            inputs[scene_id] = {name: dict(ref) for name, ref in refs.items()}
            for ref in inputs[scene_id].values():
                validate_file_ref(ref)
        self.root, self.registry, self.case_inputs, self.qualification = root, registry, inputs, qualification

    def verify_wave(self, plan, outcome, shards, partial=False):
        """The live verification: the coordinator's outcome and the live shard owners are checked, then the records recompute."""
        try:
            if (type(plan) is not dict or type(outcome) is not dict
                    or set(outcome) - {'scene_faults'} != {'wave_index', 'coordinator_root', 'case_results', 'infra_errors'}
                    or type(plan['wave_index']) is not int or type(outcome['wave_index']) is not int
                    or outcome['wave_index'] != plan['wave_index']
                    or type(outcome['infra_errors']) is not list or outcome['infra_errors']):
                raise ValueError('shape/infra')
            if outcome['coordinator_root'] != str(self.root/'host'/('wave-'+str(plan['wave_index']))/'task-journal'):
                raise ValueError('journal scope')
            records = {item['launch']['launch_id']: item for item in self.registry.records()}
            launch_records = []
            for shard in shards:
                record = records[shard.launch.launch_id]
                if record['launch'] != asdict(shard.launch) or record['owner'] != asdict(shard.owner):
                    raise ValueError('unregistered instance')
                launch_records.append(record)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            raise ValueError('CONTAINER_WAVE_COMMIT_READBACK_INVALID') from error
        record = verify_wave_records(self.root, plan, launch_records, self.case_inputs, self.qualification,
                                     case_rows=outcome['case_results'], readback_workers=self.readback_workers,
                                     readback_timeout_s=self.readback_timeout_s, partial=partial)
        # the coordinator's fault list must be exactly the journal's FAILED tasks
        claimed = outcome.get('scene_faults', [])
        journaled = record.get('faults', ()) if type(record) is dict else ()
        if (type(claimed) is not list or any(type(item) is not dict for item in claimed)
                or sorted(str(item.get('task_id')) for item in claimed) != sorted(item['task_id'] for item in journaled)):
            raise ValueError('CONTAINER_WAVE_COMMIT_READBACK_INVALID')
        return record

    def verify_processing(self, waves, scene_ids):
        """The combined proof of both phases (`processing_verifier.verify_processing`) over the verified phase-1 waves."""
        from so101_demo.runtime.container_campaign.processing_verifier import verify_processing

        return verify_processing(self.root, waves, scene_ids, readback_workers=self._finalize_workers(),
                                 readback_timeout_s=self.readback_timeout_s)

    def _finalize_workers(self):
        return resolve_readback_workers(self.finalize_readback_workers, finalize=True)

    def verify_rounds(self, rounds, scene_ids):
        """Recompute every recording round and select one final verdict per scene."""
        from so101_demo.runtime.container_campaign.processing_verifier import verify_rounds

        return verify_rounds(self.root, rounds, scene_ids, readback_workers=self._finalize_workers(),
                             readback_timeout_s=self.readback_timeout_s)

    def verify_rounds_provisional(self, rounds, scene_ids):
        """`verify_rounds` for an intermediate pass that only selects the next retry candidates: it trusts the offline processor's
        content-bound QC memo where the memo covers the files on disk now, and reads each round once (a round whose inputs and files are
        unchanged is not read again). The result is never written to an index; the final pass is `verify_rounds`."""
        from so101_demo.runtime.container_campaign.processing_verifier import verify_rounds

        return verify_rounds(self.root, rounds, scene_ids, readback_workers=self._finalize_workers(),
                             readback_timeout_s=self.readback_timeout_s, trust_memo=True, round_cache=self._round_cache)

    def _check_scheduling(self, plan, by_scene, roots):
        check_wave_scheduling(plan, by_scene, roots, self.qualification)


_TASK_DATA = ('result_status', 'teacher_execution_status', 'teacher_task_result', 'act_data_status', 'act_data_reason',
              'act_data_qc', 'export_eligible', 'result_sha256', 'task_result_sha256')


def _round_frozen_index(campaign_id, qualification, scene_count, combined):
    final = {key: value for key, value in combined.items() if key != 'rounds'}
    index = build_frozen_index(campaign_id=campaign_id, qualification=qualification, scene_count=scene_count, combined=final)
    tasks = []
    for scene in combined['scenes']:
        for attempt in scene['recording_attempts']:
            one = build_frozen_index(campaign_id=campaign_id, qualification=qualification, scene_count=1,
                                     combined=dict(scenes=[attempt]))
            tasks.extend(dict(item, recording_round=attempt['recording_round'], wave_index=attempt['wave_index'],
                              final=attempt['recording_round'] == scene['recording_round']) for item in one['collected_tasks'])
    index.update(schema_version=3, collected_tasks=tasks)
    return index


def build_frozen_index(*, campaign_id, qualification, scene_count, waves=None, combined=None):
    """The one document export reads: every collected task, and the episodes a formal export may take.

    A qualification campaign never lists committed episodes. With `waves` (phase-1 verified records) every proof must already be
    final: a proof whose processing is still pending has no episode or QC to list, and the index is refused with
    PROCESSING_PENDING. With `combined` (the combined proof of both phases, `processing_verifier.verify_processing`) each task
    carries the final verdict of both phases and a processed pass becomes a schema 4 committed episode whose evidence names the
    phase-2 output directory; scenes without evidence (processing fault or missing, or never recorded) are listed in
    `scenes_without_evidence` and never skipped."""
    if (waves is None) == (combined is None):
        raise ValueError('FROZEN_INDEX_SOURCE_INVALID')
    if combined is not None and 'rounds' in combined:
        return _round_frozen_index(campaign_id, qualification, scene_count, combined)
    tasks, committed, without = [], [], []
    if combined is not None:
        for item in combined['scenes']:
            proof, state = item['phase1'], item['state']
            if state in ('FAULT', 'MISSING'):
                without.append(dict(scene_id=item['scene_id'], state=state, reason=item['reason']))
            if proof is None:
                continue
            verdict = item['verdict']
            phase2 = item['phase2']
            tasks.append(dict(scene_id=item['scene_id'], worker_id=item['worker_id'], task_id=item['task_id'],
                launch_id=item['launch_id'], location=item['location'], state=state,
                result_status=verdict['status'], teacher_execution_status=verdict['teacher_execution_status'],
                teacher_task_result=verdict['teacher_task_result'], act_data_status=verdict['act_data_status'],
                act_data_reason=verdict['act_data_reason'], act_data_qc=verdict['act_data_qc'],
                export_eligible=verdict['export_eligible'], result_sha256=proof['result_sha256'],
                task_result_sha256=proof['task_result_sha256'],
                processed_result_sha256=None if phase2 is None else phase2['processed_result']['sha256']))
            if state == 'PROCESSED' and verdict['export_eligible'] is True and not qualification:
                committed.append(dict(kind='ACT_COMMITTED_EPISODE', schema_version=4, scene_id=item['scene_id'],
                    verifier_sha256=proof['result_sha256'], task_result_sha256=proof['task_result_sha256'],
                    processed_result_sha256=phase2['processed_result']['sha256'],
                    collection_evidence=dict(registration=item['registration'], owner_root=item['owner_root'],
                        task_id=item['task_id'], result_location=proof['location'], scope_path=item['scope_path'],
                        inputs_manifest=item['inputs_manifest'], processing_output=phase2['output_dir'])))
        return dict(schema_version=2, kind='act_collection_frozen_index', campaign_id=campaign_id,
                    qualification=qualification, scene_count=scene_count, collected_tasks=tasks,
                    committed_episodes=committed, scenes_without_evidence=without)
    for wave in waves:
        for row in wave['case_results']:
            proof = row['proof']
            if proof.get('processing') == 'PENDING':
                raise ValueError('PROCESSING_PENDING')
            tasks.append(dict(scene_id=row['scene_id'], worker_id=row['worker_id'], task_id=row['task_id'],
                launch_id=row['launch_id'], location=row['location'], **{name: proof[name] for name in _TASK_DATA}))
            if proof['export_eligible'] is True and not qualification:
                committed.append(dict(kind='ACT_COMMITTED_EPISODE', schema_version=3, scene_id=row['scene_id'],
                    verifier_sha256=proof['result_sha256'], task_result_sha256=proof['task_result_sha256'],
                    collection_evidence=dict(registration=row['registration'], owner_root=row['owner_root'],
                        task_id=row['task_id'], result_location=proof['location'], scope_path=row['scope_path'],
                        inputs_manifest=row['inputs_manifest'])))
    return dict(schema_version=1, kind='act_collection_frozen_index', campaign_id=campaign_id,
                qualification=qualification, scene_count=scene_count, collected_tasks=tasks,
                committed_episodes=committed)
