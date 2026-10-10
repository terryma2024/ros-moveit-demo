"""Complete v2 export-port fixtures with an explicit commit-reader double, never formal live proof."""
from dataclasses import asdict
import copy
import hashlib
import json
import re
import struct
import zlib

from so101_demo.act.collection_scope import write_collection_scope
from so101_demo.act.episode_qc import write_qc_report,read_qc_report
from test_act_qc_report_publication import report
from test_act_seal_and_downgrade import lease


#: the content of a committed episode as the trainer may read it: rows of an observation (joint state, two images) and an action
ROW_CONTENT=dict(frames=1,rows=[dict(observation=dict(sim_time_s=0.,state=[0.]*8,head_png='frames/000000-head.png',wrist_png='frames/000000-wrist.png'),
    action=[0.]*6)])


_FRAME_NAME=re.compile(r'frames/\d{6}-(head|wrist)\.png')


def tiny_png(width=2,height=2,seed=0):
    """A real RGB PNG (8-bit, colour type 2) built with zlib only, so the ordinary interpreter needs no imaging library."""
    rows=b''.join(b'\x00'+bytes((seed+3*x+7*y+channel*41)%256 for x in range(width) for channel in range(3)) for y in range(height))
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')


def _observations(content):
    if isinstance(content.get('rows'),list):
        return [row['observation'] for row in content['rows'] if isinstance(row,dict) and isinstance(row.get('observation'),dict)]
    return [content['observation']] if isinstance(content.get('observation'),dict) else []


def write_sealed_episode(location,content,*,frame=None):
    """A minimal recorder directory (`episode/seal.json`, `records.jsonl`, `frames/*.png`) holding exactly the rows of ``content``.

    Names that are not recorder frame names (the refusal tests use `h`) are not written. ``frame(name)`` returns the PNG bytes."""
    root=location/'episode';(root/'frames').mkdir(parents=True)
    files={}
    rows=content.get('rows') if isinstance(content.get('rows'),list) else []
    for observation in _observations(content):
        for key in ('head_png','wrist_png'):
            name=observation.get(key)
            if isinstance(name,str) and _FRAME_NAME.fullmatch(name) and name not in files:
                data=frame(name) if frame is not None else tiny_png(seed=len(files))
                (root/name).write_bytes(data)
                files[name]=dict(sha256=hashlib.sha256(data).hexdigest(),size=len(data))
    records=b''.join(json.dumps(dict(row,audit={'contacts':[],'release_epoch':0}),sort_keys=True).encode()+b'\n' for row in rows if isinstance(row,dict))
    (root/'records.jsonl').write_bytes(records)
    files['records.jsonl']=dict(sha256=hashlib.sha256(records).hexdigest(),size=len(records))
    seal=dict(kind='ACT_EPISODE_SEAL',schema_version=2,status='PASSED',record_count=len(rows),files=dict(sorted(files.items())))
    seal_bytes=json.dumps(seal,sort_keys=True,separators=(',',':')).encode()+b'\n'
    (root/'seal.json').write_bytes(seal_bytes)
    return hashlib.sha256(seal_bytes).hexdigest()


def complete_export_entries(tmp_path,monkeypatch,scene_ids=('act-1','act-2'),proof_overrides=None,teacher_manifests=None,content=None,
        contents=None,splits=None,frame=None):
    from so101_demo.act import result_store
    records=[];proofs={}
    for index,scene_id in enumerate(scene_ids):
        root=tmp_path/f'controlled-v2-export-{index}';root.mkdir()
        scope=root/'scope.json';inputs=root/'inputs-manifest.json'
        scope_doc=dict(kind='ACT_COLLECTION_SCOPE',schema_version=1,mode='formal',scene_id=scene_id,seed=0,inputs_sha256='a'*64)
        write_collection_scope(scope_doc,scope)
        inputs.write_text(json.dumps(dict(mode='formal',inputs_sha256='a'*64)))
        location=root/'sealed';location.mkdir()
        episode_content=copy.deepcopy((contents or {}).get(scene_id)) if contents and scene_id in contents else (
            copy.deepcopy(ROW_CONTENT) if content is None else copy.deepcopy(content))
        seal_sha256=write_sealed_episode(location,episode_content,frame=frame)
        qc=report();qc['identity'].update(mode='formal',scene_id=scene_id);qc['episode_seal_sha256']=seal_sha256
        # the Teacher manifest of the sealed result, bound by the QC reference check (default: a policy v2 manifest, which has no summary)
        teacher_manifest=(teacher_manifests or {}).get(scene_id,{'schema':'so101-dynamic-mujoco-execute-v2'})
        (location/'dynamic').mkdir()
        (location/'dynamic'/'dynamic-execute-manifest.json').write_text(json.dumps(teacher_manifest,sort_keys=True))
        qc['checks']['teacher_reference_consistency']['details']['teacher_manifest_sha256']=hashlib.sha256(
            (location/'dynamic'/'dynamic-execute-manifest.json').read_bytes()).hexdigest()
        qc.update(scope_sha256=hashlib.sha256(scope.read_bytes()).hexdigest(),inputs_sha256='a'*64)
        write_qc_report(qc,location/'qc-report.json')
        qc_hash=hashlib.sha256((location/'qc-report.json').read_bytes()).hexdigest()
        identity={key:value for key,value in asdict(lease()).items() if key not in ('lease_issued_monotonic_s','lease_deadline_monotonic_s')}
        binding=dict(qc_report_sha256=qc_hash,episode_seal_sha256=qc['episode_seal_sha256'],inputs_sha256='a'*64,
            scope_sha256=qc['scope_sha256'],audit_manifest_sha256=qc['audit_manifest_sha256'],collection_mode='formal')
        # the Teacher passed and the independent data QC passed: the only combination that is exportable (schema 3)
        data=dict(teacher_execution_status='COMPLETED',teacher_task_result='PASS',act_data_status='PENDING_QC',
            act_data_reason=None,act_data_qc='PASS',export_eligible=True)
        receipt=dict(status='PASSED',sha256='c'*64,location=str(location),recovery_deadline_monotonic_s=30.,**binding,**data)
        proof=dict(kind='ACT_COORDINATOR_COMMIT_PROOF',schema_version=1,status='PASS',result_status='PASSED',
            result_schema_version=3,**{key:data[key] for key in ('teacher_execution_status','teacher_task_result',
                'act_data_status','act_data_qc','export_eligible')},
            identity={**identity,'location':str(location)},receipt=receipt,**binding,result_sha256='c'*64,
            commit_sequence=7,commit_frame_sha256='d'*64,journal_terminal_sha256='e'*64,aggregate_sha256='f'*64)
        proof.update((proof_overrides or {}).get(scene_id,{}))
        coordinator=root/'coordinator';coordinator.mkdir()
        content_path=root/'content.json';content_path.write_text(json.dumps(episode_content))
        record=dict(kind='ACT_COMMITTED_EPISODE',schema_version=2,scene_id=scene_id,status='PASSED',split=(splits or {}).get(scene_id,'train'),
            journal_sha256='d'*64,verifier_sha256='c'*64,content=episode_content,
            content_path=str(content_path),content_sha256=hashlib.sha256(content_path.read_bytes()).hexdigest(),
            collection_evidence=dict(coordinator_root=str(coordinator),result_location=str(location),
                scope_path=str(scope),inputs_manifest=str(inputs),receipt=receipt))
        records.append(record)
        proofs[str(location)]=(coordinator,scope,inputs,proof,qc)
    def reader(coordinator_root,*,location,scope,inputs_manifest):
        expected_root,expected_scope,expected_inputs,proof,qc=proofs[str(location)]
        if (coordinator_root,scope,inputs_manifest)!=(expected_root,expected_scope,expected_inputs):
            raise ValueError('controlled original locator mismatch')
        if read_qc_report(location/'qc-report.json')!=qc or hashlib.sha256(scope.read_bytes()).hexdigest()!=proof['scope_sha256']:
            raise ValueError('controlled original evidence mismatch')
        return copy.deepcopy(proof)
    monkeypatch.setattr(result_store,'verify_coordinator_commit',reader)
    return tuple(records)
