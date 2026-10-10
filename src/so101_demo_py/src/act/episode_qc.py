"""The independent data QC recomputation for one sealed episode.

Data QC answers one question: is the recording itself valid training data? It re-reads the sealed audit a fresh process
was pointed at, exactly as ``verify_audit_manifest`` listed it, and keeps every data check (lossless rows, causal
labels, real camera acquisition, t+0.1 s references, seal and readback, native collection boundaries).

It does **not** judge the task. Task success is the Teacher's ``teacher_endpoint`` result; the episode seal's
``pick_place_validation_success`` is not a QC criterion (design D2, "Old QC path").
Instead ``verify_teacher_references`` cross-checks that the recording is consistent with the start and end source
references the Teacher manifest recorded: that is data integrity, and it never reads the Teacher's PASS/FAIL.

"""

from __future__ import annotations

import bisect
import json
import hashlib
import math
import os
import stat
import uuid
from pathlib import Path

from so101_demo.application.e2e_acceptance import SCHEMA_TEACHER, is_manifest_of
from so101_demo.act.episode_audit import verify_audit_manifest
from so101_demo.act.qc_session import active, cached_lines, file_signature, load_model, session_memo

PHYSICS_STREAM = "physics.jsonl"
REFERENCE_STREAM = "references.jsonl"


def verify_episode_physical_rows(rows, *, raw_chunks, associations, inputs, identity):
    from .episode_physical_readback import verify_physical_rows
    return verify_physical_rows(rows, raw_chunks=raw_chunks, associations=associations,
                                inputs=inputs, identity=identity)


def verify_original_references(references):
    from .episode_reference_readback import verify_original_references as verify
    return verify(references)


def _native_events_key(events, *, identity, window, inputs):
    from .qc_session import Identity

    return (Identity(events), len(events),
            json.dumps([identity, window, inputs], sort_keys=True, separators=(",", ":"), default=str))


@session_memo(_native_events_key, copy_result=False)
def verify_native_collection_events(events, *, identity, window, inputs):
    """Recompute complete collection boundaries from originals, without live ports.

    The enclosing episode reader still authenticates the seal, scope, rows, references and lease. This readback
    supplies the cross-boundary causality, from `SO101_TEACHER_EVENT` events: `reset_complete` is the Teacher's start (after the
    capture is running), the verified reset is the Recorder's own first evidence of the epoch,
    the first command is the first goal-sending `phase_begin`, the normal end is `normal_stop` then `terminal`. It also
    requires the event sequence to be whole and the `controller_state` label stream to have no gap in its window.
    It never grants command authority.
    """
    import copy
    import mujoco
    from .collection_boundaries import boundary_clock, claim_collection_boundary, world_source_digest
    from .contracts import finite
    from .episode_audit import _identity_ok
    from .execution_snapshot import verify_execution_snapshot
    from .diagnostic_episode_inputs import audit_execution_model_identity
    from .joints import ACT_JOINTS
    from .native_endpoints import first_world_after_start, first_world_after_stop, verify_world_source
    from .raw_physics_chunks import verify_raw_chunk
    from .scene_association import canonical
    from .teacher_collection import (
        SCHEMA as EVENT_SCHEMA, first_command_clock, validate_event_summary, validate_first_command_window,
        validate_normal_end_window, validate_reset_complete_matches, validate_teacher_event)

    if not _identity_ok(identity, formal=True):
        raise ValueError('NATIVE_QC_LEASE_REQUIRED')
    model_identity = audit_execution_model_identity(inputs)
    if model_identity is None:
        raise ValueError('NATIVE_QC_FROZEN_MODEL_REQUIRED')
    if 'first_command_s' not in window or 'physics_end_s' not in window:
        raise ValueError('NATIVE_QC_OBSERVED_WINDOW_REQUIRED')
    boundaries, sources, teacher, raw_steps, summaries, continuity = {}, [], [], [], [], []
    seen_boundaries, world_hashes = set(), {}
    previous = None
    chunks = inputs['execution_snapshot']['physics_chunks']
    for event in events:
        if event['kind'] == 'native_dispatch':
            raise ValueError('NATIVE_QC_EVENT_REJECTED')
        if event['kind'] == 'physics_chunk':
            raw = event['payload']['raw_chunk']
            verify_raw_chunk(raw, previous=previous, previous_verified=True, session_id=identity['session_id'],
                reset_epoch=identity['reset_epoch'], nq=model_identity['nq'], nv=model_identity['nv'],
                max_samples=chunks['max_samples'], max_contacts=chunks['max_contacts'])
            raw_steps.extend(raw['chunk']['samples']); previous = raw
        elif event['kind'] == 'world_source':
            source = event['payload']['world_source']
            sources.append(source)
            sequence = source['physics']['publisher_sequence']
            if sequence in world_hashes:
                raise ValueError('NATIVE_QC_WORLD_REPEATED')
            world_hashes[sequence] = world_source_digest(source)
        elif event['kind'] == 'teacher_event':
            document = event['payload']['teacher_event']
            if document.get('schema') != EVENT_SCHEMA:
                raise ValueError('NATIVE_QC_EVENT_SCHEMA_INVALID')
            try:
                validate_teacher_event(document, identity=identity)
            except ValueError as error:
                raise ValueError('NATIVE_QC_EVENT_IDENTITY_INVALID') from error
            teacher.append((event, document))
        elif event['kind'] == 'teacher_event_summary':
            summaries.append(validate_event_summary(event['payload']['event_summary']))
        elif event['kind'] == 'controller_reference':
            continuity.append(event['payload']['reference_continuity'])
        elif event['kind'] == 'collection_boundary':
            document = claim_collection_boundary(event, identity=identity,
                seen=seen_boundaries, world_hashes=world_hashes)
            boundaries[document['stage']] = document
    if set(boundaries) != {'verified_reset', 'capture_start', 'initial_capture', 'normal_stop', 'final_capture'} \
            or not sources:
        raise ValueError('NATIVE_QC_COMPLETE_ORIGINALS_REQUIRED')
    # ---- the V2 event sequence: whole, ordered, and each required event present ---------------------------------
    if len(summaries) != 1:
        raise ValueError('NATIVE_QC_EVENT_SUMMARY_REQUIRED')
    summary = summaries[0]
    by_type = {}
    for _event, document in teacher:
        by_type.setdefault(document['type'], []).append(document)
    if not by_type.get('reset_complete'):
        raise ValueError('NATIVE_QC_RESET_COMPLETE_REQUIRED')
    first_command = next((clock for clock in (first_command_clock(item) for item in by_type.get('phase_begin', ()))
                          if clock is not None), None)
    if first_command is None:
        raise ValueError('NATIVE_QC_FIRST_COMMAND_EVENT_REQUIRED')
    if not by_type.get('normal_stop'):
        raise ValueError('NATIVE_QC_NORMAL_STOP_EVENT_REQUIRED')
    if not by_type.get('terminal'):
        raise ValueError('NATIVE_QC_TERMINAL_EVENT_REQUIRED')
    sequences = [document['seq'] for _event, document in teacher]
    scene_operations = summary['types'].get('scene_operation', 0)
    if (summary['accepted'] != summary['last_seq'] or sequences != sorted(set(sequences))
            or (sequences and sequences[-1] > summary['last_seq'])
            or summary['last_seq'] - len(sequences) != scene_operations
            or any(summary['types'].get(kind, 0) != len(items) for kind, items in by_type.items())
            or sum(summary['types'].values()) != summary['accepted']):
        raise ValueError('NATIVE_QC_EVENT_SEQUENCE_GAP')
    reset = boundaries['verified_reset']['value']
    validate_reset_complete_matches(by_type['reset_complete'][0], reset)
    stop = boundaries['normal_stop']['value']
    stop_clock = boundary_clock(boundaries['normal_stop'])
    if by_type['terminal'][0]['monotonic_ns'] < stop_clock['end_monotonic_ns']:
        raise ValueError('NATIVE_QC_TERMINAL_ORDER_INVALID')
    # ---- boundary order and lease clocks ----------------------------------------------------------------------
    clocks = [boundary_clock(boundaries[stage]) for stage in ('verified_reset', 'capture_start', 'initial_capture')]
    # The Teacher starts after the capture is running with its initial boundary committed (the orchestrator waits for
    # CAPTURING): its `reset_complete` event comes after the initial capture and before its first command
    teacher_start = by_type['reset_complete'][0]
    clocks += [dict(sim_time_ns=teacher_start['sim_time_ns'], begin_monotonic_ns=teacher_start['monotonic_ns'],
                    end_monotonic_ns=teacher_start['monotonic_ns'])]
    clocks += [first_command]
    clocks += [boundary_clock(boundaries[stage]) for stage in ('normal_stop', 'final_capture')]
    for before, after in zip(clocks, clocks[1:]):
        if (before['end_monotonic_ns'] > after['begin_monotonic_ns']
                or before['sim_time_ns'] > after['sim_time_ns']):
            raise ValueError('NATIVE_QC_BOUNDARY_ORDER_INVALID')
    # ---- the source alignments the rows rest on: the empty scene before the capture, the SETUP scene before the
    # first command. The Teacher's later scene changes (attach, detach) are checked row by row against their own alignments.
    alignments = [item['payload']['association'] for item in events if item['kind'] == 'source_alignment']
    initial = [item for item in alignments if item['operation'] == 'initial']
    capture_start = boundaries['capture_start']['value']
    if (len(initial) != 1 or initial[0]['schema_version'] != 3
            or initial[0]['query']['record']['request_ros_clock']['sim_time_ns'] > capture_start['sim_time_ns']):
        raise ValueError('NATIVE_QC_INITIAL_ALIGNMENT_INVALID')
    if not any(item['operation'] == 'world_sync'
               and item['query']['record']['response_ros_clock']['sim_time_ns'] <= first_command['sim_time_ns']
               for item in alignments):
        raise ValueError('NATIVE_QC_WORLD_SYNC_REQUIRED')
    lease = identity['lease']
    issued = finite(lease['lease_issued_monotonic_s'], nonnegative=True)
    deadline = finite(lease['lease_deadline_monotonic_s'], nonnegative=True)
    if any(not issued <= clock['begin_monotonic_ns']/1e9 <= clock['end_monotonic_ns']/1e9 < deadline
           for clock in clocks):
        raise ValueError('NATIVE_QC_LEASE_CLOCK_INVALID')
    validate_first_command_window(first_command, window)
    validate_normal_end_window(stop_clock, window)
    if stop_clock['sim_time_ns'] - first_command['sim_time_ns'] > 120_000_000_000:
        raise ValueError('NATIVE_QC_MOTION_DEADLINE_INVALID')
    # ---- the label stream: no gap in its window, one epoch, nothing before the reset boundary ------------------
    if len(continuity) != 1:
        raise ValueError('REFERENCE_CONTINUITY_MISSING')
    reference = verify_reference_continuity(continuity[0], identity=identity, window=window)

    # Full model/FK checks are required even for sources not selected as endpoints.
    models, previous = {}, None
    for source in sources:
        root = source['execution_root']
        if root not in models:
            snapshot = verify_execution_snapshot(root, expected_sha256=inputs['execution_snapshot']['sha256'])
            models[root] = load_model(Path(root)/snapshot['scene_path'], root=root)
        verify_world_source(source, identity=identity, model=models[root], model_identity=model_identity,
                            raw_steps=raw_steps, previous=previous)
        previous = source
    initial = boundaries['initial_capture']['value']
    final = boundaries['final_capture']['value']
    selected_initial = first_world_after_start(sources, identity=identity, reset_clock=reset['source_clock'],
        capture_start_clock=boundary_clock(boundaries['capture_start']), first_dispatch_clock=first_command,
        capture_clock=initial['source_clock'], raw_steps=raw_steps)
    selected_final = first_world_after_stop(sources, stop, identity=identity,
        capture_clock=final['source_clock'], raw_steps=raw_steps)
    if (canonical(selected_initial) != canonical(initial['world_source'])
            or canonical(selected_final) != canonical(final['world_source'])):
        raise ValueError('NATIVE_QC_FIRST_SOURCE_INVALID')
    last = stop_native_step(raw_steps, stop_clock)
    model = models[selected_final['execution_root']]
    for name in ACT_JOINTS:
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint < 0 or int(model.jnt_type[joint]) not in (
                int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)):
            raise ValueError('NATIVE_QC_STOP_JOINT_MAPPING_INVALID')
        if abs(finite(last['model_qvel'][int(model.jnt_dofadr[joint])])) > .002:
            raise ValueError('NATIVE_QC_STOP_NATIVE_MOVING')
    return copy.deepcopy(dict(initial_source=selected_initial, final_source=selected_final,
        normal_stop_step=last['physics_step'],
        goal_phase_begins=sum(1 for item in by_type.get('phase_begin', ()) if first_command_clock(item) is not None),
        first_command_s=first_command['sim_time_ns'] / 1e9, reference_gaps=reference['neck_gaps']))


def stop_native_step(raw_steps, stop_clock):
    """The native step that is the normal stop's state: the last step finished before the stop receipt AND not later than the
    stop's simulation stamp, within 100 ms of it.

    The stamp is a received /clock value, so physics can already be a step ahead of it when the stamp is taken (bag 429dbf50: step
    116.548 s ended 46 us before a receipt that read 116.546 s). A step ahead of the stamp is not the state the Teacher confirmed
    and is not stale evidence either; the receipt order stays exact."""
    stamp_ns = stop_clock['sim_time_ns']
    before_stop = [sample for sample in raw_steps
                   if sample['clock_interval_end_monotonic_ns'] <= stop_clock['begin_monotonic_ns']
                   and round(sample['simulation_time_s'] * 1e9) <= stamp_ns]
    if not before_stop:
        raise ValueError('NATIVE_QC_STOP_NATIVE_REQUIRED')
    last = max(before_stop, key=lambda sample: sample['physics_step'])
    if not 0 <= stamp_ns - round(last['simulation_time_s'] * 1e9) <= 100_000_000:
        raise ValueError('NATIVE_QC_STOP_NATIVE_STALE')
    return last


def label_instants_ns(window):
    """The instants the labels belong to: each row's `t + 0.1 s`, for the rows from `collection_start_s` through `label_cutoff_s`."""
    start, cutoff = round(window['collection_start_s'] * 1e9), round(window['label_cutoff_s'] * 1e9)
    step = 100_000_000
    return [start + step * (index + 1) for index in range((cutoff - start) // step + 1)] if cutoff >= start else []


def reference_frames_needed_ns(instant_ns, period_ns):
    """The controller frames a label at `instant_ns` needs: the frame at the instant and the ones a period either side.

    The controller publishes on a `period_ns` stamp grid; a label instant that is off the grid by a nanosecond (a camera stamp
    4.803999999 s) names the grid frame that matches it within 1 us, so the needed frames are that frame's grid position +- one period.
    """
    grid = round(instant_ns / period_ns) * period_ns
    return (grid - period_ns, grid, grid + period_ns)


def verify_reference_continuity(report, *, identity, window):
    """The reference must be continuous AT EVERY LABEL INSTANT; gaps that touch no label instant are diagnostic.

    The arm and gripper `controller_state` frame at each row's label instant (`t + 0.1 s`) and the frames one controller period
    either side must exist. A gap is a consecutive per-controller stamp step other than one controller period; it removes the
    frames strictly between its two stamps. A gap that removes a needed frame makes the data INVALID. Every other arm or gripper
    gap, and every neck gap, is only counted. The gap list keeps the first 256 steps per controller; a count larger than the
    list cannot prove the labels clean. (The earlier rule, zero gaps anywhere in the window, was one that a producer
    dropping one realtime publication per ~30 s per controller can never meet although no label is affected.)
    """
    from .teacher_collection import CONTINUITY_PERIOD_NS, validate_reference_continuity

    if report is None:
        raise ValueError('REFERENCE_CONTINUITY_MISSING')
    validate_reference_continuity(report)
    if (report['session_id'], report['reset_epoch']) != (identity['session_id'], identity['reset_epoch']):
        raise ValueError('REFERENCE_EPOCH_MISMATCH')
    start, cutoff = window.get('collection_start_s'), window.get('label_cutoff_s')
    if type(start) not in (int, float) or type(cutoff) not in (int, float):
        raise ValueError('REFERENCE_WINDOW_REQUIRED')
    needed = sorted({frame for instant in label_instants_ns(window)
                     for frame in reference_frames_needed_ns(instant, CONTINUITY_PERIOD_NS)})
    touching, diagnostic = 0, 0
    for kind in ('arm', 'gripper'):
        block = report['kinds'][kind]
        if block['gaps'] > len(block['steps']):
            raise ValueError('REFERENCE_GAP_LIST_INCOMPLETE')
        for previous, stamp in block['steps']:
            # frames strictly between the two stamps are missing; is a needed frame among them?
            index = bisect.bisect_right(needed, previous)
            if index < len(needed) and needed[index] < stamp:
                touching += 1
            else:
                diagnostic += 1
    if touching:
        raise ValueError('REFERENCE_GAP_IN_LABEL_WINDOW')
    return dict(gaps_in_window=touching, diagnostic_gaps=diagnostic, neck_gaps=report['kinds']['neck']['gaps'],
                label_instants=len(label_instants_ns(window)), period_ns=CONTINUITY_PERIOD_NS)


def verify_reference_epoch(rows, *, reset_sim_time_ns):
    """Every label frame belongs to this reset epoch: none is stamped before the verified reset boundary."""
    count = 0
    for row in rows:
        for frame in row['frames'].values():
            if frame['sim_stamp_ns'] < reset_sim_time_ns:
                raise ValueError('REFERENCE_CROSS_RESET_FRAME')
        count += 1
    return count


def _requires_native_collection(inputs, events):
    # The frozen input digest (manifest schema 2) and the external scope bind this marker. Removing all
    # Teacher events from a current episode therefore cannot select an old reader.
    from .teacher_collection import is_current_episode
    return is_current_episode(inputs, events)



def _physical_audit_key(episode_root, audit_manifest, scope):
    from .qc_session import file_signature, tree_signature

    root = Path(episode_root).absolute()
    return (str(root), str(Path(audit_manifest).absolute()), tree_signature(root), file_signature(Path(scope).absolute()))


@session_memo(_physical_audit_key)
def verify_episode_physical_audit(episode_root, audit_manifest, scope):
    """Re-read sealed originals for the selected publisher and bound Coordinator.

    Historical diagnostic seals remain readable by their archival readers.
    This production boundary requires the full observed window and native/source-alignment
    originals; its return is data evidence, not a complete QC verdict.
    """
    from .episode_audit import _WINDOW_FIELDS, _identity_ok
    from .recorder import verify_episode_seal

    try:
        root = _report_path(episode_root)
        manifest_path = _report_path(audit_manifest)
        scope_path = _report_path(scope)
        if manifest_path != root / "audit/audit-manifest.json":
            raise ValueError("original audit location")
        verify_episode_seal(root / "seal.json", audit_manifest=manifest_path, scope=scope_path)
        manifest = verify_audit_manifest(manifest_path)
        if (set(manifest["window"]) != _WINDOW_FIELDS
                or not _identity_ok(manifest["identity"], formal=True)):
            raise ValueError("full observed window/lease absent")

        def read_original(path):
            descriptor = os.open(_report_path(path), os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("original is not regular")
                return stream.read()

        def original_rows(path):
            # strict: a blank line is an error here. A file that parses is the same list `read_verified_rows` would give, so the
            # session shares it (the events are parsed once for the whole QC).
            rows = cached_lines(path, lambda target: [json.loads(line) for line in read_original(target).splitlines()])
            session = active()
            if session is not None:
                session.cache.setdefault(("lines", "lenient", file_signature(path)), rows)
            return rows

        inputs = json.loads(read_original(manifest_path.parent / "inputs.json"))
        rows = original_rows(root / "records.jsonl")
        events = original_rows(manifest_path.parent / "events.jsonl")
        references = original_rows(manifest_path.parent / "references.jsonl")
        verify_original_references(references)
        summary = verify_episode_physical_rows(rows,
            raw_chunks=[event["payload"]["raw_chunk"] for event in events
                        if event["kind"] == "physics_chunk"],
            associations=[event["payload"]["association"] for event in events
                          if event["kind"] == "source_alignment"],
            inputs=inputs, identity=manifest["identity"])
        if _requires_native_collection(inputs, events):
            verify_native_collection_events(events, identity=manifest['identity'], window=manifest['window'], inputs=inputs)
        return summary
    except (OSError, UnicodeDecodeError, ValueError, TypeError, KeyError) as error:
        raise ValueError("EPISODE_PHYSICAL_READBACK_INVALID") from error

QC_REPORT_FIELDS = frozenset({"kind", "schema_version", "status", "rule_version", "identity",
    "episode_seal_sha256", "audit_manifest_sha256", "inputs_sha256", "scope_sha256", "counts",
    "checks", "reason"})
QC_COUNT_FIELDS = frozenset({"records", "head_acquisitions", "wrist_acquisitions", "references",
                            "events", "physics", "native_steps"})


QC_SCHEMA_VERSION = 3
QC_RULE_VERSION = "act_data_qc"   # the data check, the Teacher-reference check and the topic_loss_gate check; any other rule is refused
REFERENCE_CHECK = "teacher_reference_consistency"
TOPIC_LOSS_CHECK = "topic_loss_gate"
#: the closed set of reasons data QC gives when the recording disagrees with the Teacher's recorded references
TEACHER_REFERENCE_CODES = frozenset({
    "TEACHER_REFERENCE_MANIFEST_MISSING", "TEACHER_REFERENCE_START_MISSING", "TEACHER_REFERENCE_END_MISSING",
    "TEACHER_REFERENCE_SESSION_MISMATCH", "TEACHER_REFERENCE_START_NOT_IN_WINDOW",
    "TEACHER_REFERENCE_END_AFTER_RECORDING", "TEACHER_REFERENCE_ORDER_INVALID",
    "TEACHER_REFERENCE_PHYSICS_STEP_ABSENT", "TEACHER_REFERENCE_PHYSICS_TIME_MISMATCH"})
_REFERENCE_FIELDS = frozenset({"session_id", "reset_epoch", "simulation_step", "simulation_time_s",
                               "publisher_sequence"})
_TIME_TOLERANCE_S = 1e-6


def _is_int(value):
    return type(value) is int


def _is_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _reference(value):
    """The closed reference document of one Teacher observation, or None when the observation cannot be one."""
    if type(value) is not dict:
        return None
    result = {key: value.get(key) for key in _REFERENCE_FIELDS}
    if (not isinstance(result["session_id"], str) or not result["session_id"]
            or not _is_int(result["reset_epoch"]) or not _is_int(result["simulation_step"])
            or result["simulation_step"] < 1 or not _is_number(result["simulation_time_s"])
            or not _is_int(result["publisher_sequence"])):
        return None
    return result


def verify_teacher_references(document, *, identity, window, physics_steps) -> dict:
    """Data integrity: is the recording consistent with the Teacher's recorded start and end source references?

    ``document`` is the Teacher manifest or None; ``physics_steps`` are the verified raw physics samples of the
    episode. The Teacher's PASS/FAIL is never read: a Teacher FAIL with consistent data passes here, and export is gated
    by the Teacher result elsewhere. The checks, in order, each with its own reason code: the manifest and both
    references exist; both belong to this session and reset epoch; the recording window covers the start reference
    (collection start up to the first command); the end reference is at or before the recorded end; start precedes end;
    and each referenced physics step is a retained raw sample of this session/epoch with the same simulation time.
    """

    steps = {}
    for sample in physics_steps:
        if (type(sample) is dict and _is_int(sample.get("physics_step"))
                and _is_number(sample.get("simulation_time_s"))):
            steps[(sample["physics_step"], sample.get("simulation_session_id"), sample.get("reset_epoch"))] = (
                float(sample["simulation_time_s"]))
    numbers = [step for step, _, _ in steps]
    recorded = {"first_step": min(numbers), "last_step": max(numbers)} if numbers else None
    details = {"teacher_manifest_sha256": None, "start_reference": None, "end_reference": None,
               "recorded_physics": recorded}

    def result(code):
        return {"status": "FAIL" if code else "PASS", "reason": code or "", "details": details}

    if not is_manifest_of(document, SCHEMA_TEACHER):
        return result("TEACHER_REFERENCE_MANIFEST_MISSING")
    start = _reference(document.get("teacher_start_observation"))
    end = _reference(document.get("teacher_end_observation"))
    details["start_reference"], details["end_reference"] = start, end
    if start is None:
        return result("TEACHER_REFERENCE_START_MISSING")
    if end is None:
        return result("TEACHER_REFERENCE_END_MISSING")
    if any((value["session_id"], value["reset_epoch"]) != (identity.get("session_id"), identity.get("reset_epoch"))
           for value in (start, end)):
        return result("TEACHER_REFERENCE_SESSION_MISMATCH")
    window = window if type(window) is dict else {}
    first = window.get("first_command_s")
    upper = first if _is_number(first) else window.get("physics_end_s")
    lower = window.get("collection_start_s")
    if (not _is_number(lower) or not _is_number(upper)
            or not lower - _TIME_TOLERANCE_S <= start["simulation_time_s"] <= upper + _TIME_TOLERANCE_S):
        return result("TEACHER_REFERENCE_START_NOT_IN_WINDOW")
    collection_end = window.get("collection_end_s")
    if (not _is_number(collection_end) or end["simulation_time_s"] > collection_end + _TIME_TOLERANCE_S
            or recorded is None or end["simulation_step"] > recorded["last_step"]):
        return result("TEACHER_REFERENCE_END_AFTER_RECORDING")
    if end["simulation_step"] <= start["simulation_step"]:
        return result("TEACHER_REFERENCE_ORDER_INVALID")
    for value in (start, end):
        recorded_time = steps.get((value["simulation_step"], value["session_id"], value["reset_epoch"]))
        if recorded_time is None:
            return result("TEACHER_REFERENCE_PHYSICS_STEP_ABSENT")
        if abs(recorded_time - value["simulation_time_s"]) > _TIME_TOLERANCE_S:
            return result("TEACHER_REFERENCE_PHYSICS_TIME_MISMATCH")
    return result("")


def _validate_reference_check(check):
    from .contracts import sha256
    if (type(check) is not dict or set(check) != {"status", "reason", "details"}
            or check["status"] not in ("PASS", "FAIL") or type(check["reason"]) is not str
            or (check["status"] == "FAIL") != bool(check["reason"])
            or (check["status"] == "FAIL" and check["reason"] not in TEACHER_REFERENCE_CODES)):
        raise ValueError("reference check")
    details = check["details"]
    if (type(details) is not dict or set(details) != {"teacher_manifest_sha256", "start_reference",
            "end_reference", "recorded_physics"}):
        raise ValueError("reference details")
    if details["teacher_manifest_sha256"] is not None:
        sha256(details["teacher_manifest_sha256"])
    for name in ("start_reference", "end_reference"):
        value = details[name]
        if value is not None and _reference(value) is None or (value is not None and set(value) != _REFERENCE_FIELDS):
            raise ValueError("reference")
    physics = details["recorded_physics"]
    if physics is not None and (type(physics) is not dict or set(physics) != {"first_step", "last_step"}
            or not all(_is_int(value) for value in physics.values()) or physics["first_step"] > physics["last_step"]):
        raise ValueError("recorded physics")
    if check["status"] == "PASS" and (details["teacher_manifest_sha256"] is None
            or details["start_reference"] is None or details["end_reference"] is None or physics is None):
        raise ValueError("reference pass")


def validate_qc_report(report):
    """Validate the closed report shape; this does not authenticate a QC verdict.

    Reports are schema 3 (rule ``act_data_qc``): the data check, the Teacher-reference consistency check and the topic-loss
    gate; no task success and no endpoint rule.
    """
    from .contracts import sha256
    from .episode_audit import _identity_ok
    try:
        if (type(report) is not dict or set(report) != QC_REPORT_FIELDS
                or report["kind"] != "ACT_EPISODE_QC" or type(report["schema_version"]) is not int
                or report["schema_version"] != QC_SCHEMA_VERSION or report["rule_version"] != QC_RULE_VERSION
                or report["status"] not in ("PASS", "FAIL") or type(report["reason"]) is not str
                or not _identity_ok(report["identity"], formal=True)):
            raise ValueError("schema")
        for name in ("episode_seal_sha256", "audit_manifest_sha256", "inputs_sha256", "scope_sha256"):
            sha256(report[name])
        counts = report["counts"]
        if (type(counts) is not dict or set(counts) != QC_COUNT_FIELDS
                or any(type(value) is not int or value < 0 for value in counts.values())):
            raise ValueError("counts")
        checks = report["checks"]
        if type(checks) is not dict or set(checks) != {"episode_data", REFERENCE_CHECK, TOPIC_LOSS_CHECK}:
            raise ValueError("checks")
        check = checks["episode_data"]
        if (type(check) is not dict or set(check) != {"status", "reason"}
                or check["status"] not in ("PASS", "FAIL") or type(check["reason"]) is not str
                or bool(check["reason"]) != (check["status"] == "FAIL")):
            raise ValueError("check")
        _validate_reference_check(checks[REFERENCE_CHECK])
        from .topic_loss import validate_check
        validate_check(checks[TOPIC_LOSS_CHECK])
        failing = [item["reason"] for item in (checks["episode_data"], checks[REFERENCE_CHECK], checks[TOPIC_LOSS_CHECK])
                   if item["status"] == "FAIL"]
        success = not failing
        if ((report["status"] == "PASS") != success or report["reason"] != (failing[0] if failing else "")
                or success and any(counts[name] == 0 for name in QC_COUNT_FIELDS)):
            raise ValueError("verdict")
        return json.loads(json.dumps(report, allow_nan=False))
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        raise ValueError("QC_REPORT_INVALID") from error


def _report_path(path):
    path = Path(path)
    if (not path.is_absolute() or ".." in path.parts
            or any(item.is_symlink() for item in (path, *path.parents))):
        raise ValueError("QC_REPORT_PATH_INVALID")
    return path


def _report_canonical(report):
    return (json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def write_qc_report(report, output: Path) -> str:
    """Publish a complete report once after fsync, retaining its staging artifact.

    The no-replace hard link is the atomic publication boundary. Staging names,
    including unsuccessful writes, remain available as deletion candidates.
    Publication alone never grants result, Coordinator or training authority.
    """
    document = validate_qc_report(report)
    target = _report_path(output)
    if target.exists():
        raise ValueError("QC_REPORT_ALREADY_WRITTEN")
    payload = _report_canonical(document)
    staged = target.parent / ("." + target.name + "." + uuid.uuid4().hex + ".pending")
    directory = None
    try:
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory)
        os.link(staged, target, follow_symlinks=False)
        os.fsync(directory)
    except FileExistsError as error:
        raise ValueError("QC_REPORT_ALREADY_WRITTEN") from error
    except OSError as error:
        raise ValueError("QC_REPORT_UNWRITABLE") from error
    finally:
        if directory is not None:
            os.close(directory)
    return hashlib.sha256(payload).hexdigest()


def read_qc_report(path: Path):
    """Read the canonical complete report; callers must independently recompute it."""
    path = _report_path(path)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("QC_REPORT_INVALID")
            payload = stream.read()
        document = validate_qc_report(json.loads(payload))
        if payload != _report_canonical(document):
            raise ValueError("QC_REPORT_INVALID")
        return document
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("QC_REPORT_INVALID") from error


def _raw_physics_samples(events):
    """The raw physics samples of the retained, already verified ``physics_chunk`` events."""
    samples = []
    for event in events:
        if type(event) is dict and event.get("kind") == "physics_chunk":
            samples.extend(event["payload"]["raw_chunk"]["chunk"]["samples"])
    return samples


def _read_teacher_manifest(path):
    """(document or None, sha256 or None): a missing or unreadable Teacher manifest is a QC reason, not a crash."""
    try:
        data = _report_path(path).read_bytes()
        document = json.loads(data)
    except (OSError, ValueError):
        return None, None
    return (document if type(document) is dict else None), hashlib.sha256(data).hexdigest()


def physics_chunk_count(events) -> int:
    """How many raw physics chunks the episode retained: the `physics` count of the schema-3 QC report.

    `physics.jsonl` held the Teacher-side physics observations of the in-child capture; since the Recorder was decoupled nothing
    writes it, so its row count was always 0 and a passing report could not validate (a passing report needs every count above 0).
    The raw chunks are the physics the episode carries.
    """
    return sum(1 for event in events if type(event) is dict and event.get('kind') == 'physics_chunk')


def recompute_native_qc(episode_root, *, scope, inputs_manifest, teacher_manifest=None, topic_loss=None):
    """Read-only current data QC (schema 3); see `_recompute_native_qc`. The verifiers it repeats run once per session."""
    import contextlib

    from .qc_session import ENTRY_OWNERS, active, qc_session

    session = active()
    if session is not None and session.owner in ENTRY_OWNERS:
        return _recompute_for_readback(session, episode_root, scope=scope, inputs_manifest=inputs_manifest,
                                       teacher_manifest=teacher_manifest, topic_loss=topic_loss)
    with contextlib.nullcontext() if session is not None else qc_session():
        return _recompute_native_qc(episode_root, scope=scope, inputs_manifest=inputs_manifest,
                                    teacher_manifest=teacher_manifest, topic_loss=topic_loss)


def _recompute_for_readback(session, episode_root, *, scope, inputs_manifest, teacher_manifest, topic_loss):
    """One full recomputation per readback process, shared by the stages that each need "the QC of these files".

    Only this result is shared; the stored report, the journal, the index, the receipt and every eligibility decision are read and
    decided afresh by each stage. The reuse key is a full-content fingerprint hashed without the memo's stat cache (every byte of the
    episode, the scope, the frozen inputs, the Teacher manifest and the gate document), the QC code digest and the arguments. It is
    computed before and after the recomputation and again at every lookup: any difference fails closed (READBACK_INPUT_CHANGED). A
    stat key could hit stale after an in-place rewrite that restores the size and the mtime."""
    import copy

    from . import qc_memo

    def content():
        return qc_memo.fingerprint(episode_root=episode_root, scope=scope, inputs_manifest=inputs_manifest,
                                   teacher_manifest=teacher_manifest, topic_loss=topic_loss, use_cache=False)

    key = (str(episode_root), str(scope), str(inputs_manifest), str(teacher_manifest), str(topic_loss), qc_memo.code_digest())
    before = content()
    entry = session.qc_results.get(key)
    if entry is not None:
        if entry["fingerprint"] != before:
            raise ValueError("READBACK_INPUT_CHANGED")
        session.qc_hits += 1
        return copy.deepcopy(entry["report"])
    report = _recompute_native_qc(episode_root, scope=scope, inputs_manifest=inputs_manifest,
                                  teacher_manifest=teacher_manifest, topic_loss=topic_loss)
    if content() != before:
        raise ValueError("READBACK_INPUT_CHANGED")
    session.qc_results[key] = {"fingerprint": before, "report": copy.deepcopy(report), "code_digest": qc_memo.code_digest()}
    session.note("recompute_native_qc")
    return report


def _recompute_native_qc(episode_root, *, scope, inputs_manifest, teacher_manifest=None, topic_loss=None):
    """Read-only current data QC (schema 3), suitable for an installed fresh process.

    The caller supplies the original run scope and original frozen input set. Episode-local copies cannot substitute
    for either external binding. Every data check is unchanged: the sealed episode and audit, the physical rows, the
    complete native collection boundaries and the original-source verification all still raise on any defect. What is
    gone is the task judgement: neither the episode seal's ``pick_place_validation_success`` nor ``endpoint_pose_v1`` is a criterion.
    The only added check is ``verify_teacher_references``, a data-integrity cross-check against the Teacher manifest
    (default ``<attempt>/dynamic/dynamic-execute-manifest.json``, beside the episode). A legal report remains separate
    from the Coordinator's durable commit authority.
    """
    from .diagnostic_episode_inputs import verify_frozen_inputs
    from .recorder import verify_episode_seal
    from .scene_association import canonical

    root = _report_path(episode_root)
    scope_path, frozen_path = _report_path(scope), _report_path(inputs_manifest)
    frozen = verify_frozen_inputs(frozen_path)
    if (frozen.get('mode') not in ('preselected_target_diagnostic','formal')
            or not {'runtime_policy','execution_snapshot'} <= set(frozen)):
        raise ValueError('NATIVE_QC_CURRENT_INPUTS_REQUIRED')
    audit_root = root/'audit'
    manifest_path = audit_root/'audit-manifest.json'
    local_inputs = json.loads(_report_path(audit_root/'inputs.json').read_bytes())
    if canonical(frozen) != canonical(local_inputs):
        raise ValueError('NATIVE_QC_ORIGINAL_INPUTS_MISMATCH')
    scope_document = json.loads(scope_path.read_bytes())
    if (scope_document.get('mode') != frozen['mode']
            or scope_document.get('inputs_sha256') != frozen['inputs_sha256']):
        raise ValueError('NATIVE_QC_ORIGINAL_SCOPE_MISMATCH')
    summary = verify_episode_physical_audit(root, manifest_path, scope_path)
    episode = verify_episode_seal(root/'seal.json', audit_manifest=manifest_path, scope=scope_path)
    manifest = verify_audit_manifest(manifest_path)
    events = read_verified_rows(audit_root, 'events.jsonl')
    verify_native_collection_events(events, identity=manifest['identity'], window=manifest['window'], inputs=frozen)
    acquisitions = read_verified_rows(audit_root, 'acquisitions.jsonl')
    teacher, teacher_sha256 = _read_teacher_manifest(
        root.parent/'dynamic'/'dynamic-execute-manifest.json' if teacher_manifest is None else teacher_manifest)
    reference = verify_teacher_references(teacher, identity=manifest['identity'], window=manifest['window'],
                                          physics_steps=_raw_physics_samples(events))
    reference['details']['teacher_manifest_sha256'] = teacher_sha256
    from .topic_loss import qc_check as topic_loss_check
    loss = topic_loss_check(root, identity=manifest['identity'], path=topic_loss)
    checks = {"episode_data": dict(status='PASS', reason=''), REFERENCE_CHECK: reference, TOPIC_LOSS_CHECK: loss}
    failing = [item for item in (reference, loss) if item['status'] == 'FAIL']
    document = dict(kind='ACT_EPISODE_QC', schema_version=QC_SCHEMA_VERSION, rule_version=QC_RULE_VERSION,
        status='FAIL' if failing else 'PASS', identity=manifest['identity'], reason=failing[0]['reason'] if failing else '',
        episode_seal_sha256=_manifest_digest(root/'seal.json'), audit_manifest_sha256=_manifest_digest(manifest_path),
        inputs_sha256=frozen['inputs_sha256'], scope_sha256=_manifest_digest(scope_path),
        counts=dict(records=episode['record_count'], head_acquisitions=sum(row['camera']=='head' for row in acquisitions),
            wrist_acquisitions=sum(row['camera']=='wrist' for row in acquisitions),
            references=len(read_verified_rows(audit_root, REFERENCE_STREAM)), events=len(events),
            physics=physics_chunk_count(events), native_steps=summary['native_steps']), checks=checks)
    return validate_qc_report(document)


def read_verified_rows(root: Path, stream: str) -> list[dict]:
    """The rows a fresh process re-reads from the sealed audit, in file order."""

    path = Path(root) / stream
    if not path.is_file():
        return []
    return cached_lines(path, _parse_stream_rows, "lenient")


def _parse_stream_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def _manifest_digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
