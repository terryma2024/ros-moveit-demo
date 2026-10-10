"""Serial installed Head-only attempts and final-result evidence extraction."""
from copy import deepcopy
import hashlib
import json
import os
import shutil
from pathlib import Path
import signal
import struct
import subprocess
import time

from so101_demo.act.head_search_functional_acceptance import (
    calculate_final_yaw, classify_functional_case)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def reference(path):
    path = Path(path)
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def select_terminal_image(events, result):
    source = round(result['timestamp']*1e9)
    rows = [row for row in events if row['kind'] == 'IMAGE_PAYLOAD'
            and row['record']['source_ns'] == source]
    if len(rows) != 1:
        raise ValueError('HEAD_FUNCTIONAL_TERMINAL_IMAGE_MISSING_OR_DUPLICATE')
    return rows[0]


def _validated_proof(proof):
    # Reuse the strict wire predicate on the exact recorded fields.
    from so101_demo.adapters.act.head_control_protocol import _PROOF, _FIELDS, parse_proof_record
    if type(proof) is not dict:
        raise ValueError('HEAD_FUNCTIONAL_PROOF_ABSENT')
    values = []
    for key in _FIELDS:
        value = 0 if key.startswith('_reserved') else proof[key]
        if type(value) is not int:
            raise ValueError('HEAD_FUNCTIONAL_PROOF_TYPE')
        values.append(value)
    return parse_proof_record(_PROOF.pack(*values))


def _startup_complete(facts):
    from so101_demo.adapters.act.head_control_protocol import identity_fields
    protocol = facts['startup_protocol']
    if protocol.get('seal_verified') is not True:
        return False
    def one(kind):
        rows = protocol[kind]
        if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
            raise ValueError('HEAD_FUNCTIONAL_STARTUP_CARDINALITY')
        return rows[0]
    bootstrap = one('BOOTSTRAP_IDENTITY')
    generation = bootstrap['generation']
    if type(generation) is not int or generation <= 0:
        return False
    scope = identity_fields(bootstrap, generation)
    owner = bootstrap['native_owner']
    if (type(owner) is not dict or set(owner) != {'uid', 'pid', 'start_ticks'}
            or any(type(value) is not int for value in owner.values())
            or not 0 <= owner['uid'] < 2**32 or not 0 < owner['pid'] < 2**31
            or not 0 < owner['start_ticks'] < 2**64
            or bootstrap.get('status') != 'AVAILABLE'
            or bootstrap.get('ack_validated') is not True):
        return False
    statuses = protocol['PREARM_STATUS']
    if type(statuses) is not list or not statuses:
        return False
    ready_id = None
    for index, status in enumerate(statuses):
        if (identity_fields(status, generation) != scope or status.get('native_owner') != owner
                or status.get('gate_reason') != 0 or type(status.get('stored_generation')) is not int
                or not 0 <= status['stored_generation'] < generation):
            return False
        proof = _validated_proof(status['proof'])
        last = index == len(statuses)-1
        expected = 'READY' if last else 'NOT_READY'
        if (status.get('status') != expected or status.get('native_status') != (0 if last else 1)
                or (proof['wrapper_reason'] == 0) != last
                or proof['wrapper_reason'] in (7, 8)):
            return False
        if last:
            ready_id = proof['evaluation_id']
    arm = one('ARM_RESULT')
    proof = _validated_proof(arm['proof'])
    if (arm.get('status') != 'ACK' or arm.get('native_status') != 0
            or arm.get('phase') != 'NONE' or arm.get('gate_reason') != 0
            or arm.get('role') != 3 or arm.get('generation') != generation
            or arm.get('native_owner') != owner or proof['wrapper_reason'] != 0
            or proof['evaluation_id'] <= ready_id):
        return False
    close = one('NATIVE_CLOSE')
    receipt = close.get('receipt')
    if (close.get('ack') is not True or close.get('error') is not None
            or type(receipt) is not dict or receipt.get('ack_validated') is not True
            or receipt.get('status') != 'ARMED_CLOSED'
            or receipt.get('stored_generation') != generation
            or identity_fields(receipt, generation) != scope
            or receipt.get('native_owner') != owner):
        return False
    stops = protocol['CANCEL_STOP']
    if not stops or not any(row.get('raw_stop_confirmed') is True and row.get('error') is None
                            for row in stops):
        return False
    children = facts['children']
    post = facts['postflight']
    return (bool(children) and all(type(row.get('pid')) is int and row['pid'] > 0
            and type(row.get('rc')) is int and row['rc'] == 0 for row in children)
            and post.get('owner_absent') is True and post.get('graph_empty') is True
            and post.get('graph_rc') == 0)


def may_continue(facts, *, require_startup_protocol=False):
    if facts.get('stop_confirmed') is not True or facts.get('owned_children_exited') is not True:
        return False
    if not require_startup_protocol:
        return True
    try:
        return _startup_complete(facts)
    except (KeyError, TypeError, ValueError, RuntimeError, OverflowError, AttributeError, struct.error):
        return False


def summarize(cases, attempts):
    return [classify_functional_case(case, attempts.get(case['case_id'], [])) for case in cases]


def process_identity(pid):
    fields = (Path('/proc')/str(pid)/'stat').read_text().rsplit(')', 1)[1].split()
    return dict(pid=pid, started_ticks=int(fields[19]), state=fields[0])


def postflight(receipt, environment, output):
    if (type(receipt.get('actual_os_return_code')) is not int
            or type(receipt.get('ended_ns')) is not int or receipt['ended_ns'] > time.time_ns()):
        raise ValueError('HEAD_FUNCTIONAL_ACTUAL_OS_END_REQUIRED')
    output = Path(output)
    output.mkdir(exist_ok=False)
    start = time.time_ns()
    p = subprocess.run(['/opt/ros/jazzy/bin/ros2', 'node', 'list', '--no-daemon'],
        env=dict(os.environ, **environment), capture_output=True, text=True, timeout=15)
    (output/'ros-nodes.stdout').write_text(p.stdout)
    (output/'ros-nodes.stderr').write_text(p.stderr)
    owner_absent = not (Path('/proc')/str(receipt['owner']['pid'])).exists()
    result = dict(started_ns=start, ended_ns=time.time_ns(), actual_os_end_ns=receipt['ended_ns'],
        graph_rc=p.returncode, graph_empty=p.returncode == 0 and not p.stdout.strip(),
        owner_absent=owner_absent)
    write_json(output/'receipt.json', result)
    return result


def launch_installed(inputs_path, *, python, executable, output, signal_after_sdk=False):
    """No authority or ACK is supplied by this launcher; wait for the actual OS exit."""
    inputs = json.loads(Path(inputs_path).read_text())
    output = Path(output)
    output.mkdir(exist_ok=False)
    environment = dict(os.environ, **inputs['ros']['environment'])
    if not os.access(python, os.X_OK) or not os.access(executable, os.X_OK):
        raise ValueError('HEAD_FUNCTIONAL_EXECUTABLE_ABSENT')
    argv = [str(python), str(executable), 'run', '--execution-inputs', str(inputs_path)]
    start = time.monotonic()
    started_ns = time.time_ns()
    injection = None
    with (output/'stdout.log').open('xb') as stdout, (output/'stderr.log').open('xb') as stderr:
        child = subprocess.Popen(argv, env=environment, stdout=stdout, stderr=stderr,
                                 start_new_session=True)
        identity = process_identity(child.pid)
        receipt = dict(argv=argv, owner=identity, started_ns=started_ns,
            inputs=reference(inputs_path), executable=reference(executable))
        write_json(output/'launcher-start.json', receipt)
        events = Path(inputs['run_root'])/'events.jsonl'
        while child.poll() is None:
            if signal_after_sdk and injection is None and events.is_file():
                # Writer rows are newline committed; never interpret a partial row.
                rows = [json.loads(line) for line in events.read_text().splitlines(keepends=True)
                        if line.endswith('\n')]
                sdk = next((row for row in rows if row['kind'] == 'HEAD_ACTION_SDK_RETURNED'), None)
                locked = any(row['kind'] == 'SEARCH_CONTROLLER_TERMINAL'
                    and row['record']['result']['status'] == 'TARGET_LOCKED' for row in rows)
                if sdk is not None:
                    current = process_identity(child.pid)
                    if current['started_ticks'] != identity['started_ticks'] or locked:
                        raise PermissionError('HEAD_FUNCTIONAL_SIGNAL_SCOPE_INVALID')
                    occurred_ns = time.monotonic_ns()
                    os.kill(child.pid, signal.SIGTERM)
                    injection = dict(kind='signal_stop', status='PASS', before_locked=True,
                        occurred_ns=occurred_ns, sdk_sequence=sdk['sequence'],
                        goal_uuid=sdk['record']['goal_uuid'], owner=identity)
                    write_json(output/'injection.json', injection)
            time.sleep(.02)
        code = child.wait()
    receipt.update(actual_os_return_code=code, ended_ns=time.time_ns(),
                   elapsed_s=time.monotonic()-start, injection=injection)
    write_json(output/'launcher-result.json', receipt)
    return receipt


def prepare_attempt(case, baseline, output, *, identity, domain, interrupt=False):
    from so101_demo.act.head_search_campaign_scene import prepare_case_fixture
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    inputs = deepcopy(baseline)
    inputs['run'] = deepcopy(identity)
    # Matrix anchor poses are applied by the same native reset; no new defaults.
    prepared = prepare_case_fixture(case, inputs, output/'fixture', paired_truth_enabled=False)
    inputs['refs'].update(prepared['refs'])
    inputs['development_pose'] = prepared['development_pose']
    inputs.update(event_log_enabled=True, save_all_rgb_frames=False, campaign_truth_enabled=False,
        run_root=str(Path(baseline['run_root']).parent/identity['run_id']),
        snapshot_root=str(output/'snapshots'), fault_stop_probes=[])
    Path(inputs['snapshot_root']).mkdir(exist_ok=False)
    if interrupt and case['condition_class'] == 'fast_interruption':
        inputs['fault_stop_probes'] = ['CAMERA_LOSS_AFTER_FIRST_SDK_RETURN']
    environment = inputs['ros']['environment']
    session = identity['session_id']
    # The private reservation scope lives under the root the baseline declares; no host constant.
    reservation_root = environment.get('SO101_ACT_RESERVATION_ROOT')
    if type(reservation_root) is not str or not Path(reservation_root).is_absolute():
        raise ValueError('HEAD_FUNCTIONAL_RESERVATION_ROOT_REQUIRED')
    ipc = Path(reservation_root)/'ipc'/hashlib.sha256(session.encode()).hexdigest()[:16]
    assert not ipc.exists()
    environment.update(ROS_DOMAIN_ID=str(domain), GZ_PARTITION=session,
        SO101_SIMULATION_SESSION_ID=session, ROS_HOME=str(output/'ros-home'),
        ROS_LOG_DIR=str(output/'ros-log'),
        ROS_WORKSPACE=str(Path(reservation_root)/session),
        SO101_ACT_CONTROLLER_RESERVATION_DIR=str(ipc))
    inputs['ros']['domain_id'] = domain
    # Native identity is provisioned by the existing authority from run fields
    # and session environment. Controller parameters stay byte-identical.
    path = output/'execution-inputs.json'
    write_json(path, inputs)
    # Read-only closed parsing catches stale paths before creating any resource.
    from so101_demo.act.head_execution_inputs import HeadExecutionInputs
    HeadExecutionInputs.parse(path)
    return path


def extract_attempt(inputs_path, receipt, output):
    """Verify retained originals, then derive pictures/geometry with no simulation step."""
    import mujoco
    import numpy as np
    from PIL import Image
    from so101_demo.adapters.act.physics import model_sha256
    output = Path(output)
    inputs = json.loads(Path(inputs_path).read_text())
    run = Path(inputs['run_root'])
    facts = dict(identity=inputs['run'], actual_os_return_code=receipt['actual_os_return_code'],
                 evidence_root=str(run), stop_confirmed=None, owned_children_exited=None,
                 scene_verified=False, original_terminal='UNPROVEN', business_rc=None)
    if not (run/'seal.json').is_file():
        write_json(output/'facts.json', facts)
        return facts
    seal = json.loads((run/'seal.json').read_text())
    for ref in seal['files']:
        path = run/ref['path']
        if path.is_symlink() or not path.is_relative_to(run):
            raise ValueError('HEAD_FUNCTIONAL_ARTIFACT_PATH')
        raw = path.read_bytes()
        if len(raw) != ref['size'] or hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError('HEAD_FUNCTIONAL_SEAL_MISMATCH')
    sealed = {ref['path'] for ref in seal['files']}
    if not {'events.jsonl', 'completion.json'} <= sealed:
        raise ValueError('HEAD_FUNCTIONAL_EVENTS_UNSEALED')
    events = [json.loads(line) for line in (run/'events.jsonl').open()]
    if any(row['run'] != inputs['run'] for row in events):
        raise ValueError('HEAD_FUNCTIONAL_EVENT_IDENTITY')
    completion = json.loads((run/'completion.json').read_text())
    facts['business_rc'] = completion['business_return_code']
    def records(kind):
        return [row['record'] for row in events if row['kind'] == kind]
    facts['startup_protocol'] = dict(seal_verified=True, **{
        kind: records(kind) for kind in ('BOOTSTRAP_IDENTITY', 'PREARM_STATUS',
            'ARM_RESULT', 'NATIVE_CLOSE', 'CANCEL_STOP')})
    facts['stop_confirmed'] = (any(row.get('ack') is True and row.get('error') is None
        for row in records('NATIVE_CLOSE')) and any(row.get('raw_stop_confirmed') is True
        for row in records('CANCEL_STOP')))
    exits = records('EXECUTION_CHILD_RETIREMENT')
    children = exits[-1]['children'] if exits else []
    post = postflight(receipt, inputs['ros']['environment'], output/'postflight')
    facts['owned_children_exited'] = (bool(children) and all(row['rc'] == 0
        and not (Path('/proc')/str(row['pid'])).exists() for row in children)
        and post['graph_empty'] and post['owner_absent'])
    facts['children'] = children
    facts['postflight'] = post
    model = mujoco.MjModel.from_xml_path(inputs['refs']['scene']['path'])
    compiled = model_sha256(model)
    reset = records('SCENE_RESET_VERIFIED')
    fixture = json.loads(Path(inputs['refs']['scenario_fixture']['path']).read_text())
    verified = [row for row in reset if row['simulation_session_id'] == inputs['run']['session_id']
        and row['reset_epoch'] == 1 and row['model_sha256'] == compiled
        and row['verified_pose'] == inputs['development_pose']]
    if len(verified) == 1:
        body_ok = True
        for name, pose in fixture['reset_free_bodies'].items():
            joint = model.body_jntadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)]
            address = model.jnt_qposadr[joint]
            body_ok &= np.allclose(verified[0]['qpos'][address:address+3], pose['xyz'], atol=1e-9)
        facts['scene_verified'] = bool(body_ok)
    facts['scene'] = dict(model_sha256=compiled, fixture=inputs['refs']['scenario_fixture'],
        reset=verified, lights=dict(diffuse=model.light_diffuse.tolist(),
                                  specular=model.light_specular.tolist()))
    terminals = records('SEARCH_CONTROLLER_TERMINAL')
    result = terminals[-1]['result'] if terminals else None
    if result is not None:
        facts['original_terminal'] = result['status']
        facts['original_result'] = result
        facts['bounded_search_completed'] = result['status'] == 'TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL'
    elif records('EXECUTION_OPERATOR_TERMINAL'):
        facts['original_terminal'] = records('EXECUTION_OPERATOR_TERMINAL')[-1]['status']
    elif records('FAULT'):
        facts['original_terminal'] = 'FAULT'
        facts['fault'] = records('FAULT')[-1]
    injection = receipt.get('injection')
    cuts = [row for row in events if row['kind'] == 'CAMPAIGN_CAMERA_DELIVERY_CUT']
    if cuts:
        cut = cuts[0]
        sdk = [row for row in events if row['kind'] == 'HEAD_ACTION_SDK_RETURNED'
               and row['record']['goal_uuid'] == cut['record']['goal_uuid']]
        proved = bool(sdk) and sdk[0]['record']['callback_wall_ns'] <= cut['record']['occurred_ns']
        facts['injection'] = dict(kind='camera_loss', status='PASS' if proved else 'UNKNOWN',
            before_locked=not terminals, cut=cut, sdk=sdk)
    elif injection is not None:
        facts['injection'] = injection
    images = [row for row in events if row['kind'] == 'IMAGE_PAYLOAD']
    observations = records('LIVE_STOPPED_OBSERVATION_FINISHED')
    inference_sources = [row['record']['source_ns'] for row in observations
                         if row['record'].get('inference_performed') is True]
    saved_sources = [row['record']['source_ns'] for row in images]
    facts['save_mode_verified'] = sorted(saved_sources) == sorted(inference_sources)
    facts['image_count'], facts['inference_count'] = len(images), len(inference_sources)
    def export(row, name):
        metadata = row['record']
        artifact = row['artifact_refs'][0]
        raw = (run/artifact['path']).read_bytes()
        if artifact['sha256'] != metadata['payload_sha256']:
            raise ValueError('HEAD_FUNCTIONAL_IMAGE_DIGEST')
        pixels = np.frombuffer(raw, dtype=np.uint8).reshape(metadata['height'], metadata['step'])
        pixels = pixels[:, :metadata['width']*3].reshape(metadata['height'], metadata['width'], 3)
        if metadata['encoding'] == 'bgr8': pixels = pixels[:, :, ::-1]
        elif metadata['encoding'] != 'rgb8': raise ValueError('HEAD_FUNCTIONAL_IMAGE_ENCODING')
        path = output/(name+'.png')
        Image.fromarray(pixels).save(path)
        return dict(path=str(path), source_ns=metadata['source_ns'],
            payload_sha256=metadata['payload_sha256'], original_artifact=artifact,
            original_event_sequence=row['sequence'], encoding=metadata['encoding'])
    if images: facts['first_detection_image'] = export(images[0], 'first-detection')
    if result is not None and result['status'] == 'TARGET_LOCKED':
        final_image = select_terminal_image(events, result)
        facts['final_image'] = export(final_image, 'final')
        stamp = facts['final_image']['source_ns']
        facts.update(final_source_ns=stamp, final_yaw_rad=result['neck_yaw_rad'],
                     final_payload_sha256=facts['final_image']['payload_sha256'])
        states = [row for row in records('SCENE_STATE') if row['reset_epoch'] == 1
                  and row['simulation_session_id'] == inputs['run']['session_id']]
        left = [row for row in states if round(row['simulation_time_s']*1e9) <= stamp]
        right = [row for row in states if round(row['simulation_time_s']*1e9) >= stamp]
        if left and right:
            lo = max(left, key=lambda row: row['simulation_time_s'])
            hi = min(right, key=lambda row: row['simulation_time_s'])
            geometry = [calculate_final_yaw(model, row, facts['final_yaw_rad']) for row in (lo, hi)]
            stable = np.max(np.abs(np.array(geometry[0]['cup_pose'])-geometry[1]['cup_pose'])) <= 1e-5
            facts['geometry'] = dict(geometry[0],
                absolute_error_deg=max(row['absolute_error_deg'] for row in geometry),
                actual_pose_stable=bool(stable), bracket_states=[lo, hi],
                time_relation='Actual states bracket the image; no exact-stamp state or interpolation claimed')
        facts['visual'] = dict(status='PENDING', reviewed_payload_sha256=facts['final_payload_sha256'])
    paths = [path for path in run.rglob('*') if path.is_file()]
    facts['storage'] = dict(logical_bytes=sum(path.stat().st_size for path in paths),
        allocated_bytes=sum(path.stat().st_blocks*512 for path in paths),
        free_bytes=os.statvfs(run).f_bavail*os.statvfs(run).f_frsize)
    write_json(output/'facts.json', facts)
    return facts


def run_case(case, baseline, *, output, prefix, python, executable, domain,
             generation_base, minimum_free_bytes, require_startup_protocol=False):
    """A faulted/unknown Stop or cleanup stops the serial campaign immediately."""
    facts = []
    for index in range(case['expected_attempt_count']):
        if shutil.disk_usage(output.parent).free < minimum_free_bytes:
            break
        token = f"{prefix}-{case['seed']}-{index+1}"
        identity = dict(run_id=token, session_id=token, epoch=token+'-epoch',
                        generation=generation_base+2*(case['seed']-900000)+index+1)
        attempt = output/f'attempt-{index+1}'
        path = prepare_attempt(case, baseline, attempt, identity=identity, domain=domain,
                               interrupt=index == 0)
        write_json(attempt/'plan.json', dict(case=case, identity=identity,
            lifecycle='OWNED_FRESH_ATTEMPT', source_commit='fcee299deb6953e683f81176052edd97b003b2df',
            install_executable=str(executable), ros_domain_id=domain, gz_partition=token,
            save_all_rgb_frames=False, campaign_truth_enabled=False,
            acceptance='Reviewed original final image and actual MJCF yaw error <=5deg; safe Stop and exit'))
        receipt = launch_installed(path, python=python, executable=executable,
            output=attempt/'installed-run', signal_after_sdk=(index == 0
                and case['condition_class'] == 'reacquire_after_stop'))
        current = extract_attempt(path, receipt, attempt)
        facts.append(current)
        print(json.dumps(dict(case=case['case_id'], attempt=index+1,
            terminal=current['original_terminal'], safe=may_continue(current, require_startup_protocol=require_startup_protocol),
            saved=current.get('image_count'), geometry=current.get('geometry', {}).get('absolute_error_deg'))),
            flush=True)
        if not may_continue(current, require_startup_protocol=require_startup_protocol):
            break
    return facts


def main(argv=None):
    import argparse
    from collections import Counter
    from so101_demo.act.head_search_campaign import load_cases
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--matrix', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--python', required=True)
    parser.add_argument('--executable', required=True)
    parser.add_argument('--domain', type=int, required=True)
    parser.add_argument('--generation-base', type=int, required=True)
    parser.add_argument('--minimum-free-bytes', type=int, default=2*1024**3)
    parser.add_argument('--require-startup-protocol', action='store_true')
    parser.add_argument('--seeds', type=int, nargs='+')
    parser.add_argument('--summarize-only', action='store_true')
    args = parser.parse_args(argv)
    baseline = json.loads(Path(args.baseline).read_text())
    cases = load_cases(json.loads(Path(args.matrix).read_text()))
    selected = [case for case in cases if args.seeds is None or case['seed'] in args.seeds]
    output = Path(args.output)
    if not args.summarize_only:
        output.mkdir(parents=True, exist_ok=False)
        write_json(output/'inputs.json', dict(baseline=reference(args.baseline),
            matrix=reference(args.matrix), selected=selected, prefix=args.prefix,
            executable=reference(args.executable), python=args.python, domain=args.domain))
    attempts = {}
    for case in selected:
        case_root = output/case['case_id']
        if args.summarize_only:
            attempts[case['case_id']] = [json.loads(path.read_text())
                for path in sorted(case_root.glob('attempt-*/facts.json'))]
        else:
            case_root.mkdir()
            attempts[case['case_id']] = run_case(case, baseline, output=case_root,
                prefix=args.prefix, python=args.python, executable=args.executable,
                domain=args.domain, generation_base=args.generation_base,
                minimum_free_bytes=args.minimum_free_bytes,
                require_startup_protocol=args.require_startup_protocol)
            if any(not may_continue(row, require_startup_protocol=args.require_startup_protocol) for row in attempts[case['case_id']]):
                break
        rows = summarize(selected, attempts)
        write_json(output/'results.json', dict(rows=rows, counts=dict(Counter(row['status'] for row in rows)),
                                              qualified=False))
    rows = summarize(selected, attempts)
    result = dict(rows=rows, counts=dict(Counter(row['status'] for row in rows)), qualified=False)
    write_json(output/'results.json', result)
    print(json.dumps(result['counts']), flush=True)
    return 0 if all(row['status'] == 'PASS' for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
