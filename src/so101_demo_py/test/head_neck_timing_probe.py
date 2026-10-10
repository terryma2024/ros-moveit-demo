"""Owned holding-only Head timing probe; no detector or search is constructed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import threading
import time


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def clock_trace_health(directory, now_ns):
    """Check task-owned diagnostic streams without changing timing qualification."""
    try:
        for stream in ('physics', 'loop'):
            path = Path(directory) / f'{stream}.status.json'
            if path.is_symlink() or path.stat().st_size > 4096:
                raise ValueError('status path/size')
            row = json.loads(path.read_text())
            observed_ns = now_ns() if callable(now_ns) else now_ns
            age = observed_ns - row['heartbeat_ns']
            if (row['schema'] != 'SOCLK001' or row['stream'] != stream
                    or row['invalid_flags'] != 0 or row['final'] is not False
                    or not 0 <= age < 2_000_000_000):
                raise ValueError('invalid/stale status')
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError('CLOCK_DIAGNOSTIC_STATUS_INVALID') from error


def monitor_clock_traces(directory, cancelled, get_runtime, finished, errors, started_ns):
    """Supervise startup and holding; use the original Stop when it exists."""
    first_trace_ns = None
    both_seen = False
    while not finished.wait(.25):
        now = time.monotonic_ns()
        try:
            if now - started_ns >= 240_000_000_000 or cancelled.is_set():
                raise RuntimeError('CLOCK_DIAGNOSTIC_NORMAL_WORK_CANCELLED')
            present = [Path(directory, f'{stream}.status.json').is_file()
                       for stream in ('physics', 'loop')]
            begun = any(present) or any(Path(directory, f'{stream}.bin').is_file()
                                       for stream in ('physics', 'loop'))
            if begun and first_trace_ns is None:
                first_trace_ns = now
            if all(present):
                both_seen = True
                clock_trace_health(directory, time.monotonic_ns)
            elif both_seen or (first_trace_ns is not None and now - first_trace_ns >= 2_000_000_000):
                raise RuntimeError('CLOCK_DIAGNOSTIC_STATUS_MISSING')
        except Exception as error:
            errors.append(dict(type=type(error).__name__, message=str(error)))
            cancelled.set()
            current = get_runtime()
            if current is not None:
                try:
                    current.stop('unknown')
                except Exception as stop_error:
                    errors.append(dict(type=type(stop_error).__name__, message=str(stop_error)))
            return


def continuous_updates(updates, hold_start, hold_end):
    if any(after[3] != before[3] + 1 for before, after in zip(updates, updates[1:])):
        return False
    holding = [row for row in updates if hold_start <= row[8] <= hold_end]
    return all(after[6] == before[6] + 2_000_000
               for before, after in zip(holding, holding[1:]))


def main():
    probe_started_ns = time.monotonic_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execution-inputs', required=True)
    parser.add_argument('--duration-s', type=int, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.duration_s != 120:
        raise ValueError('HEAD_TIMING_FROZEN_DURATION')
    output = Path(args.output)
    output.mkdir(exist_ok=False)
    cancelled = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: cancelled.set())
    signal.signal(signal.SIGINT, lambda *_: cancelled.set())
    from so101_demo.act.head_execution_inputs import HeadExecutionInputs
    from so101_demo.act.head_execution_documents import (
        build_run_local_state, retire_run_resources, retirement_unconfirmed)
    from so101_demo.adapters.act.head_execution_composition import HeadExecutionComposition
    from so101_demo.adapters.act import head_execution_provider as provider
    from so101_demo.adapters.act.head_local_observer import HeadLocalObserver
    from so101_demo.adapters.act.head_local_runtime import HeadLocalRuntime
    from so101_demo.adapters.act.head_native_policy_readback import read_native_policy
    from so101_demo.cli.head_execution_runner import _bind_originals, _await_originals
    inputs = HeadExecutionInputs.parse(args.execution_inputs)
    expected = Path(os.environ['SO101_EXPECTED_INSTALL']).resolve()
    for module in (provider, __import__(HeadLocalRuntime.__module__, fromlist=['_'])):
        if not Path(module.__file__).resolve().is_relative_to(expected):
            raise ValueError('HEAD_TIMING_INSTALLED_PRODUCT_REQUIRED')
    environment = inputs.document['ros']['environment']
    timing_root = Path(environment['SO101_STOP_TIMING_OUTPUT_DIR'])
    if timing_root != output / 'controller-records':
        raise ValueError('HEAD_TIMING_OUTPUT_SCOPE')
    timing_root.mkdir()
    composition = HeadExecutionComposition.open(inputs)
    handle = None
    runtime = None
    receipts = {}
    problem = None
    failures = []
    monitor_finished = threading.Event()
    monitor_errors = []
    monitor = None
    diagnostic_root = environment.get('SO101_CLOCK_TRACE_DIR')
    if diagnostic_root:
        monitor = threading.Thread(target=monitor_clock_traces, args=(diagnostic_root,
            cancelled, lambda: runtime, monitor_finished, monitor_errors, probe_started_ns),
            name='clock-diagnostic-owner-monitor', daemon=True)
        monitor.start()
    try:
        plan = provider.resource_plan(inputs)
        handle = provider.assemble(composition, inputs, plan=plan)
        if diagnostic_root and cancelled.is_set():
            raise RuntimeError('CLOCK_DIAGNOSTIC_STARTUP_CANCELLED')
        stack, capture = handle['stack'], handle['capture']
        state = build_run_local_state(inputs, composition.policy, None)
        camera = json.loads(Path(inputs.refs['development_config']['path']).read_text())['camera']
        observer = HeadLocalObserver(stack.node, stack.port, state, policy=composition.policy,
            camera_frame=camera['frame_id'], bind_port_sink=False)
        revoker_entry, native_entry = handle['revoker_entry'], handle['native_entry']
        revoker = revoker_entry['callable'](**revoker_entry['keywords'])
        def sink(kind, record, stamp):
            composition.emit(kind, record, source_stamp_ns=stamp,
                occurrence_mono_ns=record.get('callback_wall_ns'))
        runtime = HeadLocalRuntime(node=stack.node, port=stack.port, local_state=state,
            revoker=revoker, observer=observer, policy=composition.policy, sink=sink)
        _bind_originals(composition, capture, stack.port, observer, runtime)
        handle['local_ros'].retain_originals_until_close(runtime)
        handle['scene'].bind_fault(runtime.fault)
        runtime.bind_native_policy_readback(read_native_policy(stack.node, composition.policy))
        authority = native_entry['callable'](**dict(native_entry['keywords'],
            arm_guard=runtime.prearm_guard, fault_callback=runtime.fault))
        runtime.bind_authority(authority)
        composition.bind_native(authority=authority, revoker=revoker)
        _await_originals(observer, composition)
        if diagnostic_root:
            clock_trace_health(diagnostic_root, time.monotonic_ns)
            if cancelled.is_set():
                raise RuntimeError('CLOCK_DIAGNOSTIC_PREARM_CANCELLED')
        runtime.start()
        startup_started = time.monotonic_ns()
        runtime.arm(cancel_event=cancelled)
        startup_ended = time.monotonic_ns()
        receipts['startup_ns'] = startup_ended - startup_started
        if receipts['startup_ns'] >= 2_000_000_000:
            raise TimeoutError('HEAD_TIMING_STARTUP_EXPIRED')
        child = stack.processes[0]
        maps = (Path('/proc') / str(child.pid) / 'maps').read_text()
        native_lines = [row for row in maps.splitlines() if 'so101_broker_owned_trajectory_controller' in row]
        if not native_lines or any(str(expected) not in row for row in native_lines):
            raise ValueError('HEAD_TIMING_NATIVE_MAPS')
        (output / 'native-maps.txt').write_text(maps)
        receipts['native_child'] = handle['native_child']
        receipts['hold_started_ns'] = time.monotonic_ns()
        diagnostic_check_at = 0.
        deadline = time.monotonic() + args.duration_s
        while time.monotonic() < deadline:
            if cancelled.is_set() or child.poll() is not None or runtime.stop_requested or state.faulted:
                raise RuntimeError('HEAD_TIMING_HOLD_REFUSED')
            if diagnostic_root and time.monotonic() >= diagnostic_check_at:
                clock_trace_health(diagnostic_root, time.monotonic_ns)
                diagnostic_check_at = time.monotonic() + .25
            # No dispatch or inference is requested. The unchanged runtime
            # watchdog continues supervising originals and independent Stop.
            time.sleep(min(.02, max(0., deadline - time.monotonic())))
        receipts['hold_ended_ns'] = time.monotonic_ns()
    except Exception as error:
        problem = dict(type=type(error).__name__, message=str(error))
    finally:
        monitor_finished.set()
        if monitor is not None:
            monitor.join(timeout=.5)
            if monitor.is_alive():
                failures.append(('diagnostic_monitor', 'CLOCK_DIAGNOSTIC_MONITOR_EXIT_TIMEOUT'))
            receipts['diagnostic_monitor_errors'] = monitor_errors
            if monitor_errors:
                problem = problem or monitor_errors[0]
        receipts['retirement_started_ns'] = time.monotonic_ns()
        if runtime is not None:
            try:
                runtime.stop('success' if problem is None else 'unknown')
            except Exception as error:
                failures.append(('stop', type(error).__name__, str(error)))
            outcomes = {}
            report = retire_run_resources(runtime, None, None, outcomes=outcomes,
                defer_original_retirement=True)
            receipts['runtime'] = outcomes.get('runtime')
            failures.extend((stage, detail) for stage, detail in report.items() if detail)
        if handle is not None:
            failures.extend(provider.teardown([(stage, handle[stage]) for stage in
                ('local_ros', 'campaign_truth', 'scene', 'stack') if stage in handle]))
            composition.finish_resource_lifetime('provider_ros', confirmed=not failures)
            provider._preserve_stack_log(composition, handle['stack'])
        # A probe deliberately has no detector/inference/search composition.
        # Retain its actual events with that limitation rather than claiming
        # formal search completion or a search business return code.
        if composition.writer is not None:
            composition.writer.finish(dict(kind='HEAD_HOLDING_TIMING_PROBE',
                complete_composition=False, motion_dispatched=False, problem=problem,
                retirement_failures=failures), timeout_s=1.)
        receipts['retirement_ended_ns'] = time.monotonic_ns()
    if handle is not None:
        children = getattr(handle['stack'], 'head_retirement_children', [])
        graph = subprocess.run(['/opt/ros/jazzy/bin/ros2', 'node', 'list', '--no-daemon'],
            env=dict(os.environ, **environment), text=True, capture_output=True, timeout=15)
        (output / 'ros-nodes.stdout').write_text(graph.stdout)
        (output / 'ros-nodes.stderr').write_text(graph.stderr)
        receipts['children'] = children
        receipts['graph_empty'] = graph.returncode == 0 and not graph.stdout.strip()
        receipts['children_absent'] = bool(children) and all(row['rc'] == 0 and
            not (Path('/proc') / str(row['pid'])).exists() for row in children)
    events = []
    try:
        seal = json.loads((inputs.run_root / 'seal.json').read_text())
        if not {'events.jsonl', 'completion.json'} <= {row['path'] for row in seal['files']}:
            raise ValueError('HEAD_TIMING_EVENTS_UNSEALED')
        for row in seal['files']:
            path = inputs.run_root / row['path']
            if path.is_symlink() or '..' in Path(row['path']).parts or Path(row['path']).is_absolute():
                raise ValueError('HEAD_TIMING_SEAL_PATH')
            raw = path.read_bytes()
            if len(raw) != row['size'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('HEAD_TIMING_SEAL_MISMATCH')
        events = [json.loads(line) for line in (inputs.run_root / 'events.jsonl').read_text().splitlines()]
        if any(row['run'] != inputs.run for row in events):
            raise ValueError('HEAD_TIMING_EVENT_IDENTITY')
        receipts['seal_verified'] = True
    except Exception as error:
        problem = problem or dict(type=type(error).__name__, message=str(error))
    control = [row['record'] for row in events if row['kind'] in ('PREARM_STATUS', 'ARM_RESULT')]
    exchange_ns = []
    for row in control:
        elapsed = (row['ack_wall_s'] - row['request_wall_s']) * 1e9
        exchange_ns.append(elapsed)
        if not 0 <= elapsed < 50_000_000 or row['proof']['wrapper_reason'] == 8:
            problem = problem or dict(type='MainExchange', message='HEAD_TIMING_MAIN_BOUND')
        if row['proof']['cumulative_observation_lock_losses'] != 0:
            problem = problem or dict(type='SamplingLoss', message='HEAD_TIMING_LOCK_LOSS')
    receipts['main_exchange_ns'] = exchange_ns
    rows = []
    binary = timing_root / 'neck_controller.bin'
    integrity = Path(str(binary) + '.status.json')
    if binary.is_file() and integrity.is_file():
        raw = binary.read_bytes()
        if raw[:8] != b'SOTM0001' or (len(raw) - 8) % 88:
            problem = problem or dict(type='TimingIntegrity', message='HEAD_TIMING_RECORD_FORMAT')
        else:
            rows = list(struct.iter_unpack('=5Q5qQ', raw[8:]))
        status = json.loads(integrity.read_text())
        receipts['collector_status'] = status
        if (status['overflow'] or status['io_failed'] or status['records_written'] != len(rows)
                or status['records_reserved'] != len(rows)
                or any(row[10] != 1 or row[2] != 3 or row[0] not in (1, 2, 3) for row in rows)):
            problem = problem or dict(type='TimingIntegrity', message='HEAD_TIMING_RECORD_LOSS')
    else:
        problem = problem or dict(type='TimingIntegrity', message='HEAD_TIMING_OUTPUT_MISSING')
    timing = {}
    for kind, name in ((1, 'update'), (2, 'publication'), (3, 'proof')):
        selected = [row for row in rows if row[0] == kind]
        durations = [row[9] - row[8] for row in selected]
        timing[name] = dict(count=len(selected), max_ns=max(durations, default=0),
            overruns=sum(value >= 2_000_000 or value < 0 for value in durations))
        if not selected or timing[name]['overruns']:
            problem = problem or dict(type='TimingBound', message=name)
    updates = [row for row in rows if row[0] == 1]
    if any(row[7] != 2_000_000 for row in updates):
        problem = problem or dict(type='TimingPeriod', message='HEAD_TIMING_PERIOD')
    if any(row[1] != 1 for row in rows if row[0] == 3):
        problem = problem or dict(type='SnapshotAvailability', message='HEAD_TIMING_UNAVAILABLE')
    hold_start = receipts.get('hold_started_ns', 0)
    hold_end = receipts.get('hold_ended_ns', 0)
    if not continuous_updates(updates, hold_start, hold_end):
        problem = problem or dict(type='TimingContinuity', message='HEAD_TIMING_UPDATE_GAP')
    holding_updates = [row for row in updates if hold_start <= row[8] <= hold_end]
    receipts['startup_simulation_discontinuities'] = [
        dict(before_update=before[3], after_update=after[3],
             before_sim_ns=before[6], after_sim_ns=after[6], after_started_ns=after[8])
        for before, after in zip(updates, updates[1:])
        if after[8] < hold_start and after[6] != before[6] + 2_000_000]
    receipts['holding_update_count'] = len(holding_updates)
    if len(holding_updates) < 60000:
        problem = problem or dict(type='TimingCount', message='HEAD_TIMING_500HZ_COUNT')
    if updates:
        base_id, base_ns = updates[0][3], updates[0][8]
        receipts['scheduling_jitter_max_ns'] = max(row[8] - (base_ns +
            (row[3] - base_id) * 2_000_000) for row in updates)
    # DDS may still advertise this process's destroyed node before owner exit.
    # The parent must separately require owner absence and an empty graph.
    receipts['independent_postflight_pending'] = True
    if (not receipts.get('children_absent') or
            retirement_unconfirmed(receipts.get('runtime')) or failures):
        problem = problem or dict(type='Retirement', message='HEAD_TIMING_RETIREMENT')
    result = dict(qualified=problem is None, problem=problem, receipts=receipts,
        timing=timing, scope=1, search_executed=False, detector_executed=False,
        ordinary_package_green=False, production_qualified=False)
    write_json(output / 'report.json', result)
    print(json.dumps(result), flush=True)
    return 0 if result['qualified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
