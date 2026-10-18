"""Synthetic archive data only; no production evidence is read by these fixtures."""
import base64
import hashlib
import json
from pathlib import Path

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')

class ArchiveFixture:
    def __init__(self, parent):
        self.root = parent / 'registry'
        self.package = self.root / 'collection'
        self.package.mkdir(parents=True)
        self.supporting = self.root / 'supporting'
        self.supporting.mkdir()
        self.outputs = {}
        scenes=[]; committed=[]; scenarios=[]
        for i, (split, state, count) in enumerate([('train','VALID',5),('validation','VALID',7),('train','FAULT',0),('offline_test','MISSING',0)]):
            scene=f'frm-{i:03d}'
            scenarios.append(dict(scene_id=scene, split=split, seed=200+i, cup_position_world_m=[0.01,-0.3,0.165]))
            attempts=[]
            if count:
                out=self.package/'processing'/scene/'proc-1';self.outputs[scene]=out
                ep=out/'episode';(ep/'frames').mkdir(parents=True);(ep/'audit').mkdir()
                write_json(ep/'seal.json',dict(status='PASSED',qc_passed=True,pick_place_validation_success=True,record_count=count,committed=False,stopped_confirmed=True))
                write_json(out/'processed-result.json',dict(act_data_status='VALID',export_eligible=True,proc_attempt=1,qc_report_path='qc-report.json'))
                write_json(out/'qc-report.json',dict(status='PASS',counts=dict(records=count),checks=[]))
                rows=[]
                for row in range(count):
                    for camera in ['head','wrist']:(ep/'frames'/f'{row:06d}-{camera}.png').write_bytes(PNG)
                    rows.append(dict(action=[float(row)]*6,observation=dict(state=[float(row)]*8,sim_time_s=36.2+row/10,head_png=f'frames/{row:06d}-head.png',wrist_png=f'frames/{row:06d}-wrist.png'),audit=dict(secret='large audit payload')))
                (ep/'records.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
                (ep/'audit/events.jsonl').write_text(''.join(json.dumps(dict(row=r,text='中文'))+'\n' for r in range(8)))
                attempts=[dict(outcome='VALID',reason=None,proc_attempt=1,processor_id='p00',output_dir=str(out))]
                committed.append(dict(scene_id=scene,collection_evidence=dict(processing_output=str(out),inputs_manifest=str(self.package/'inputs/frozen/inputs-manifest.json'))))
            recording=[]
            if i==1:
                recording.append(dict(recording_round=0,wave_index=0,worker_id='w01',state='PROCESSED',reason='bad first recording',attempts=[dict(outcome='INVALID',reason='QC_BAD',proc_attempt=1,processor_id='p00',output_dir=str(self.package/'processing/old'))]))
            recording.append(dict(recording_round=int(i==1),wave_index=int(i==1),worker_id='w00',state='PROCESSED' if count else state,reason=None if count else 'not recorded',attempts=attempts,phase1=dict(teacher_task_result='PASS') if count else None))
            scenes.append(dict(scene_id=scene,state='PROCESSED' if count else state,reason=None if count else 'not recorded',attempts=attempts,recording_round=int(i==1),recording_attempts=recording,phase1=dict(teacher_task_result='PASS') if count else None))
        self.index=dict(schema_version=3,campaign_id='synthetic',scene_count=4,collected_tasks=[],committed_episodes=committed)
        self.campaign=dict(schema_version=2,scene_count=4,scenes=scenes,retry=dict(rounds_run=1,recovered=1,decisions=[dict(recording_round=1,status='RUN'),dict(recording_round=2,status='SKIPPED')]))
        write_json(self.package/'collection-index.json',self.index)
        write_json(self.package/'host/campaign-result.json',self.campaign)
        write_json(self.package/'inputs/frozen/inputs-manifest.json',dict(scene_manifest=dict(path='scene_manifest/scenes.json'),source_commit='source-commit'))
        write_json(self.package/'inputs/frozen/scene_manifest/scenes.json',dict(scenarios=scenarios))
        self.seal();self.seal(self.supporting)
        write_json(self.root/'SEALED-ROOTS.json',dict(kind='SEALED_ROOTS_REGISTRY',roots=[json.loads((self.package/'SEALED.json').read_text())]))

    def seal(self, package=None):
        package=package or self.package
        entries=[]
        for p in sorted(package.rglob('*')):
            if p.is_file() and p.name!='SEALED.json':
                raw=p.read_bytes();entries.append(dict(path=str(p.relative_to(package)),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        manifest=package.with_name(package.name+'.seal-manifest.jsonl')
        manifest.write_text(''.join(json.dumps(r)+'\n' for r in entries))
        write_json(package/'SEALED.json',dict(kind='SEALED_EVIDENCE_ROOT',root=str(package),sealed_at='2026-10-17T00:00:00Z',reason='synthetic',files=len(entries),bytes=sum(r['bytes'] for r in entries),manifest=str(manifest),manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest()))
        return entries
