"""Independent Host readback of every frozen scene's actual committed result."""

from dataclasses import asdict
from pathlib import Path

from so101_demo.act.result_store import verify_coordinator_commit
from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
from so101_demo.runtime.inference.config import validate_file_ref


class ContainerWaveResultVerifier:
    def __init__(self,*,root,registry,case_inputs):
        root=Path(root)
        if (not root.is_absolute() or root.resolve(strict=True)!=root or not root.is_dir()
                or type(registry) is not ContainerLaunchRegistry or type(case_inputs) is not dict
                or not case_inputs):
            raise ValueError('CONTAINER_WAVE_VERIFIER_INVALID')
        inputs={}
        for scene_id,refs in case_inputs.items():
            if (type(scene_id) is not str or not scene_id or type(refs) is not dict
                    or set(refs)!={'scope','inputs_manifest'}):
                raise ValueError('CONTAINER_WAVE_VERIFIER_INVALID')
            inputs[scene_id]={name:dict(ref) for name,ref in refs.items()}
            for ref in inputs[scene_id].values():
                validate_file_ref(ref)
        self.root,self.registry,self.case_inputs=root,registry,inputs

    def verify_wave(self,plan,outcome,shards):
        try:
            if (type(plan) is not dict or type(outcome) is not dict
                    or set(outcome)!={'wave_index','coordinator_root','case_results','infra_errors'}
                    or type(plan['wave_index']) is not int or type(outcome['wave_index']) is not int
                    or outcome['wave_index']!=plan['wave_index']
                    or type(outcome['infra_errors']) is not list or outcome['infra_errors']):
                raise ValueError('shape/infra')
            coordinator_root=self.root/'host'/('wave-'+str(plan['wave_index']))/'coordinator'
            if outcome['coordinator_root']!=str(coordinator_root):
                raise ValueError('coordinator scope')
            records={item['launch']['launch_id']:item for item in self.registry.records()}
            roots={}
            generations={}
            for shard in shards:
                launch=shard.launch
                record=records[launch.launch_id]
                if (record['launch']!=asdict(launch) or launch.role!='shard'
                        or launch.wave_id!='wave-'+str(plan['wave_index'])
                        or record['owner']!=asdict(shard.owner) or record['binding'] is None
                        or launch.worker_id in roots):
                    raise ValueError('unregistered instance')
                root=Path(launch.owned_root)
                if root!=self.root/launch.wave_id/launch.worker_id/('g'+str(launch.launch_generation)):
                    raise ValueError('private root')
                roots[launch.worker_id]=root
                generations[launch.worker_id]=launch.launch_generation
            rows=outcome['case_results']
            if type(rows) is not list or not rows or not roots:
                raise ValueError('missing cases')
            scene_order=plan['scene_ids']
            if (type(scene_order) is not list or not scene_order or len(set(scene_order))!=len(scene_order)
                    or len(rows)!=len(scene_order)):
                raise ValueError('denominator')
            verified={}
            for row in rows:
                if (type(row) is not dict or set(row)!={'scene_id','worker_id','location'}
                        or row['scene_id'] not in scene_order or row['scene_id'] in verified
                        or row['worker_id'] not in roots):
                    raise ValueError('case identity')
                refs=self.case_inputs[row['scene_id']]
                paths={name:validate_file_ref(ref) for name,ref in refs.items()}
                proof=verify_coordinator_commit(coordinator_root,location=row['location'],
                    scope=paths['scope'],inputs_manifest=paths['inputs_manifest'],worker_roots=roots)
                if (proof['identity']['point_id']!=row['scene_id']
                        or proof['identity']['worker_id']!=row['worker_id']
                        or proof['identity']['worker_generation']!=generations[row['worker_id']]):
                    raise ValueError('commit identity')
                # Keep FAILED Teacher and INVALID/QC-failed data in the frozen
                # denominator. Qualification is a separate all-case report.
                verified[row['scene_id']]=dict(scene_id=row['scene_id'],worker_id=row['worker_id'],
                    location=row['location'],proof=proof)
            if set(verified)!=set(scene_order):
                raise ValueError('missing scene')
            return dict(wave_index=plan['wave_index'],scene_count=len(scene_order),
                coordinator_root=str(coordinator_root),case_results=[verified[name] for name in scene_order])
        except (OSError,ValueError,TypeError,KeyError,AttributeError) as error:
            raise ValueError('CONTAINER_WAVE_COMMIT_READBACK_INVALID') from error
