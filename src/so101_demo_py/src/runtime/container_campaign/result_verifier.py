"""Independent Host readback of every frozen scene's registered container task result."""

from dataclasses import asdict
from pathlib import Path

from so101_demo.act.result_store import verify_container_task_registration
from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.task_journal import ContainerTaskJournal
from so101_demo.runtime.inference.config import validate_file_ref

_ROW = {'scene_id', 'worker_id', 'location', 'task_id', 'launch_id'}


class ContainerWaveResultVerifier:
    def __init__(self, *, root, registry, case_inputs, qualification=False):
        root = Path(root)
        if (not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir()
                or type(registry) is not ContainerLaunchRegistry or type(case_inputs) is not dict
                or not case_inputs or type(qualification) is not bool):
            raise ValueError('CONTAINER_WAVE_VERIFIER_INVALID')
        inputs = {}
        for scene_id, refs in case_inputs.items():
            if (type(scene_id) is not str or not scene_id or type(refs) is not dict
                    or set(refs) != {'scope', 'inputs_manifest'}):
                raise ValueError('CONTAINER_WAVE_VERIFIER_INVALID')
            inputs[scene_id] = {name: dict(ref) for name, ref in refs.items()}
            for ref in inputs[scene_id].values():
                validate_file_ref(ref)
        self.root, self.registry, self.case_inputs, self.qualification = root, registry, inputs, qualification

    def verify_wave(self, plan, outcome, shards):
        try:
            if (type(plan) is not dict or type(outcome) is not dict
                    or set(outcome) != {'wave_index', 'coordinator_root', 'case_results', 'infra_errors'}
                    or type(plan['wave_index']) is not int or type(outcome['wave_index']) is not int
                    or outcome['wave_index'] != plan['wave_index']
                    or type(outcome['infra_errors']) is not list or outcome['infra_errors']):
                raise ValueError('shape/infra')
            journal_root = self.root/'host'/('wave-'+str(plan['wave_index']))/'task-journal'
            if outcome['coordinator_root'] != str(journal_root):
                raise ValueError('journal scope')
            records = {item['launch']['launch_id']: item for item in self.registry.records()}
            roots, instances = {}, {}
            for shard in shards:
                launch = shard.launch
                record = records[launch.launch_id]
                if (record['launch'] != asdict(launch) or launch.role != 'shard'
                        or launch.wave_id != 'wave-'+str(plan['wave_index'])
                        or record['owner'] != asdict(shard.owner) or record['binding'] is None
                        or launch.worker_id in roots):
                    raise ValueError('unregistered instance')
                root = Path(launch.owned_root)
                if root != self.root/launch.wave_id/launch.worker_id/('g'+str(launch.launch_generation)):
                    raise ValueError('private root')
                roots[launch.worker_id] = root
                instances[launch.launch_id] = dict(owner_root=str(root), worker_id=launch.worker_id,
                    launch_generation=launch.launch_generation, wave_id=launch.wave_id)
            rows = outcome['case_results']
            scene_order = plan['scene_ids']
            if (type(rows) is not list or not rows or not roots or type(scene_order) is not list or not scene_order
                    or len(set(scene_order)) != len(scene_order) or len(rows) != len(scene_order)):
                raise ValueError('denominator')
            journal = ContainerTaskJournal(journal_root, instances=instances).records()
            if (len(journal) != len(rows) or any(item['failed'] is not None or item['collected'] is None
                                                   for item in journal.values())):
                raise ValueError('failed or unfinished task')
            by_scene = {}
            for task_id, item in journal.items():
                collected = item['collected']
                if (collected['scene_id'] in by_scene or collected['scene_id'] not in scene_order
                        or collected['owner_root'] != str(roots.get(collected['worker_id']))):
                    raise ValueError('journal identity')
                by_scene[collected['scene_id']] = collected
            verified = {}
            for row in rows:
                if type(row) is not dict or set(row) != _ROW or row['scene_id'] in verified:
                    raise ValueError('case identity')
                collected = by_scene.get(row['scene_id'])
                if (collected is None or row['worker_id'] != collected['worker_id']
                        or row['location'] != collected['host_output'] or row['task_id'] != collected['task_id']
                        or row['launch_id'] != collected['instance_id']):
                    raise ValueError('row differs from the collected record')
                refs = self.case_inputs[row['scene_id']]
                paths = {name: validate_file_ref(ref) for name, ref in refs.items()}
                proof = verify_container_task_registration(journal_root/row['task_id']/'collected.json',
                    scope=paths['scope'], inputs_manifest=paths['inputs_manifest'])
                if proof['task_id'] != row['task_id'] or proof['worker_id'] != row['worker_id']:
                    raise ValueError('readback identity')
                # Keep FAILED Teacher and INVALID/QC-failed data in the frozen denominator.
                verified[row['scene_id']] = dict(row, proof=proof, registration=str(journal_root/row['task_id']/'collected.json'),
                    owner_root=str(roots[row['worker_id']]), scope_path=str(paths['scope']),
                    inputs_manifest=str(paths['inputs_manifest']))
            if set(verified) != set(scene_order):
                raise ValueError('missing scene')
            self._check_scheduling(plan, by_scene, roots)
            return dict(wave_index=plan['wave_index'], scene_count=len(scene_order),
                coordinator_root=str(journal_root), case_results=[verified[name] for name in scene_order])
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            raise ValueError('CONTAINER_WAVE_COMMIT_READBACK_INVALID') from error

    def _check_scheduling(self, plan, by_scene, roots):
        if self.qualification:
            counts = {worker: 0 for worker in roots}
            for collected in by_scene.values():
                counts[collected['worker_id']] += 1
            if any(count < 2 for count in counts.values()):
                raise ValueError('two collected tasks per instance required')
        assignment = plan.get('assignment')
        if assignment is None:
            return
        done = {}
        for worker, reserved in assignment['reserved_by_worker'].items():
            if any(by_scene[scene]['worker_id'] != worker for scene in reserved):
                raise ValueError('reserved scene collected by another instance')
            done[worker] = max(by_scene[scene]['collected_monotonic_s'] for scene in reserved)
        for scene in assignment['surplus']:
            collected = by_scene[scene]
            if collected['assigned_monotonic_s'] < done[collected['worker_id']]:
                raise ValueError('surplus assigned before both reserved tasks were collected')


_TASK_DATA = ('result_status', 'teacher_execution_status', 'teacher_task_result', 'act_data_status', 'act_data_reason',
              'act_data_qc', 'export_eligible', 'result_sha256', 'task_result_sha256')


def build_frozen_index(*, campaign_id, qualification, scene_count, waves):
    """The one document export reads: every collected task, and the episodes a formal export may take.

    A qualification campaign never lists committed episodes."""
    tasks, committed = [], []
    for wave in waves:
        for row in wave['case_results']:
            proof = row['proof']
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
