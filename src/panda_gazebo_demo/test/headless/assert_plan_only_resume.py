#!/usr/bin/env python3
"""Validate one resumed plan-only result and immutable checkpoint evidence."""

import json
import math
from pathlib import Path
import re
import sys


NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
TCP_POSITION_TOLERANCE = 0.020
TCP_ORIENTATION_TOLERANCE_RAD = 0.0872665
EVIDENCE_LABELS = (
    'TARGET_TCP_POSE',
    'START_TCP_POSE',
    'PLANNED_END_TCP_POSE',
    'CARTESIAN_FRACTION',
    'TRAJECTORY_POINTS',
    'MAX_JOINT_JUMP',
    'TRAJECTORY_DURATION',
)


def fail(message: str) -> None:
    print(f'FAIL: {message}', file=sys.stderr)
    raise SystemExit(1)


if len(sys.argv) != 6:
    fail(
        'expected LOG EXPECTED_STATE EXPECTED_PHASE '
        'CHECKPOINT_BEFORE CHECKPOINT_AFTER'
    )

log_path = Path(sys.argv[1])
expected_state = sys.argv[2]
expected_phase = sys.argv[3]
before_path = Path(sys.argv[4])
after_path = Path(sys.argv[5])
if expected_phase != 'FORWARD':
    fail(f'unsupported checkpoint phase {expected_phase}')
if expected_state.startswith('RECOVER_'):
    fail('recovery states are not valid plan-only targets')

text = log_path.read_text(encoding='utf-8')
before_bytes = before_path.read_bytes()
after_bytes = after_path.read_bytes()
if before_bytes != after_bytes:
    fail('checkpoint bytes changed during plan-only resume')
checkpoint = json.loads(before_bytes)
if checkpoint.get('schema_version') != 3:
    fail('checkpoint schema_version is not 3')
if checkpoint.get('source_mode') != 'execute':
    fail('plan-only target-entry checkpoint source_mode is not execute')
if checkpoint.get('phase') != expected_phase:
    fail(
        f'checkpoint phase is {checkpoint.get("phase")}, '
        f'expected {expected_phase}'
    )
sequence = checkpoint.get('sequence')
if not isinstance(sequence, int) or sequence < 1:
    fail('checkpoint sequence is not a positive integer')
next_state = checkpoint.get('next_state')
if not isinstance(next_state, str) or not next_state:
    fail('checkpoint next_state is missing')
if expected_phase == 'FORWARD' and next_state != expected_state:
    fail(
        f'forward checkpoint selects {next_state}, expected {expected_state}'
    )

load_pattern = (
    rf'CHECKPOINT_PHASE={expected_phase}\s+'
    rf'CHECKPOINT_SEQUENCE={sequence}\s+NEXT_STATE={re.escape(next_state)}\s+'
    r'resume_load=1'
)
if not re.search(load_pattern, text):
    fail('log is missing the exact checkpoint resume-load evidence')
completion_pattern = (
    r'Run completed: status=PLAN_ONLY_COMPLETE\s+'
    rf'current_state={re.escape(expected_state)}\b'
)
if not re.search(completion_pattern, text):
    fail(f'plan-only result did not select {expected_state}')
if 'Run failed:' in text:
    fail('plan-only log contains Run failed')
if re.search(r'=\s*[-+]?(?:nan|inf(?:inity)?)\b', text, re.IGNORECASE):
    fail('plan-only log contains a non-finite numeric value')
if re.search(
    rf'(?:EXECUTED_END_TCP_POSE|STATE_TRANSITION|execute:|transition-validate:)[^\n]*'
    rf'\b{re.escape(expected_state)}\b',
    text,
):
    fail('plan-only log contains target execute/postcondition evidence')
checkpoint_lines = re.findall(r'^.*CHECKPOINT_PHASE=.*$', text, re.MULTILINE)
if any('resume_load=1' not in line for line in checkpoint_lines):
    fail('plan-only log contains a checkpoint commit')
if 'RECOVER_' in text or 'CHECKPOINT_PHASE=RECOVERY' in text:
    fail('forward plan-only resume entered recovery')

named_target = re.search(
    rf'NAMED_JOINT_TARGET[^\n]*\bstate={re.escape(expected_state)}\b'
    r'[^\n]*\btarget=(\S+)',
    text,
)
if named_target:
    for label in ('START_TCP_POSE', 'PLANNED_END_TCP_POSE'):
        pose = re.search(
            rf'{label}[^\n]*\bstate={re.escape(expected_state)}\b'
            rf'[^\n]*\bx=({NUMBER})[^\n]*\by=({NUMBER})'
            rf'[^\n]*\bz=({NUMBER})[^\n]*\broll=({NUMBER})'
            rf'[^\n]*\bpitch=({NUMBER})[^\n]*\byaw=({NUMBER})',
            text,
        )
        if not pose or not all(
            math.isfinite(float(value)) for value in pose.groups()
        ):
            fail(f'{label} does not contain a finite 6DoF pose for {expected_state}')
    points = re.search(
        rf'TRAJECTORY_POINTS[^\n]*\bstate={re.escape(expected_state)}\b'
        rf'[^\n]*\bvalue=({NUMBER})',
        text,
    )
    if not points or float(points.group(1)) < 1.0:
        fail(f'planned named-target trajectory is empty for {expected_state}')
    print(
        f'PASS: {expected_phase} named-target plan-only resume validated '
        f'for {expected_state}; checkpoint unchanged'
    )
    raise SystemExit(0)

for label in EVIDENCE_LABELS:
    if not re.search(
        rf'{label}[^\n]*\bstate={re.escape(expected_state)}\b', text
    ):
        fail(f'log is missing {label} for {expected_state}')

poses = {}
for label in ('TARGET_TCP_POSE', 'PLANNED_END_TCP_POSE'):
    pose = re.search(
        rf'{label}[^\n]*\bstate={re.escape(expected_state)}\b'
        rf'[^\n]*\bx=({NUMBER})[^\n]*\by=({NUMBER})'
        rf'[^\n]*\bz=({NUMBER})[^\n]*\broll=({NUMBER})'
        rf'[^\n]*\bpitch=({NUMBER})[^\n]*\byaw=({NUMBER})',
        text,
    )
    if not pose or not all(math.isfinite(float(value)) for value in pose.groups()):
        fail(f'{label} does not contain a finite 6DoF pose for {expected_state}')
    poses[label] = tuple(float(value) for value in pose.groups())


def quaternion_from_rpy(roll: float, pitch: float, yaw: float) -> tuple:
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


target_pose = poses['TARGET_TCP_POSE']
planned_pose = poses['PLANNED_END_TCP_POSE']
position_error = math.sqrt(
    sum((target_pose[index] - planned_pose[index]) ** 2 for index in range(3))
)
target_quaternion = quaternion_from_rpy(*target_pose[3:])
planned_quaternion = quaternion_from_rpy(*planned_pose[3:])
quaternion_dot = abs(
    sum(lhs * rhs for lhs, rhs in zip(target_quaternion, planned_quaternion))
)
orientation_error = 2.0 * math.acos(min(1.0, quaternion_dot))
if position_error > TCP_POSITION_TOLERANCE:
    fail(
        f'planned endpoint position error {position_error} exceeds '
        f'{TCP_POSITION_TOLERANCE}'
    )
if orientation_error > TCP_ORIENTATION_TOLERANCE_RAD:
    fail(
        f'planned endpoint orientation error {orientation_error} exceeds '
        f'{TCP_ORIENTATION_TOLERANCE_RAD}'
    )


def evidence_value(label: str) -> float:
    match = re.search(
        rf'{label}[^\n]*\bstate={re.escape(expected_state)}\b'
        rf'[^\n]*\bvalue=({NUMBER})',
        text,
    )
    if not match:
        fail(f'{label} numeric value is missing for {expected_state}')
    value = float(match.group(1))
    if not math.isfinite(value):
        fail(f'{label} is non-finite for {expected_state}')
    return value


if evidence_value('CARTESIAN_FRACTION') < 0.99:
    fail('Cartesian fraction is below 0.99')
if evidence_value('TRAJECTORY_POINTS') < 1.0:
    fail('planned trajectory is empty')
joint_jump = evidence_value('MAX_JOINT_JUMP')
if joint_jump < 0.0 or joint_jump > 0.2:
    fail(f'maximum joint jump {joint_jump} is outside [0.0, 0.2]')
if evidence_value('TRAJECTORY_DURATION') <= 0.0:
    fail('planned trajectory duration is not positive')

print(
    f'PASS: {expected_phase} plan-only resume validated for '
    f'{expected_state}; checkpoint unchanged'
)
