"""Independent basic post-run checks over versioned disk originals."""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import statistics
import uuid

from .head_run_reader import (AuditToolError, MAX_CORRELATIONS, canonical_digest,
                              is_integer, normalized, open_regular)

RULESET_ID = 'head-file-postrun-basic'
EXECUTION_RULES = tuple('HFA-%03d' % number for number in range(2, 9)) + ('HFA-011',)
CAPABILITIES = {name: 'NOT_ASSESSED' for name in (
    'wire_payload_equivalence', 'trajectory_safety_reproof', 'pointing_algorithm_reproof',
    'model_bytes_rehash', 'source_install_closure_rehash', 'owner_lock_atomicity',
    'whole_machine_cleanup')}
KINDS = {
    'JOINT', 'IMAGE', 'INFO', 'HEAD_PREPARED_DISPATCH_TRACE', 'INVENTORY_OWNED',
    'HEAD_ACTION_SDK_RETURNED', 'HEAD_ACTION_SDK_ACCEPTANCE', 'HEAD_ACTION_SDK_RESULT',
    'HEAD_ACTION_SDK_CANCEL', 'HEAD_ACTION_STATUS', 'HEAD_ACTION_SERVICE_REQUEST',
    'HEAD_ACTION_CANCEL', 'HEAD_ACTION_GET_RESULT', 'SEARCH_OWNED_GOAL_DISPATCHED',
    'SEARCH_OWNED_GOAL_SETTLED', 'SEARCH_OBSERVATION_REQUESTED',
    'LIVE_STOPPED_OBSERVATION_FINISHED', 'LIVE_STOPPED_OBSERVATION_HANDOFF',
    'SEARCH_EXPOSURE_DECISION', 'SEARCH_OBSERVATION_DISCARDED', 'SEARCH_CONTROLLER_TERMINAL',
    'EXECUTION_LOOP_TERMINAL', 'EXECUTION_LOOP_REFUSED', 'FAULT', 'STOP_REQUEST',
    'NATIVE_CLOSE', 'CANCEL_STOP', 'EXECUTION_LOOP_RETIREMENT', 'EXECUTION_STACK_RETIREMENT',
    'EXECUTION_CHILD_RETIREMENT', 'EXECUTION_OWNER_DESCRIPTOR', 'NATIVE_CHILD_BOUND',
    # the startup protocol of the stock-controller subclass
    'CONTROLLER_READBACK', 'DEADMAN_ARMED', 'GRAPH_PROOF', 'STARTUP_STOP_WINDOW',
    'CONTROLLER_SWITCH_PLANNED', 'DEADMAN_CLOSED_PLANNED', 'DEADMAN_CLOSED_FAULT',
    'STOCK_STOP_PROOF',
}
STOP_WINDOW_SAMPLES = 51


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def ns_interval(seconds):
    if not finite(seconds):
        return None
    center = seconds * 1_000_000_000
    error = math.ulp(float(seconds)) * 500_000_000 + 1
    return (math.floor(center-error), math.ceil(center+error))


def precedes(first, second, *, inclusive=False):
    """Use three-valued ordering when saved float clock intervals overlap."""
    if first is None or second is None:
        return None
    if first[1] < second[0] or (inclusive and first[1] == second[0]):
        return True
    if first[0] > second[1] or (not inclusive and first[0] == second[1]):
        return False
    return None


def callback_uuid(original):
    values = original.get('uuid') if isinstance(original, dict) else None
    if not isinstance(values, list) or len(values) != 16 or \
            any(not is_integer(value) or not 0 <= value <= 255 for value in values):
        return None
    return str(uuid.UUID(bytes=bytes(values)))


def summarize(values):
    values = sorted(values)
    if not values:
        return dict(count=0, min=None, max=None, median=None, p95=None)
    return dict(count=len(values), min=values[0], max=values[-1],
                median=statistics.median(values), p95=values[math.ceil(.95*len(values))-1])


class BasicAudit:
    def __init__(self, reader):
        self.reader = reader
        self.manifest = reader.documents.get('manifest.json') or {}
        self.completion = reader.documents.get('completion.json') or {}
        if str(normalized(reader.run_root / 'manifest.json')) in reader.tainted:
            self.manifest = {}
        if str(normalized(reader.run_root / 'completion.json')) in reader.tainted:
            self.completion = {}
        self.config = reader.trusted_external('development_config') or {}
        self.values = self.config.get('values', {})
        self.policy = reader.trusted_external('local_policy') or {}
        self.rules = {f'HFA-{number:03d}': [] for number in range(1, 12)}
        self.findings = []
        self.rows = defaultdict(list)
        self.counts = Counter()
        self.metrics = dict(goals=[], observations=[], stop={}, diagnostics={})
        self.search_outcome = 'UNKNOWN'
        self.goals = {}
        self.requests = {}
        self.observations = {}
        self.decisions = {}
        self.branch_no_observation = False

    def check(self, rule, truth, code, event=None, *, expected=None, observed=None, calculation=None):
        verdict = 'UNKNOWN' if truth is None else ('HOLDS' if truth else 'VIOLATED')
        evidence = self.reader.evidence(self.reader.run_root / 'events.jsonl',
            line=None if event is None else event['_line'],
            sequence=None if event is None else event['sequence'])
        self.rules[rule].append(dict(verdict=verdict, code=code, evidence=evidence))
        if truth is not True:
            affected = ['stop'] if rule == 'HFA-009' else (['exit_cleanup'] if rule == 'HFA-010'
                                                       else ['execution_checks'])
            self.findings.append(dict(code=code, rule=rule,
                category='EVIDENCE_GAP' if truth is None else 'CONTRACT',
                severity='WARNING' if truth is None else 'ERROR', affected_results=affected,
                evidence=evidence, identifiers=self.identifiers(event), expected=expected,
                observed=observed, calculation=calculation))

    def identifiers(self, event):
        record = {} if event is None else event['record']
        if 'record' in record and isinstance(record['record'], dict):
            record = record['record']
        return {key: record.get(key) for key in ('goal_uuid', 'observation_sequence',
                                               'sequence', 'source_ns', 'motion_epoch')}

    def not_applicable(self, rule, reason):
        self.rules[rule].append(dict(verdict='NOT_APPLICABLE', code=reason, evidence=None))

    def diagnostic(self, code, event=None, observed=None):
        self.findings.append(dict(code=code, category='DIAGNOSTIC', severity='INFO',
            affected_results=[], evidence=self.reader.evidence(self.reader.run_root / 'events.jsonl',
                line=None if event is None else event['_line'],
                sequence=None if event is None else event['sequence']),
            identifiers=self.identifiers(event), expected=None, observed=observed, calculation=None))

    def budget(self, rule, code, end_interval, start_interval, seconds, event=None):
        if end_interval is None or start_interval is None or not finite(seconds):
            self.check(rule, None, code+'_MISSING', event)
            return None
        elapsed = (end_interval[0]-start_interval[1], end_interval[1]-start_interval[0])
        limit = math.floor(seconds*1e9)
        truth = False if elapsed[0] > limit or elapsed[1] < 0 else (
            True if 0 <= elapsed[0] and elapsed[1] <= limit else None)
        self.check(rule, truth, code, event, expected=dict(min_ns=0, max_ns=limit),
                   observed=dict(elapsed_interval_ns=elapsed), calculation='same-run monotonic only')
        return dict(elapsed_interval_ns=elapsed, budget_ns=limit)

    def index(self):
        run = self.manifest.get('run')
        refs = self.manifest.get('refs', {})
        expected_digests = dict(source_sha256=self.manifest.get('source_manifest', {}).get('sha256'),
            config_sha256=refs.get('development_config', {}).get('sha256'),
            model_sha256=refs.get('weights', {}).get('sha256'))
        identity_known = isinstance(run, dict) and set(run) == {'run_id','epoch','session_id','generation'}
        self.check('HFA-002', True if identity_known else None, 'RUN_IDENTITY_AVAILABLE')
        controller = None
        for event in self.reader.events():
            self.counts[event['kind']] += 1
            if event['kind'] in KINDS:
                group = self.rows[event['kind']]
                if len(group) >= MAX_CORRELATIONS:
                    raise AuditToolError('CORRELATION_LIMIT')
                group.append(event)
            if identity_known:
                if event['run'] != run:
                    self.check('HFA-002', False, 'RUN_IDENTITY_CONFLICT', event,
                               expected=run, observed=event['run'])
            for key, value in expected_digests.items():
                if value is not None and event[key] != value:
                    self.check('HFA-002', False, 'EVENT_DIGEST_BINDING_CONFLICT', event,
                               expected={key:value}, observed={key:event[key]})
            record = event['record']
            candidates = [record]
            for name in ('record','request','inventory_record'):
                if isinstance(record.get(name), dict):
                    candidates.append(record[name])
            if isinstance(record.get('prepared_proof'), dict):
                candidates.append(record['prepared_proof'].get('scope', {}))
            for scoped in candidates:
                if isinstance(run, dict):
                    for name in ('epoch','session_id','generation'):
                        if name in scoped and (type(scoped[name]) is not type(run.get(name)) or
                                               scoped[name] != run.get(name)):
                            self.check('HFA-002', False, 'SCOPED_IDENTITY_CONFLICT', event,
                                       expected={name:run.get(name)}, observed={name:scoped[name]})
                for name in ('policy_sha256','simulation_policy_sha256'):
                    if name in scoped and self.manifest.get('simulation_policy_sha256') is not None and \
                            scoped[name] != self.manifest['simulation_policy_sha256']:
                        self.check('HFA-002', False, 'POLICY_IDENTITY_CONFLICT', event)
                identity = scoped.get('controller_identity')
                if isinstance(identity, dict):
                    generation = None if not isinstance(run, dict) else run.get('generation')
                    self.check('HFA-002', None if generation is None or identity.get('generation') is None else
                               is_integer(identity['generation']) and identity['generation'] == generation,
                               'CONTROLLER_GENERATION_MATCH', event)
                    if controller is None:
                        controller = identity
                    elif identity != controller:
                        self.check('HFA-002', False, 'CONTROLLER_BOOT_CONFLICT', event)
        has_goals = bool(self.rows['HEAD_ACTION_SDK_RETURNED'] or self.rows['HEAD_PREPARED_DISPATCH_TRACE'])
        if has_goals:
            available = None if not controller or controller.get('boot') is None or \
                controller.get('incarnation') is None else \
                all(isinstance(controller[key], str) and bool(controller[key])
                    for key in ('boot', 'incarnation'))
            self.check('HFA-002', available,
                       'CONTROLLER_BOOT_AVAILABLE')
        if not identity_known or any(value is None for value in expected_digests.values()):
            self.check('HFA-002', None, 'MANIFEST_IDENTITY_BINDING_GAP')
        inputs = self.reader.trusted_external('execution_inputs') or self.reader.trusted_external('inputs')
        if isinstance(inputs, dict) and isinstance(inputs.get('run'), dict):
            self.check('HFA-002', inputs['run'] == run if identity_known else None,
                       'INPUT_RUN_IDENTITY_MATCH')
        self.branch_no_observation = bool(self.rows['FAULT'] or self.rows['EXECUTION_LOOP_REFUSED']) \
            and not self.rows['SEARCH_OBSERVATION_REQUESTED']

    def goal_checks(self):
        prepared = self.rows['HEAD_PREPARED_DISPATCH_TRACE']
        sent = self.rows['HEAD_ACTION_SDK_RETURNED']
        if not prepared and not sent:
            if self.branch_no_observation:
                self.not_applicable('HFA-003','NO_ACTION_DISPATCH_BEFORE_RECORDED_FAULT')
                self.not_applicable('HFA-004','NO_TYPED_ACTION_DISPATCH')
            return
        all_goal_ids = set()
        for event in prepared + sent:
            goal = event['record'].get('goal_uuid')
            if goal is not None:
                all_goal_ids.add(goal)
                if len(all_goal_ids) > MAX_CORRELATIONS:
                    raise AuditToolError('GOAL_CORRELATION_LIMIT')
        for goal in sorted(all_goal_ids):
            group = {kind:[e for e in self.rows[kind] if e['record'].get('goal_uuid') == goal]
                     for kind in ('HEAD_PREPARED_DISPATCH_TRACE','HEAD_ACTION_SDK_RETURNED',
                         'HEAD_ACTION_SDK_ACCEPTANCE','HEAD_ACTION_SDK_RESULT','HEAD_ACTION_STATUS',
                         'HEAD_ACTION_SERVICE_REQUEST','HEAD_ACTION_CANCEL','HEAD_ACTION_GET_RESULT')}
            trace = group['HEAD_PREPARED_DISPATCH_TRACE']
            sends = group['HEAD_ACTION_SDK_RETURNED']
            self.check('HFA-003', False if len(sends)>1 else (True if len(sends)==1 else None),
                       'UUID_SINGLE_DISPATCH', (sends or trace)[0], observed=len(sends))
            self.check('HFA-003', True if len(trace)==1 else (False if len(trace)>1 else None),
                       'UUID_TYPED_TRACE', (trace or sends)[0])
            terminal_events = group['HEAD_ACTION_SDK_RESULT'] + group['HEAD_ACTION_GET_RESULT']
            statuses = group['HEAD_ACTION_STATUS']
            acceptance = group['HEAD_ACTION_SDK_ACCEPTANCE']
            independent = bool(group['HEAD_ACTION_GET_RESULT'])
            self.check('HFA-003', True if acceptance or (independent and statuses and
                group['HEAD_ACTION_CANCEL'] and self.rows['FAULT']) else None,
                'SDK_ACCEPTANCE_OR_INDEPENDENT_UNKNOWN_RECONCILIATION', (trace or sends)[0])
            for event in acceptance:
                original = event['record'].get('original', {})
                raw = callback_uuid(original.get('goal_id', {}))
                self.check('HFA-003', None if raw is None else raw == goal,
                           'ACCEPTANCE_UUID_MATCH', event)
                self.check('HFA-003', original.get('accepted') if type(original.get('accepted')) is bool
                           else None, 'SDK_SERVER_ACCEPTED', event)
            for event in statuses:
                original = event['record'].get('original', {})
                raw = callback_uuid(original.get('goal_info', {}).get('goal_id', {}))
                self.check('HFA-003', None if raw is None else raw == goal, 'STATUS_UUID_MATCH', event)
            self.check('HFA-003', True if terminal_events else None,
                       'ORIGINAL_TERMINAL_AVAILABLE', (trace or sends)[0])
            final = None
            for event in terminal_events:
                original = event['record'].get('original', {})
                code = original.get('status')
                error_code = original.get('result', {}).get('error_code')
                self.check('HFA-003', None if code is None else is_integer(code) and code in (4,5,6),
                           'TERMINAL_STATUS_VALID', event)
                self.check('HFA-003', None if error_code is None else is_integer(error_code),
                           'RESULT_ERROR_CODE_VALID', event)
                terminal_statuses = [e['record'].get('original', {}).get('status') for e in statuses
                                     if e['record'].get('original', {}).get('status') in (4,5,6)]
                self.check('HFA-003', None if code is None or not terminal_statuses else code in terminal_statuses,
                           'TERMINAL_STATUS_ORIGINAL_MATCH', event)
                if code == 4 and error_code is not None and error_code != 0:
                    self.check('HFA-004', False, 'SUCCESS_TERMINAL_ERROR_CONFLICT', event)
                final = event
            requests = group['HEAD_ACTION_SERVICE_REQUEST']
            for kind in ('HEAD_ACTION_CANCEL','HEAD_ACTION_GET_RESULT'):
                for event in group[kind]:
                    cancel=kind=='HEAD_ACTION_CANCEL'
                    matched=[e for e in requests if ('goal_info' in e['record'].get('original',{}))==cancel]
                    self.check('HFA-003',True if matched else None,
                               'SERVICE_RESPONSE_REQUEST_ORIGINAL_MISSING' if not matched else
                               'SERVICE_RESPONSE_REQUEST_ORIGINAL_MATCH',event)
            for event in requests:
                original = event['record'].get('original', {})
                cancel = 'goal_info' in original
                raw = callback_uuid((original.get('goal_info', {}) if cancel else original).get('goal_id', {}))
                self.check('HFA-003', None if raw is None else raw == goal, 'SERVICE_REQUEST_UUID_MATCH', event)
                replies = group['HEAD_ACTION_CANCEL'] if cancel else group['HEAD_ACTION_GET_RESULT']
                self.check('HFA-003', True if replies else None, 'CONDITIONAL_SERVICE_RESPONSE', event)
            for event in group['HEAD_ACTION_CANCEL']:
                original = event['record'].get('original', {})
                cancel_ids = [callback_uuid(item.get('goal_id', {}))
                              for item in original.get('goals_canceling', []) if isinstance(item, dict)]
                self.check('HFA-003', None if 'return_code' not in original else
                    is_integer(original['return_code']) and original['return_code'] == 0 and
                    goal in cancel_ids, 'CANCEL_REPLY_UUID_MATCH', event)
            if not requests and not independent:
                self.diagnostic('CANCEL_GET_RESULT_NOT_APPLICABLE_NORMAL_BRANCH', (trace or sends)[0])
            inventory = trace[0]['record'].get('inventory_record', {}) if trace else {}
            if inventory.get('goal_uuid') is not None:
                self.check('HFA-003', inventory['goal_uuid'] == goal, 'TYPED_INVENTORY_UUID_MATCH', trace[0])
            trajectory = inventory.get('typed_goal', {}).get('trajectory')
            if not isinstance(trajectory, dict):
                self.check('HFA-004', None, 'TYPED_TRAJECTORY_MISSING', (trace or sends)[0])
            else:
                self.trajectory(trajectory, trace[0])
                points=trajectory.get('points',[])
                final_positions=points[-1].get('positions') if points and isinstance(points[-1],dict) else None
                for event in self.rows['SEARCH_OWNED_GOAL_DISPATCHED']+self.rows['SEARCH_OWNED_GOAL_SETTLED']:
                    command=event['record'].get('command',{})
                    if command.get('goal_uuid')==goal:
                        target=command.get('target_rad')
                        self.check('HFA-004',None if final_positions is None or target is None else
                            len(final_positions)==1 and finite(target) and final_positions[0]==target,
                            'TYPED_FINAL_POSITION_DISPATCH_MATCH',event)
            self.goals[goal] = dict(trace=trace[0] if trace else None, terminal=final,
                                   statuses=statuses, trajectory=trajectory)
            timing = dict(goal_uuid=goal, terminal_status=None if final is None else
                          final['record'].get('original', {}).get('status'))
            if sends and final:
                a=sends[0]['record'].get('callback_wall_ns');b=final['record'].get('callback_wall_ns')
                if is_integer(a) and is_integer(b):
                    timing['sdk_to_terminal_ns']=b-a
            self.metrics['goals'].append(timing)

    def trajectory(self, trajectory, event):
        names = trajectory.get('joint_names')
        points = trajectory.get('points')
        self.check('HFA-004', None if names is None else names == ['neck_yaw_joint'],
                   'TYPED_NECK_JOINT_SCOPE', event)
        if not isinstance(points, list) or not points:
            self.check('HFA-004', None, 'TYPED_POINTS_MISSING', event)
            return
        previous = -1
        interval = self.values.get('lock_valid_neck_rad')
        for point in points:
            if not isinstance(point, dict):
                self.check('HFA-004', False, 'TRAJECTORY_POINT_INVALID', event)
                continue
            for name in ('positions','velocities','accelerations'):
                vector = point.get(name)
                valid = isinstance(vector, list) and (len(vector)==1 or
                    (name!='positions' and not vector)) and all(finite(x) for x in vector)
                self.check('HFA-004', None if vector is None else valid, 'POINT_VECTOR_'+name.upper(), event)
            duration = point.get('time_from_start', {})
            sec,nano=duration.get('sec'),duration.get('nanosec')
            valid=is_integer(sec) and sec>=0 and is_integer(nano) and 0<=nano<1_000_000_000
            offset=sec*1_000_000_000+nano if valid else -1
            self.check('HFA-004', valid and offset>previous, 'POINT_TIME_STRICTLY_INCREASING', event)
            previous=offset
            positions=point.get('positions')
            if isinstance(interval,list) and len(interval)==2 and isinstance(positions,list):
                self.check('HFA-004', all(finite(x) and interval[0]<=x<=interval[1] for x in positions),
                           'POINT_POSITION_IN_APPROVED_INTERVAL', event)
            else:
                self.check('HFA-004', None, 'APPROVED_JOINT_INTERVAL_MISSING', event)

    def raw_joint(self, event):
        record=event['record']
        names=record.get('raw_names'); positions=record.get('raw_positions');velocities=record.get('raw_velocities')
        if not isinstance(names,list) or names.count('neck_yaw_joint')!=1 or \
                not isinstance(positions,list) or not isinstance(velocities,list) or \
                len(names)!=len(positions) or len(names)!=len(velocities):
            return None
        index=names.index('neck_yaw_joint')
        if not finite(positions[index]) or not finite(velocities[index]):
            return None
        return dict(source_ns=record.get('source_ns'),sequence=record.get('sequence'),
                    wall=ns_interval(record.get('wall_s')),position=positions[index],
                    velocity=velocities[index],valid=record.get('valid') is True,event=event)

    def observations_checks(self):
        requests=self.rows['SEARCH_OBSERVATION_REQUESTED']
        rows=self.rows['LIVE_STOPPED_OBSERVATION_HANDOFF']
        if not requests and not rows and self.branch_no_observation:
            for rule in ('HFA-005','HFA-006','HFA-007','HFA-008'):
                self.not_applicable(rule,'NO_STOPPED_OBSERVATION_BEFORE_RECORDED_FAULT')
            return
        deadlines=set(); epochs=defaultdict(int)
        for event in requests:
            request=event['record'].get('request', {})
            number=request.get('observation_sequence')
            if not is_integer(number):
                self.check('HFA-007',None,'OBSERVATION_REQUEST_ID_MISSING',event)
                continue
            self.check('HFA-007',number not in self.requests,'OBSERVATION_REQUEST_UNIQUE',event)
            self.requests.setdefault(number,event)
            deadline=request.get('search_deadline_ns')
            if is_integer(deadline): deadlines.add(deadline)
            else:self.check('HFA-007',None,'SEARCH_DEADLINE_MISSING',event)
            requested=ns_interval(request.get('requested_wall_s'))
            if requested and is_integer(deadline):
                self.check('HFA-007',precedes(requested,(deadline,deadline)),
                           'REQUEST_WITHIN_ORIGINAL_DEADLINE',event)
        if deadlines:
            self.check('HFA-007',len(deadlines)==1,'ORIGINAL_SEARCH_DEADLINE_UNCHANGED',requests[0])
        # This observable deadline also appears in the frozen prepared proof.
        for event in self.rows['HEAD_PREPARED_DISPATCH_TRACE']:
            declared=event['record'].get('prepared_proof',{}).get('search_deadline_ns')
            if declared is not None and deadlines:
                self.check('HFA-007',declared in deadlines,'PREPARED_SEARCH_DEADLINE_MATCH',event)
        for event in rows:
            row=event['record'].get('record',{})
            number=row.get('observation_sequence')
            if not is_integer(number):
                self.check('HFA-006',None,'RESULT_JOB_ID_MISSING',event);continue
            self.check('HFA-006',number not in self.observations,'RESULT_JOB_UNIQUE',event)
            self.observations.setdefault(number,event)
            finished=[e for e in self.rows['LIVE_STOPPED_OBSERVATION_FINISHED'] if
                      e['record'].get('record',{}).get('observation_sequence')==number]
            for original in finished:
                # Handoff may add a decision-clock receipt, but never rewrite the
                # completed job/frame/detections or its request identity.
                fields=('source_ns','sequence','motion_epoch','observation_sequence','observation_request',
                        'observation_outcome','detections','payload_sha256','completion_wall_s')
                previous=original['record']['record']
                self.check('HFA-006',all(previous.get(k)==row.get(k) for k in fields),
                           'FINISHED_HANDOFF_JOB_PAYLOAD_MATCH',event)
            request_event=self.requests.get(number)
            if request_event is None:
                self.check('HFA-006',None,'RESULT_REQUEST_ORIGINAL_MISSING',event);continue
            request=request_event['record']['request']
            self.check('HFA-006',row.get('observation_request')==request,'RESULT_REQUEST_MATCH',event)
            for field in ('session_id','epoch','generation','motion_epoch'):
                self.check('HFA-006',None if field not in row else row[field]==request.get(field),
                           'RESULT_'+field.upper()+'_MATCH',event)
            if 'observation_request_sha256' in row:
                self.check('HFA-006',row['observation_request_sha256']==canonical_digest(request),
                           'OBSERVATION_REQUEST_DIGEST_MATCH',event)
            self.stopped_capture(request,row,event)
            timing=dict(observation_sequence=number,frame_source_ns=row.get('source_ns'),
                motion_epoch=row.get('motion_epoch'),outcome=row.get('observation_outcome'))
            job_start=ns_interval(row.get('job_started_wall_s'))
            end=ns_interval(row.get('completion_wall_s'))
            if end and job_start:
                timing['inference_duration_interval_ns']=[end[0]-job_start[1],end[1]-job_start[0]]
            self.metrics['observations'].append(timing)
        for event in self.rows['SEARCH_OBSERVATION_DISCARDED']:
            number=event['record'].get('observation_sequence');row=self.observations.get(number)
            if row is None:
                self.check('HFA-006',None,'DISCARD_RESULT_ORIGINAL_MISSING',event)
            else:
                epoch=row['record']['record'].get('motion_epoch');epochs[epoch]+=1
                self.check('HFA-006',event['record'].get('outcome') in ('EXPIRED','SHORT_DROP'),
                           'LEGAL_DISCARD_OUTCOME',event)
            self.diagnostic('LEGAL_OBSERVATION_DISCARD_RECORDED',event)
        total=sum(epochs.values())
        per_stop=self.policy.get('max_reobservations_per_stop');maximum=self.policy.get('max_reobservations_total')
        self.check('HFA-007',None if not is_integer(maximum) else total<=maximum,'REOBSERVATION_TOTAL_BOUND')
        self.check('HFA-007',None if not is_integer(per_stop) else all(n<=per_stop for n in epochs.values()),
                   'REOBSERVATION_PER_STOP_BOUND')
        for number,event in self.requests.items():
            self.check('HFA-007',True if number in self.observations else None,
                       'REQUEST_HAS_ORIGINAL_COMPLETION',event)
        self.consumption_and_lock()

    def stopped_capture(self, request, row, event):
        if row.get('observation_outcome') != 'VALID':
            self.diagnostic('NONVALID_OBSERVATION_NOT_CAPTURE_PROOF',event)
            return
        source=row.get('source_ns');floor=request.get('settled_source_floor_ns')
        self.check('HFA-005',None if not is_integer(source) or not is_integer(floor) else source>floor,
                   'CAPTURE_AFTER_SETTLED_SOURCE',event)
        settled=ns_interval(request.get('settled_wall_s'))
        for field in ('image_received_wall_s','info_received_wall_s'):
            receipt=ns_interval(row.get(field))
            self.check('HFA-005',precedes(settled,receipt),
                       'CAPTURE_RECEIPT_AFTER_SETTLED_'+field.upper(),event)
        for field in ('info_source_ns','tf_source_ns'):
            self.check('HFA-005',None if field not in row else row[field]==source,
                       'CAPTURE_'+field.upper()+'_MATCH',event)
        for field, size in (('tf_translation', 3), ('tf_rotation', 4)):
            vector = row.get(field)
            self.check('HFA-005', None if vector is None else
                       isinstance(vector, list) and len(vector) == size and all(finite(x) for x in vector),
                       'CAPTURE_' + field.upper() + '_SHAPE_FINITE', event)
        causal_joint = row.get('causal_joint')
        joint_originals = [original for original in self.rows['JOINT']
                           if original['record'].get('source_ns') == row.get('joint_source_ns')]
        self.check('HFA-005', None if not joint_originals or not isinstance(causal_joint, dict)
                   else any(original['record'] == causal_joint for original in joint_originals),
                   'CAPTURE_USED_JOINT_ORIGINAL_MATCH', event)
        if isinstance(causal_joint, dict):
            joint_source = causal_joint.get('source_ns')
            self.check('HFA-005', None if not is_integer(joint_source) or not is_integer(floor)
                       else joint_source > floor, 'CAPTURE_JOINT_AFTER_SETTLED_SOURCE', event)
            receipt = ns_interval(causal_joint.get('wall_s'))
            self.check('HFA-005', precedes(settled,receipt),
                       'CAPTURE_JOINT_RECEIPT_AFTER_SETTLED', event)
        images=[e for e in self.rows['IMAGE'] if e['record'].get('source_ns')==source]
        infos=[e for e in self.rows['INFO'] if e['record'].get('source_ns')==source]
        self.check('HFA-005',True if images and infos else None,'ORIGINAL_IMAGE_INFO_PAIR_AVAILABLE',event)
        if images and infos:
            image,info=images[0]['record'],infos[0]['record']
            self.check('HFA-005', None if 'valid' not in info else info['valid'] is True,
                       'CAPTURE_ORIGINAL_INFO_VALID', event)
            frame=self.config.get('camera',{}).get('frame_id')
            camera = self.config.get('camera', {})
            width, height = camera.get('width'), camera.get('height')
            expected_image = dict(width=width, height=height, encoding='rgb8', is_bigendian=0,
                                  valid=True, step=width*3 if is_integer(width) else None,
                                  payload_bytes=width*height*3 if is_integer(width) and is_integer(height) else None)
            for field, expected in expected_image.items():
                value = image.get(field)
                truth = None if value is None or expected is None else \
                    type(value) is type(expected) and value == expected
                self.check('HFA-005', truth, 'CAPTURE_IMAGE_' + field.upper() + '_CONTRACT', event)
            self.check('HFA-005',None if frame is None else image.get('frame_id')==info.get('frame_id')==frame and
                image.get('width')==info.get('width') and image.get('height')==info.get('height'),
                'IMAGE_INFO_IDENTITY_SHAPE_MATCH',event)
            for original, field in ((image, 'image_received_wall_s'), (info, 'info_received_wall_s')):
                original_wall = original.get('wall_s')
                self.check('HFA-005', None if original_wall is None or row.get(field) is None else
                           original_wall == row[field], 'CAPTURE_' + field.upper() + '_ORIGINAL_MATCH', event)
            self.check('HFA-005',image.get('payload_sha256')==row.get('payload_sha256'),
                       'CAPTURE_ORIGINAL_RGB_DIGEST_MATCH',event)
            digest = image.get('payload_sha256')
            artifacts = [entry for path, entry in self.reader.files.items()
                         if path.startswith(str(self.reader.run_root / 'artifacts') + '/')
                         and path not in self.reader.tainted and entry['sha256'] == digest
                         and entry['size'] == image.get('payload_bytes')]
            self.check('HFA-005', True if artifacts else None,
                       'CAPTURE_RGB_BYTES_VERIFIED', event)
            self.check('HFA-005',info==row.get('original_info'), 'CAPTURE_ORIGINAL_INFO_MATCH',event)
        settled_events=self.rows['SEARCH_OWNED_GOAL_SETTLED']
        candidate=[e for e in settled_events if e['record'].get('command',{}).get('terminal_source_floor_ns',-1)<
                   (floor if is_integer(floor) else -1) and
                   e['record'].get('command',{}).get('settled_wall_s')==request.get('settled_wall_s')]
        if not candidate:
            self.check('HFA-005',None,'MATCHED_GOAL_SETTLEMENT_MISSING',event)
            return
        command=candidate[-1]['record']['command'];goal=self.goals.get(command.get('goal_uuid'),{})
        terminal=goal.get('terminal');target=command.get('target_rad')
        self.check('HFA-005',True if terminal and terminal['record'].get('original',{}).get('status')==4
                   else None,'MATCHED_ORIGINAL_SUCCESS_TERMINAL',event)
        samples=command.get('confirming_samples',[])
        originals=[]
        for sample in samples:
            found=[e for e in self.rows['JOINT'] if e['record']==sample]
            if found:originals.append(self.raw_joint(found[0]))
        valid=len(originals)>=3 and all(x is not None and x['valid'] for x in originals)
        if valid:
            tolerance=self.config.get('motion',{}).get('goal_tolerance_rad')
            velocity=self.config.get('motion',{}).get('settle_velocity_rad_s')
            valid=finite(target) and finite(tolerance) and finite(velocity) and all(
                abs(x['position']-target)<=tolerance and abs(x['velocity'])<=velocity for x in originals)
            valid=valid and all(b['source_ns']>a['source_ns'] and b['sequence']>a['sequence']
                for a,b in zip(originals,originals[1:]))
            self.check('HFA-004',valid if all(finite(x) for x in (target,tolerance,velocity)) else None,
                       'ACTUAL_JOINT_TARGET_SETTLEMENT',event)
        self.check('HFA-005',True if valid else None,'THREE_ADVANCING_ORIGINAL_SETTLED_JOINTS',event)

    def consumption_and_lock(self):
        by_sequence={}
        for event in self.observations.values():
            row=event['record']['record'];number=row.get('sequence')
            if is_integer(number):by_sequence[number]=event
        lock=0;track=None;epoch=None;last_source=-1
        for event in sorted(self.rows['SEARCH_EXPOSURE_DECISION'],key=lambda e:e['record'].get('observation',{}).get('sequence',-1)):
            decision=event['record'].get('observation',{});number=decision.get('sequence')
            if number in self.decisions:
                self.check('HFA-006',False,'DUPLICATE_RESULT_CONSUMPTION',event)
            self.decisions[number]=event
            observed=by_sequence.get(number)
            if observed is None:
                self.check('HFA-006',None,'CONSUMED_RESULT_ORIGINAL_MISSING',event)
                self.check('HFA-008',None,'LOCK_DETECTOR_ORIGINAL_MISSING',event);continue
            row=observed['record']['record'];source=row.get('source_ns')
            self.check('HFA-006',row.get('observation_outcome')=='VALID','ONLY_VALID_RESULT_CONSUMED',event)
            self.check('HFA-006',decision.get('source_ns')==source,'CONSUMED_FRAME_MATCH',event)
            tick=ns_interval(decision.get('core_tick_wall_s'));deadline=row.get('deadline_ns')
            requested=ns_interval(row.get('observation_request',{}).get('requested_wall_s'))
            if requested and tick:
                new_motion=[e for e in self.rows['HEAD_ACTION_SDK_RETURNED'] if
                    is_integer(e['record'].get('callback_wall_ns')) and
                    requested[1]<e['record']['callback_wall_ns']<tick[0]]
                self.check('HFA-006',not new_motion,'NO_NEW_MOTION_BEFORE_RESULT_CONSUMPTION',event)
            self.check('HFA-006',None if not is_integer(deadline) else
                       precedes(tick,(deadline,deadline),inclusive=True),
                       'RESULT_CONSUMED_BEFORE_DEADLINE',event)
            total_deadline = row.get('observation_request', {}).get('search_deadline_ns')
            self.check('HFA-007', None if not is_integer(total_deadline) else
                       precedes(tick,(total_deadline,total_deadline),inclusive=True),
                       'CONSUMPTION_WITHIN_ORIGINAL_TOTAL_DEADLINE', event)
            for field in ('image_received_wall_s','info_received_wall_s'):
                self.budget('HFA-006','CONSUMED_'+field.upper()+'_AGE',tick,ns_interval(row.get(field)),
                            self.policy.get('perception_max_age_s'),event)
            self.budget('HFA-006','CONSUMED_JOB_DURATION',ns_interval(row.get('completion_wall_s')),
                        ns_interval(row.get('job_started_wall_s')),self.policy.get('perception_job_timeout_s'),event)
            sim=decision.get('current_joint_decision',{}).get('sim_ns')
            age=self.policy.get('perception_max_age_s')
            if is_integer(sim) and is_integer(source) and finite(age):
                self.check('HFA-006',0<=sim-source<=math.floor(age*1e9),'CONSUMED_SIM_SOURCE_AGE',event)
            else:self.check('HFA-006',None,'CONSUMED_SIM_SOURCE_AGE_MISSING',event)
            info=row.get('original_info',{});width=info.get('width');height=info.get('height')
            k=info.get('k');deadband=self.values.get('center_deadband_px')
            detections=row.get('detections');current_track=decision.get('track_id');current_epoch=row.get('motion_epoch')
            if not is_integer(width) or not is_integer(height) or not isinstance(k,list) or len(k)!=9 or \
                    not finite(k[2]) or not finite(deadband) or not isinstance(detections,list):
                self.check('HFA-008',None,'LOCK_GEOMETRY_OR_DETECTOR_FIELDS_MISSING',event);continue
            if current_epoch!=epoch or current_track!=track:
                lock=0
            centered=False
            matches=[d for d in detections if isinstance(d,dict) and d.get('track_id')==current_track]
            if len(matches)==1:
                box=matches[0].get('xyxy')
                if isinstance(box,list) and len(box)==4 and all(finite(x) for x in box):
                    x1,y1,x2,y2=box;center=(x1+x2)/2;vertical=(y1+y2)/2
                    self.check('HFA-008',0<=x1<x2<=width and 0<=y1<y2<=height,'DETECTION_BBOX_WITHIN_IMAGE',event)
                    bounds=self.values.get('vertical_bounds_px',[0,height])
                    confidence = matches[0].get('confidence')
                    class_id = matches[0].get('class_id')
                    min_confidence = self.values.get('min_confidence')
                    min_area = self.values.get('min_area_px2')
                    min_aspect = self.values.get('min_bbox_aspect')
                    eligibility_known = class_id is not None and all(finite(value) for value in
                                            (confidence, min_confidence, min_area, min_aspect))
                    eligible = eligibility_known and is_integer(class_id) and class_id == 0 and \
                        confidence >= min_confidence and \
                        x2 > x1 and (x2-x1)*(y2-y1) >= min_area and \
                        (y2-y1)/(x2-x1) >= min_aspect
                    self.check('HFA-008', eligible if eligibility_known else None,
                               'LOCK_DETECTION_ELIGIBLE', event)
                    if not eligibility_known:
                        lock = None
                        track, epoch, last_source = current_track, current_epoch, source
                        continue
                    centered=eligible and abs(center-k[2])<=deadband and bounds[0]<=vertical<=bounds[1]
                    self.metrics['observations'][list(self.observations).index(row['observation_sequence'])][
                        'horizontal_center_error_px']=center-k[2]
            advancing=is_integer(source) and source>last_source
            self.check('HFA-008',advancing,'LOCK_DISTINCT_ADVANCING_FRAME',event)
            if centered and advancing and row.get('observation_outcome')=='VALID':
                lock = None if lock is None else lock + 1
            else:lock=0
            declared=decision.get('lock_count')
            self.check('HFA-008',None if declared is None or lock is None else is_integer(declared) and declared==lock,
                       'LOCK_COUNT_RECOMPUTED',event,expected=lock,observed=declared,
                       calculation='bbox center - original K principal point; approved center/vertical bounds')
            status=decision.get('decision',{}).get('status')
            if status=='TARGET_LOCKED':
                self.check('HFA-008',None if lock is None else lock>=3,'THREE_VALID_CENTERED_FRAMES_FOR_LOCK',event)
            track,epoch,last_source=current_track,current_epoch,source if is_integer(source) else last_source

    def stop_checks(self):
        origins=self.rows['FAULT'] or self.rows['STOP_REQUEST']
        actions=bool(self.goals or self.rows['INVENTORY_OWNED'])
        if not origins:
            if not actions and self.rows['EXECUTION_LOOP_REFUSED'] and self.reader.integrity_status=='PASS':
                self.not_applicable('HFA-009','ENTRY_REFUSAL_BEFORE_ACTION_NO_STOP_OBLIGATION')
            return
        origin_event=min(origins,key=lambda e:e['record'].get('occurred_ns',e['occurrence_mono_ns']))
        origin=origin_event['record'].get('occurred_ns',origin_event['occurrence_mono_ns'])
        origin=(origin,origin)
        stops=self.rows['CANCEL_STOP']
        retirements = self.rows['EXECUTION_LOOP_RETIREMENT']
        runtimes = [event['record'].get('outcomes', {}).get('runtime', {})
                    for event in retirements]
        self.deadman_stop_checks(origin, runtimes, retirements)
        terminal_floor=0;terminal_mono=origin[0]
        for goal,entry in self.goals.items():
            terminal=entry['terminal']
            self.check('HFA-009',True if terminal and terminal['record'].get('original',{}).get('status') in (4,5,6)
                       else None,'STOP_ALL_OWNED_GOALS_TERMINAL',terminal,observed=goal)
            if terminal:
                terminal_floor=max(terminal_floor,terminal['record'].get('callback_sim_ns',0))
                terminal_mono=max(terminal_mono,terminal['record'].get('callback_wall_ns',terminal['occurrence_mono_ns']))
            if terminal and terminal['record'].get('callback_wall_ns',terminal['occurrence_mono_ns'])>origin[0]:
                requests=[e for e in self.rows['HEAD_ACTION_SERVICE_REQUEST'] if e['record'].get('goal_uuid')==goal
                          and 'goal_info' in e['record'].get('original',{})]
                replies=[e for e in self.rows['HEAD_ACTION_CANCEL'] if e['record'].get('goal_uuid')==goal]
                self.check('HFA-009',True if requests and replies else None,
                           'CONDITIONAL_STOP_CANCEL_ORIGINALS',terminal)
        # Obtain the original simulation clock at the Stop origin with a bounded additional pass.
        stop_source_floor=0
        for event in self.reader.events():
            if event['kind']=='CLOCK' and event['occurrence_mono_ns']<=origin[0]:
                value=event['record'].get('source_ns',event.get('source_stamp_ns'))
                if is_integer(value):stop_source_floor=max(stop_source_floor,value)
        request_wall = origin
        for runtime in runtimes:
            stop = runtime.get('stop', {})
            wall = ns_interval(stop.get('request_wall_s'))
            sim = ns_interval(stop.get('request_sim_s'))
            if wall is not None and sim is not None:
                request_wall = wall
                stop_source_floor = sim[1]
        # Stop samples follow the Stop origin, not the later independent result
        # callback. Terminal inventory and a continuous quiet window meet at
        # confirmation; requiring three new samples after GetResult tightens the
        # frozen producer contract and loses valid fault-stop evidence.
        terminal_floor=stop_source_floor
        until=max((e['occurrence_mono_ns'] for e in stops),default=2**63-1)
        raw=[self.raw_joint(e) for e in self.rows['JOINT']]
        malformed = [event for event, sample in zip(self.rows['JOINT'], raw)
                     if sample is None and ns_interval(event['record'].get('wall_s')) is not None and
                     request_wall[1] < ns_interval(event['record']['wall_s'])[0] <= until]
        raw=[x for x in raw if x and x['wall'] and x['wall'][0]>request_wall[1] and
             is_integer(x['source_ns']) and x['source_ns']>terminal_floor and
             x['wall'][1]<=until]
        raw.sort(key=lambda x:x['sequence'] if is_integer(x['sequence']) else -1)
        limit=self.values.get('stop_velocity_rad_s');quiet=[];proof=None
        for sample in raw:
            valid=sample['valid'] and finite(limit) and abs(sample['velocity'])<=limit
            if quiet:
                valid=valid and sample['source_ns']>quiet[-1]['source_ns'] and sample['wall'][0]>quiet[-1]['wall'][1]
            if not valid:quiet=[];proof=None;continue
            quiet.append(sample)
            if len(quiet)>=3 and proof is None:
                proof=sample
        self.check('HFA-009',True if proof else None,'CONTINUOUS_RAW_QUIET_JOINT_PROOF',
                   None if proof is None else proof['event'],observed=dict(raw_samples=len(raw),quiet_count=len(quiet)))
        if malformed:
            self.check('HFA-009', None, 'STOP_RAW_JOINT_CONTINUITY_GAP', malformed[0])
        if proof:
            self.metrics['stop']['raw_quiet_reaction']=self.budget('HFA-009','PHYSICAL_STOP_BUDGET',
                (max(proof['wall'][0],terminal_mono),max(proof['wall'][1],terminal_mono)),
                origin,self.policy.get('stop_confirmation_timeout_s'),proof['event'])
        if not stops:self.check('HFA-009',None,'CANCEL_STOP_COMPLETION_MISSING')
        for event in stops:
            record=event['record']
            self.check('HFA-009',record.get('cancel_error') is None and record.get('result_error') is None,
                       'STOP_SERVICE_ERRORS_ABSENT',event)
            if record.get('raw_stop_confirmed') is False:
                self.check('HFA-009',False,'REPORTED_STOP_UNCONFIRMED',event)

    def deadman_stop_checks(self, origin, runtimes, retirements):
        """HFA-009: the dead-man close, the stop proof and the end window of a stock-controller run."""
        closes = self.rows['DEADMAN_CLOSED_PLANNED'] + self.rows['DEADMAN_CLOSED_FAULT']
        proofs = self.rows['STOCK_STOP_PROOF']
        receipts = [(event, runtime.get('deadman_close'))
                    for event, runtime in zip(retirements, runtimes)
                    if isinstance(runtime.get('deadman_close'), dict)]
        if not receipts:
            self.check('HFA-009', None, 'DEADMAN_CLOSE_RECEIPT_MISSING')
        for event, receipt in receipts:
            self.check('HFA-009', None if 'ack' not in receipt else receipt['ack'] is True and
                       receipt.get('error') is None, 'DEADMAN_CLOSE_RECEIPT_ACK', event)
        if not closes:
            self.check('HFA-009', None, 'DEADMAN_CLOSE_ORIGINAL_MISSING')
        for event in self.rows['DEADMAN_CLOSED_FAULT']:
            record = event['record']
            end = (event['occurrence_mono_ns'], event['occurrence_mono_ns'])
            self.check('HFA-009', None if 'ack' not in record else record['ack'] is True and
                       record.get('error') is None, 'DEADMAN_CLOSE_ACK', event)
            self.metrics['stop']['deadman_close_reaction'] = self.budget(
                'HFA-009', 'FAULT_TO_DEADMAN_CLOSE', end, origin,
                self.policy.get('fault_reaction_limit_s'), event)
        confirmed = [e for e in self.rows['CANCEL_STOP'] if e['record'].get('raw_stop_confirmed') is True]
        if confirmed and not proofs:
            self.check('HFA-009', None, 'STOCK_STOP_PROOF_MISSING')
        for event in proofs:
            record = event['record']
            window = record.get('window') if isinstance(record.get('window'), dict) else {}
            samples = record.get('raw_stop_samples')
            self.check('HFA-009', None if 'n' not in window else
                       is_integer(window['n']) and window['n'] == STOP_WINDOW_SAMPLES,
                       'STOP_WINDOW_SAMPLE_COUNT', event, observed=window.get('n'))
            floor = record.get('raw_stop_confirmed_sim_ns')
            self.check('HFA-009', None if floor is None or window.get('first_sim_ns') is None else
                       is_integer(floor) and is_integer(window['first_sim_ns']) and window['first_sim_ns'] > floor,
                       'STOP_WINDOW_AFTER_RAW_STOP', event)
            self.check('HFA-009', None if samples is None else
                       isinstance(samples, list) and len(samples) >= 3 and all(is_integer(x) for x in samples)
                       and samples == sorted(set(samples)), 'STOP_PROOF_RAW_SAMPLES', event)
            terminal = record.get('terminal')
            self.check('HFA-009', None if not isinstance(terminal, dict) else
                       all(status in (4, 5, 6) for status in terminal.values()),
                       'STOP_PROOF_TERMINAL_RESULT', event)
            if record.get('deadman_closed_planned') is True:
                planned = [e for e in self.rows['DEADMAN_CLOSED_PLANNED']
                           if e['occurrence_mono_ns'] >= event['occurrence_mono_ns']]
                self.check('HFA-009', bool(planned), 'DEADMAN_CLOSED_PLANNED_AFTER_PROOF', event)
        for event in self.rows['DEADMAN_CLOSED_PLANNED']:
            self.check('HFA-009', True if proofs else None, 'PLANNED_CLOSE_NEEDS_STOP_PROOF', event)

    def exit_checks(self):
        launcher=self.reader.external.get('launcher')
        actual=None if not isinstance(launcher,dict) else launcher.get('actual_os_return_code')
        business=self.completion.get('business_return_code')
        self.check('HFA-010',True if is_integer(actual) else None,'ACTUAL_OS_RETURN_CODE_AVAILABLE')
        self.check('HFA-010',None if not is_integer(actual) or not is_integer(business) else actual==business,
                   'OS_BUSINESS_RETURN_CODE_MATCH',expected=business,observed=actual)
        self.check('HFA-010',True if self.reader.seal is not None else None,'RUN_SEALED_BEFORE_EXIT')
        for kind in ('EXECUTION_LOOP_RETIREMENT','EXECUTION_STACK_RETIREMENT','EXECUTION_CHILD_RETIREMENT'):
            rows=self.rows[kind]
            self.check('HFA-010',True if rows else None,'OWNED_'+kind+'_AVAILABLE')
            for event in rows:
                record=event['record']
                failures=record.get('failures',{})
                self.check('HFA-010',not record.get('forced_kill') and not record.get('errors') and
                    not any(value is not None for value in failures.values()),'OWNED_RETIREMENT_NO_FAILURE',event)
                if 'retired' in record:
                    self.check('HFA-010',record['retired'] is True,'OWNED_STACK_RETIRED',event)
                for child in record.get('children',[]):
                    self.check('HFA-010',None if child.get('rc') is None else
                               is_integer(child['rc']) and child['rc']==0,
                               'OWNED_CHILD_EXIT_CODE',event,observed={k:child.get(k) for k in ('pid','rc')})
        receipt=self.reader.external.get('execution_receipt') or {}
        refs=receipt.get('refs',{})
        post_ref=refs.get('postflight',refs.get('owned_postflight'))
        post=self.reader.external.get('postflight') or self.reader.external.get('owned_postflight')
        if not isinstance(post,dict) or not isinstance(post_ref,dict) or not isinstance(launcher,dict):
            self.check('HFA-010',None,'OWNED_POSTFLIGHT_OR_LAUNCHER_MISSING');return
        domain=post.get('domain') if self.reader.profile=='postflight-domain-key' else post.get('ros_domain_id')
        partition=post.get('partition')
        self.check('HFA-010',str(domain)==str(launcher.get('ros_domain_id')) and
                   partition==launcher.get('partition'),'OWNED_POSTFLIGHT_SCOPE_MATCH')
        commands=post.get('commands',{})
        for key in ('ps','graph'):
            self.check('HFA-010',None if key not in commands else
                       is_integer(commands[key].get('rc')) and commands[key]['rc']==0,
                       'POSTFLIGHT_'+key.upper()+'_COMMAND_SUCCEEDED')
            started = commands.get(key, {}).get('started_ns')
            ended = launcher.get('ended_ns')
            self.check('HFA-010', None if started is None or ended is None else
                       is_integer(started) and is_integer(ended) and 0 < ended <= started,
                       'POSTFLIGHT_' + key.upper() + '_SAMPLED_AFTER_OS_EXIT',
                       expected={'clock': 'outer UTC ns', 'sample_start_at_least_exit': ended},
                       observed={'sample_started_ns': started},
                       calculation='same outer UTC domain; phase and file mtime do not prove sampling order')
        from pathlib import Path
        parent=Path(post_ref['path']).parent
        texts={}
        for key in ('ps','graph'):
            path=parent/(key+'.stdout')
            try:
                with open_regular(path) as stream:
                    data=self.reader._record_stream(path,stream,structured=True)
                texts[key]=data.decode('utf-8','strict')
            except FileNotFoundError:
                self.check('HFA-010',None,'POSTFLIGHT_RAW_'+key.upper()+'_MISSING')
        owner=launcher.get('owner',{})
        owned={owner.get('pid')}
        for event in self.rows['EXECUTION_CHILD_RETIREMENT']:
            owned.update(child.get('pid') for child in event['record'].get('children',[]))
        if 'ps' in texts:
            live=set()
            for line in texts['ps'].splitlines():
                parts=line.split(None,1)
                if parts and parts[0].isdigit():live.add(int(parts[0]))
            self.check('HFA-010',None if not is_integer(owner.get('pid')) else not bool(owned & live),
                       'OWNED_POSTFLIGHT_PIDS_ABSENT',observed=sorted(owned & live))
        if 'graph' in texts:
            descriptors=[e['record'].get('node') for e in self.rows['EXECUTION_OWNER_DESCRIPTOR']]
            nodes=set(texts['graph'].splitlines())
            self.check('HFA-010',True if descriptors and not any(node in nodes for node in descriptors) else None,
                       'OWNED_POSTFLIGHT_NODES_ABSENT')

    def outcome_checks(self):
        terminal=self.rows['SEARCH_CONTROLLER_TERMINAL']
        status=None
        if terminal:status=terminal[-1]['record'].get('result',{}).get('status')
        if status=='TARGET_LOCKED':
            verdict=self.rule_verdict('HFA-008')
            self.search_outcome='LOCKED' if verdict=='HOLDS' else 'UNKNOWN'
            self.check('HFA-011',True if verdict=='HOLDS' else (False if verdict=='VIOLATED' else None),
                       'LOCKED_TERMINAL_INDEPENDENTLY_SUPPORTED',terminal[-1])
        elif status in ('TARGET_NOT_FOUND','TARGET_ABSENT'):
            self.search_outcome='NOT_FOUND';self.check('HFA-011',True,'NOT_FOUND_TERMINAL_SUPPORTED',terminal[-1])
        elif self.rows['FAULT']:
            self.search_outcome='FAILED';self.check('HFA-011',True,'RECORDED_FAULT_SEARCH_FAILURE',self.rows['FAULT'][0])
        elif self.rows['EXECUTION_LOOP_REFUSED']:
            self.search_outcome='REFUSED';self.check('HFA-011',True,'RECORDED_ENTRY_REFUSAL',self.rows['EXECUTION_LOOP_REFUSED'][0])
        elif status is not None:
            self.search_outcome='FAILED';self.check('HFA-011',True,'NONLOCK_TERMINAL_RECORDED',terminal[-1])
        else:self.check('HFA-011',None,'SEARCH_OUTCOME_ORIGINAL_MISSING')
        declared=self.completion.get('execution');business=self.completion.get('business_return_code')
        if self.search_outcome!='UNKNOWN':
            success=self.search_outcome=='LOCKED'
            self.check('HFA-011',None if declared is None or business is None else
                       declared==('SUCCEEDED' if success else 'FAILED') and
                       is_integer(business) and business==(0 if success else 1),
                       'COMPLETION_SEARCH_OUTCOME_MATCH',expected=self.search_outcome,
                       observed=dict(execution=declared,business_return_code=business))
        self.check('HFA-011',None if 'complete_composition' not in self.completion else
                   self.completion['complete_composition'] is True,'COMPOSITION_COMPLETED')

    def rule_verdict(self, rule):
        values={item['verdict'] for item in self.rules[rule]}
        if 'VIOLATED' in values:return 'VIOLATED'
        if 'UNKNOWN' in values or not values:return 'UNKNOWN'
        if 'HOLDS' in values:return 'HOLDS'
        return 'NOT_APPLICABLE'

    def category(self, rules, allow_na=False):
        values={self.rule_verdict(rule) for rule in rules}
        if 'VIOLATED' in values:return 'FAIL'
        if 'UNKNOWN' in values:return 'UNKNOWN'
        if values=={'NOT_APPLICABLE'} and allow_na:return 'NOT_APPLICABLE'
        return 'PASS'

    def run(self):
        self.index()
        if self.reader.profile is None:
            for rule in list(self.rules)[1:]:self.check(rule,None,'UNKNOWN_PRODUCER_PROFILE')
        else:
            self.goal_checks();self.observations_checks();self.stop_checks();self.exit_checks();self.outcome_checks()
        self.metrics['event_counts']=dict(sorted(self.counts.items()))
        self.metrics['goal_timing_summary_ns']=summarize([x['sdk_to_terminal_ns'] for x in
            self.metrics['goals'] if 'sdk_to_terminal_ns' in x])
        self.metrics['inference_timing_summary_ns']=summarize([sum(x['inference_duration_interval_ns'])/2
            for x in self.metrics['observations'] if 'inference_duration_interval_ns' in x])
        self.metrics['sample_limit']='Descriptive single-run samples; no stability claim'
        result=dict(audit_schema_version=1,ruleset_id=RULESET_ID,producer_profile=self.reader.profile,
            integrity={'status':self.reader.integrity_status},search=dict(outcome=self.search_outcome,
                completion_execution=self.completion.get('execution'),business_return_code=self.completion.get('business_return_code'),
                actual_os_return_code=(self.reader.external.get('launcher') or {}).get('actual_os_return_code')),
            execution_checks={'status':self.category(EXECUTION_RULES)},stop={'status':self.category(['HFA-009'],True)},
            exit_cleanup={'status':self.category(['HFA-010'])},coverage=dict(rules={},capabilities=CAPABILITIES.copy()),
            report={'status':'NOT_COMPLETED'},findings=[],metrics=self.metrics)
        self.finalize(result)
        return result

    def finalize(self,result):
        result['integrity']['status']=self.reader.integrity_status
        integrity={'PASS':'HOLDS','FAIL':'VIOLATED','INCOMPLETE':'UNKNOWN'}[self.reader.integrity_status]
        result['coverage']['rules']={'HFA-001':dict(verdict=integrity,checks=[],
            evidence=[self.reader.evidence(self.reader.run_root/'seal.json')])}
        for rule in list(self.rules)[1:]:
            checks=self.rules[rule]
            if not checks:self.check(rule,None,'REQUIRED_RULE_EVIDENCE_MISSING')
            result['coverage']['rules'][rule]=dict(verdict=self.rule_verdict(rule),checks=self.rules[rule])
        result['execution_checks']['status']=self.category(EXECUTION_RULES)
        result['stop']['status']=self.category(['HFA-009'],True)
        result['exit_cleanup']['status']=self.category(['HFA-010'])
        result['findings']=self.reader.findings+self.findings


def audit_run(reader):
    if not reader.loaded:
        raise AuditToolError('READER_NOT_LOADED')
    return BasicAudit(reader).run()
