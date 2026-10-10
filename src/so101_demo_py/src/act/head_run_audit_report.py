"""Split-result reports with an atomic, last-published completion marker."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import time

from .head_run_reader import AuditToolError, normalized, open_regular


def summary(result):
    return ' '.join([f"integrity={result['integrity']['status']}",
        f"search={result['search']['outcome']}",
        f"execution_checks={result['execution_checks']['status']}",
        f"stop={result['stop']['status']}",f"exit_cleanup={result['exit_cleanup']['status']}"])


def markdown(result):
    lines=['# Head Search basic offline review','',summary(result),'',
        'Tool rc0 means complete publication and integrity PASS; execution and Stop results remain separate.',
        '',f"Producer profile: {result['producer_profile'] or 'UNKNOWN'}",'',
        '## Rule coverage','', '| Rule | Verdict |','| --- | --- |']
    for rule,item in result['coverage']['rules'].items():
        lines.append(f"| {rule} | {item['verdict']} |")
    lines+=['','## Findings','']
    if not result['findings']:lines.append('No finding in the assessed basic checks.')
    for finding in result['findings']:
        location=finding['evidence']
        lines.append(f"- {finding['severity']} {finding['category']} `{finding['code']}`: "
                     f"{location['path']} line={location['line']} sequence={location['event_sequence']}; "
                     f"affects={','.join(finding['affected_results']) or 'diagnostics'}")
    lines+=['','## Capabilities outside this review','']
    for name,value in result['coverage']['capabilities'].items():lines.append(f'- {name}={value}')
    lines+=['','This report supports only the listed checks over saved inputs. It does not grant Head or ACT qualification.','']
    return '\n'.join(lines)


def auditor_provenance():
    from . import head_run_audit, head_run_reader
    from ..cli import head_search_audit
    paths=[Path(__file__),Path(head_run_audit.__file__),Path(head_run_reader.__file__),
           Path(head_search_audit.__file__)]
    refs=[]
    for path in paths:
        sha=hashlib.sha256();size=0
        with open_regular(path.absolute()) as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):
                size+=len(block);sha.update(block)
        refs.append(dict(module_path=str(path),size=size,sha256=sha.hexdigest()))
    return dict(version=1,python=sys.executable,modules=refs)


def invalidate_changed_results(reader,result,readback):
    """A tainted or missing prerequisite never supplies a semantic PASS."""
    result['integrity']['status']=reader.integrity_status
    state={'PASS':'HOLDS','FAIL':'VIOLATED','INCOMPLETE':'UNKNOWN'}[reader.integrity_status]
    result['coverage']['rules']['HFA-001']['verdict']=state
    result['findings']=reader.findings+[x for x in result['findings'] if x not in reader.findings]
    affected = set()
    all_rules = set(result['coverage']['rules']) - {'HFA-001'}
    dependency_rules = {
        'manifest.json': all_rules, 'events.jsonl': all_rules,
        'completion.json': {'HFA-010', 'HFA-011'},
        'source_manifest': all_rules, 'freeze_receipt': all_rules,
        'development_config': {'HFA-004', 'HFA-005', 'HFA-006', 'HFA-007', 'HFA-008', 'HFA-009'},
        'local_policy': {'HFA-006', 'HFA-007', 'HFA-009'},
        'camera_geometry': {'HFA-005', 'HFA-008'},
        'controller_config': {'HFA-004'},
        'execution_inputs': {'HFA-002'}, 'inputs': {'HFA-002'},
        'execution_receipt': {'HFA-002', 'HFA-010'},
        'launcher': {'HFA-010'}, 'postflight': {'HFA-010'}, 'owned_postflight': {'HFA-010'},
    }
    references = {name: str(normalized(reader.run_root / name))
                  for name in ('manifest.json', 'events.jsonl', 'completion.json')}
    references['execution_receipt'] = str(normalized(reader.execution_receipt))
    manifest = reader.documents.get('manifest.json') or {}
    receipt = reader.external.get('execution_receipt') or {}
    for source in (manifest, manifest.get('refs', {}), receipt.get('refs', {})):
        for name, reference in source.items():
            if name in dependency_rules and isinstance(reference, dict) and 'path' in reference:
                references[name] = str(normalized(reference['path']))
    for name, path in references.items():
        if path in reader.tainted:
            affected.update(dependency_rules[name])
    if not (reader.run_root / 'events.jsonl').exists() or \
            readback['run_inventory_before'] != readback['run_inventory_after']:
        affected.update(all_rules)
    # Saved process/graph stdout belongs only to the owned-cleanup evidence.
    if any(path.endswith(('/ps.stdout', '/graph.stdout')) for path in reader.tainted):
        affected.add('HFA-010')
    for rule in affected:
        coverage = result['coverage']['rules'][rule]
        if coverage['verdict'] not in ('VIOLATED', 'UNKNOWN'):
            coverage['verdict'] = 'UNKNOWN'
            coverage['checks'].append(dict(verdict='UNKNOWN', code='INPUT_CHANGED_DEPENDENCY', evidence=None))
    if 'HFA-008' in affected or 'HFA-011' in affected:
        result['search']['outcome'] = 'UNKNOWN'
    groups = {'execution_checks': list(all_rules - {'HFA-009', 'HFA-010'}),
              'stop': ['HFA-009'], 'exit_cleanup': ['HFA-010']}
    for key, rules in groups.items():
        verdicts = {result['coverage']['rules'][rule]['verdict'] for rule in rules}
        if 'VIOLATED' in verdicts:
            result[key]['status'] = 'FAIL'
        elif 'UNKNOWN' in verdicts:
            result[key]['status'] = 'UNKNOWN'


def open_new_output(reader,output,*,auditor=None):
    output=normalized(output)
    if not output.is_relative_to(reader.evidence_root):
        raise AuditToolError('OUTPUT_ESCAPES_EVIDENCE_ROOT')
    protected=[reader.run_root]+[Path(entry['path']).parent for entry in reader.files.values()]
    for module in (auditor or {}).get('modules', []):
        path = normalized(module['module_path'])
        protected.append(path.parent)
        for parent in path.parents:
            if parent.name == 'install' and parent.is_relative_to(reader.evidence_root):
                protected.append(parent.parent)
                break
    for path in protected:
        if output==path or output.is_relative_to(path) or path.is_relative_to(output):
            raise AuditToolError('OUTPUT_CONFLICTS_WITH_INPUT_DIRECTORY')
    descriptor=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        parts=output.parts[1:]
        for index,part in enumerate(parts):
            leaf=index==len(parts)-1
            try:
                os.mkdir(part,mode=0o700,dir_fd=descriptor)
            except FileExistsError:
                if leaf:raise AuditToolError('OUTPUT_ALREADY_EXISTS')
            next_descriptor=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
            os.fsync(descriptor)
            os.close(descriptor);descriptor=next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def atomic_file(directory,name,data):
    temporary='.'+name+'.pending'
    descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
    try:
        with os.fdopen(descriptor,'wb',closefd=False) as stream:
            stream.write(data);stream.flush();os.fsync(descriptor)
    finally:os.close(descriptor)
    os.replace(temporary,name,src_dir_fd=directory,dst_dir_fd=directory)
    try:os.fsync(directory)
    except BaseException:
        # Retain unconfirmed bytes under a non-completion name; no evidence deletion.
        if name=='audit-completion.json':
            os.replace(name,'audit-completion.unconfirmed.json',src_dir_fd=directory,dst_dir_fd=directory)
        raise
    return dict(path=name,size=len(data),sha256=hashlib.sha256(data).hexdigest())


def json_bytes(value):
    return (json.dumps(value,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')


def publish_report(reader,result,output):
    readback=reader.readback()
    invalidate_changed_results(reader,result,readback)
    result['auditor']=auditor_provenance()
    result['input_refs']=dict(run_root=str(reader.run_root),execution_receipt=str(reader.execution_receipt),
        execution_receipt_sha256=reader.receipt_sha256,seal=reader.evidence(reader.run_root/'seal.json'))
    result['audit_metadata']=dict(created_utc_ns=time.time_ns(),output_root=str(output))
    directory=open_new_output(reader,output,auditor=result['auditor'])
    try:
        result['report']['status']='COMPLETE'
        refs=[]
        for name,data in [('review.json',json_bytes(result)),('review.md',markdown(result).encode('utf-8')),
                          ('metrics.json',json_bytes(result['metrics'])),('input-readback.json',json_bytes(readback))]:
            refs.append(atomic_file(directory,name,data))
        # Publication only follows final input readback; no valid marker on interruption.
        final=reader.readback()
        if final!=readback:
            raise AuditToolError('INPUT_CHANGED_DURING_PUBLICATION')
        atomic_file(directory,'audit-completion.json',json_bytes(dict(audit_schema_version=1,
            status='COMPLETE',files=refs,integrity_status=result['integrity']['status'])))
    except BaseException:
        result['report']['status']='NOT_COMPLETED'
        raise
    finally:os.close(directory)
    return result
