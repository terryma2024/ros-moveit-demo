#!/usr/bin/env python3
"""Validate structured evidence from one complete Panda pick-place run."""

import argparse
import math
from pathlib import Path
import re
import sys


FORWARD_STATES = [
    'PREPARE_OPEN_GRIPPER',
    'MOVE_ABOVE_OBJECT',
    'DESCEND',
    'CLOSE_GRIPPER',
    'ATTACH_GAZEBO',
    'ATTACH_MOVEIT',
    'LIFT',
    'MOVE_ABOVE_PLACE',
    'DESCEND_TO_PLACE',
    'OPEN_GRIPPER',
    'DETACH_GAZEBO',
    'DETACH_MOVEIT',
    'SYNC_WORLD_OBJECT',
    'RETREAT',
]
MOTION_STATES = [
    'MOVE_ABOVE_OBJECT',
    'DESCEND',
    'LIFT',
    'MOVE_ABOVE_PLACE',
    'DESCEND_TO_PLACE',
    'RETREAT',
]
MOTION_TARGETS = {
    'MOVE_ABOVE_OBJECT': (0.30, 0.00, 0.987),
    'DESCEND': (0.30, 0.00, 0.870),
    'LIFT': (0.30, 0.00, 0.987),
    'MOVE_ABOVE_PLACE': (0.30, 0.20, 0.987),
    'DESCEND_TO_PLACE': (0.30, 0.20, 0.870),
    'RETREAT': (0.30, 0.20, 0.987),
}
NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'


def last_match(text, pattern):
    """Return the final regex match in text, or None."""
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    return matches[-1] if matches else None


def state_value(text, label, state, field='value'):
    """Extract the final numeric field for a state-labelled evidence line."""
    pattern = (
        rf'{re.escape(label)}[^\n]*\bstate={re.escape(state)}\b'
        rf'[^\n]*\b{re.escape(field)}=({NUMBER})'
    )
    match = last_match(text, pattern)
    return float(match.group(1)) if match else None


def quaternion_from_rpy(roll, pitch, yaw):
    """Return an x/y/z/w quaternion for fixed-axis roll, pitch, yaw."""
    cr, sr = math.cos(roll / 2.0), math.sin(roll / 2.0)
    cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
    cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def orientation_error_rpy(actual_rpy, expected_quaternion):
    """Return the shortest quaternion angular distance in radians."""
    actual = quaternion_from_rpy(*actual_rpy)
    norm = math.sqrt(sum(value * value for value in actual))
    if not math.isfinite(norm) or norm <= 1.0e-12:
        return math.inf
    dot = abs(sum(
        value * expected
        for value, expected in zip(actual, expected_quaternion)
    ) / norm)
    return 2.0 * math.acos(max(-1.0, min(1.0, dot)))


def state_pose(text, label, state):
    """Extract the final 6DoF RPY pose logged for one state."""
    match = last_match(
        text,
        rf'{re.escape(label)}[^\n]*\bstate={re.escape(state)}\b'
        rf'[^\n]*\bx=({NUMBER})[^\n]*\by=({NUMBER})[^\n]*\bz=({NUMBER})'
        rf'[^\n]*\broll=({NUMBER})[^\n]*\bpitch=({NUMBER})'
        rf'[^\n]*\byaw=({NUMBER})',
    )
    if not match:
        return None
    values = tuple(map(float, match.groups()))
    return values if all(math.isfinite(value) for value in values) else None


def validate(
    text,
    coke_tolerance,
    cross_world_tolerance,
    tcp_position_tolerance,
    tcp_orientation_tolerance,
    max_joint_jump,
):
    """Return validation errors for a normal pick-place log."""
    errors = []
    if not re.search(r'Run completed: status=DONE\b[^\n]*\bcurrent_state=DONE\b', text):
        errors.append('missing DONE terminal status')
    if 'Run failed:' in text:
        errors.append('log contains Run failed')
    if re.search(r'\bstate=RECOVER_', text):
        errors.append('normal run entered recovery')
    if re.search(r'=\s*[-+]?(?:nan|inf(?:inity)?)\b', text, re.IGNORECASE):
        errors.append('log contains a non-finite numeric value')

    observed_states = re.findall(r'STATE_TRANSITION state=([A-Z_]+)', text)
    if observed_states != FORWARD_STATES:
        errors.append(
            'forward state order mismatch: expected '
            + ','.join(FORWARD_STATES)
            + ' observed '
            + ','.join(observed_states)
        )

    evidence_labels = [
        'TARGET_TCP_POSE',
        'PLANNED_END_TCP_POSE',
        'EXECUTED_END_TCP_POSE',
        'CARTESIAN_FRACTION',
        'TRAJECTORY_POINTS',
        'MAX_JOINT_JUMP',
        'TRAJECTORY_DURATION',
    ]
    for state in MOTION_STATES:
        for label in evidence_labels:
            if not re.search(
                rf'{label}[^\n]*\bstate={re.escape(state)}\b', text
            ):
                errors.append(f'missing {label} for {state}')
        fraction = state_value(text, 'CARTESIAN_FRACTION', state)
        points = state_value(text, 'TRAJECTORY_POINTS', state)
        joint_jump = state_value(text, 'MAX_JOINT_JUMP', state)
        duration = state_value(text, 'TRAJECTORY_DURATION', state)
        numeric_evidence = {
            'CARTESIAN_FRACTION': fraction,
            'TRAJECTORY_POINTS': points,
            'MAX_JOINT_JUMP': joint_jump,
            'TRAJECTORY_DURATION': duration,
        }
        for label, value in numeric_evidence.items():
            if value is None or not math.isfinite(value):
                errors.append(f'{state} {label} is missing or non-finite')
        if fraction is not None and math.isfinite(fraction) and fraction < 0.99:
            errors.append(f'{state} Cartesian fraction {fraction} < 0.99')
        if points is not None and math.isfinite(points) and points < 1:
            errors.append(f'{state} trajectory is empty')
        if joint_jump is not None and math.isfinite(joint_jump) and joint_jump > max_joint_jump:
            errors.append(
                f'{state} maximum joint jump {joint_jump} > {max_joint_jump}'
            )
        if duration is not None and math.isfinite(duration) and duration <= 0.0:
            errors.append(f'{state} trajectory duration is not positive')

        expected_position = MOTION_TARGETS[state]
        expected_orientation = (1.0, 0.0, 0.0, 0.0)
        for label, description, position_tolerance, orientation_tolerance in (
            ('TARGET_TCP_POSE', 'target', 1.0e-4, 1.0e-4),
            (
                'PLANNED_END_TCP_POSE',
                'planned endpoint',
                tcp_position_tolerance,
                tcp_orientation_tolerance,
            ),
            (
                'EXECUTED_END_TCP_POSE',
                'executed endpoint',
                tcp_position_tolerance,
                tcp_orientation_tolerance,
            ),
        ):
            pose = state_pose(text, label, state)
            if pose is None:
                errors.append(f'{state} {label} 6DoF value is missing or non-finite')
                continue
            position_error = math.dist(pose[:3], expected_position)
            orientation_error = orientation_error_rpy(
                pose[3:], expected_orientation
            )
            if position_error > position_tolerance:
                errors.append(
                    f'{state} {description} position error '
                    f'{position_error:.6f} > {position_tolerance:.6f}'
                )
            if orientation_error > orientation_tolerance:
                errors.append(
                    f'{state} {description} orientation error '
                    f'{orientation_error:.6f} > {orientation_tolerance:.6f}'
                )

    gripper = last_match(
        text,
        rf'GRIPPER_EVIDENCE[^\n]*\bstate=RETREAT\b[^\n]*\bsample=AFTER\b'
        rf'[^\n]*FINGER1_POSITION=({NUMBER})[^\n]*FINGER2_POSITION=({NUMBER})'
        rf'[^\n]*FINGER1_VELOCITY=({NUMBER})[^\n]*FINGER2_VELOCITY=({NUMBER})',
    )
    if not gripper:
        errors.append('missing final gripper evidence')
    else:
        finger1, finger2, velocity1, velocity2 = map(float, gripper.groups())
        if min(finger1, finger2) < 0.038:
            errors.append('final gripper is not safely open')
        if max(abs(velocity1), abs(velocity2)) > 0.01:
            errors.append('final gripper is not stationary')

    attachment = last_match(
        text,
        r'ATTACHMENT_EVIDENCE[^\n]*\bstate=RETREAT\b[^\n]*'
        r'GAZEBO_ATTACHED_AFTER=(\d+)[^\n]*MOVEIT_ATTACHED_AFTER=(\d+)',
    )
    if not attachment or attachment.groups() != ('0', '0'):
        errors.append('final Gazebo/MoveIt attachment is not detached')

    membership = last_match(
        text,
        r'MOVEIT_MEMBERSHIP[^\n]*\bstate=RETREAT\b[^\n]*'
        r'COKE_IN_WORLD_AFTER=(\d+)[^\n]*TOUCH_LINK_COUNT=(\d+)',
    )
    if not membership or membership.groups() != ('1', '0'):
        errors.append('final MoveIt Coke membership is invalid')

    coke = last_match(
        text,
        rf'COKE_POSE_AFTER[^\n]*\bstate=RETREAT\b[^\n]*x=({NUMBER})'
        rf'[^\n]*y=({NUMBER})[^\n]*z=({NUMBER})[^\n]*roll=({NUMBER})'
        rf'[^\n]*pitch=({NUMBER})[^\n]*yaw=({NUMBER})',
    )
    if not coke:
        errors.append('missing final Gazebo Coke pose')
    else:
        actual = tuple(map(float, coke.groups()))
        if not all(math.isfinite(value) for value in actual):
            errors.append('final Coke pose is non-finite')
            actual = (math.inf,) * 6
        distance = math.dist(actual[:3], (0.30, 0.20, 0.836))
        if distance > coke_tolerance:
            errors.append(
                f'final Coke position error {distance:.6f} > {coke_tolerance:.6f}'
            )
        orientation_error = orientation_error_rpy(
            actual[3:], (0.0, 0.0, 0.0, 1.0)
        )
        if orientation_error > 0.0872665:
            errors.append(
                f'final Coke orientation error {orientation_error:.6f} > 0.087267'
            )

    cross_world = last_match(
        text,
        rf'CROSS_WORLD_COKE_POSE_ERROR[^\n]*\bstate=RETREAT\b'
        rf'[^\n]*position=({NUMBER})[^\n]*orientation_rad=({NUMBER})',
    )
    if not cross_world:
        errors.append('missing cross-world Coke pose evidence')
    else:
        position_error, orientation_error = map(float, cross_world.groups())
        if position_error > cross_world_tolerance:
            errors.append('cross-world Coke position mismatch')
        if orientation_error > 0.0872665:
            errors.append('cross-world Coke orientation mismatch')
    return errors


def main():
    """Parse arguments and validate one retained log."""
    parser = argparse.ArgumentParser()
    parser.add_argument('log', type=Path)
    parser.add_argument('--coke-tolerance', type=float, default=0.01)
    parser.add_argument('--cross-world-tolerance', type=float, default=0.01)
    parser.add_argument('--tcp-position-tolerance', type=float, default=0.01)
    parser.add_argument('--tcp-orientation-tolerance', type=float, default=0.035)
    parser.add_argument('--max-joint-jump', type=float, default=0.2)
    args = parser.parse_args()
    text = args.log.read_text(encoding='utf-8')
    errors = validate(
        text,
        args.coke_tolerance,
        args.cross_world_tolerance,
        args.tcp_position_tolerance,
        args.tcp_orientation_tolerance,
        args.max_joint_jump,
    )
    if errors:
        for error in errors:
            print(f'FAIL: {error}', file=sys.stderr)
        return 1
    print(f'PASS: complete pick-place evidence in {args.log}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
