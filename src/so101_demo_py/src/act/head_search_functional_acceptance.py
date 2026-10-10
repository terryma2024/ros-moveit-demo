"""Independent final geometry and functional verdicts; no runtime authority."""

from copy import deepcopy
import math
import re

from .head_search_campaign import _case_valid


def calculate_final_yaw(model, state, actual_yaw):
    """Solve centering on the loaded MJCF and actual full state without stepping.

    Roots are tested over one neck turn and rejected when the object is behind
    the camera. The nearest forward-facing branch preserves unwrapped yaw.
    """
    import mujoco
    import numpy as np
    from so101_demo.adapters.act.physics import model_sha256

    if (type(state) is not dict or state.get('model_sha256') != model_sha256(model)
            or type(actual_yaw) not in (int, float) or not math.isfinite(actual_yaw)):
        raise ValueError('HEAD_FUNCTIONAL_MODEL_OR_YAW_INVALID')
    for key, size in (('qpos', model.nq), ('qvel', model.nv)):
        values = state.get(key)
        if (type(values) is not list or len(values) != size
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)):
            raise ValueError('HEAD_FUNCTIONAL_STATE_INVALID')
    camera = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, 'head_camera')
    cup = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'plastic_cup')
    neck = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, 'neck_yaw_joint')
    free = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, 'cup_free_joint')
    if min(camera, cup, neck, free) < 0 or model.jnt_type[neck] != mujoco.mjtJoint.mjJNT_HINGE:
        raise ValueError('HEAD_FUNCTIONAL_COORDINATES_INVALID')
    data = mujoco.MjData(model)
    data.qpos[:] = state['qpos']
    data.qvel[:] = state['qvel']
    mujoco.mj_forward(model, data)
    minimum, maximum = np.full(3, np.inf), np.full(3, -np.inf)
    for geom in np.flatnonzero((model.geom_bodyid == cup) & (model.geom_group == 0)):
        rotation = data.geom_xmat[geom].reshape(3, 3)
        size, kind = model.geom_size[geom], model.geom_type[geom]
        if kind == mujoco.mjtGeom.mjGEOM_BOX:
            extent = np.abs(rotation) @ size
        elif kind == mujoco.mjtGeom.mjGEOM_CYLINDER:
            extent = (size[0] * np.sqrt(rotation[:, 0]**2 + rotation[:, 1]**2)
                      + size[1] * np.abs(rotation[:, 2]))
        else:
            raise ValueError('HEAD_FUNCTIONAL_CUP_GEOMETRY_UNSUPPORTED')
        minimum = np.minimum(minimum, data.geom_xpos[geom] - extent)
        maximum = np.maximum(maximum, data.geom_xpos[geom] + extent)
    center = (minimum + maximum) / 2
    if not np.isfinite(center).all():
        raise ValueError('HEAD_FUNCTIONAL_CUP_GEOMETRY_MISSING')
    neck_address = int(model.jnt_qposadr[neck])

    def residual(yaw):
        data.qpos[neck_address] = yaw
        mujoco.mj_forward(model, data)
        relative = center - data.cam_xpos[camera]
        rotation = data.cam_xmat[camera].reshape(3, 3)
        return float(rotation[:, 0] @ relative), float(-rotation[:, 2] @ relative)

    roots = []
    points = np.linspace(actual_yaw-math.pi, actual_yaw+math.pi, 65)
    for lo, hi in zip(points[:-1], points[1:]):
        left, _ = residual(lo)
        right, _ = residual(hi)
        if left * right > 0:
            continue
        for _ in range(55):
            mid = (lo+hi)/2
            middle, _ = residual(mid)
            if left * middle <= 0:
                hi = mid
            else:
                lo, left = mid, middle
        root = (lo+hi)/2
        error, forward = residual(root)
        if abs(error) <= 1e-9 and forward > 0:
            roots.append(float(root))
    if not roots:
        raise ValueError('HEAD_FUNCTIONAL_CENTER_YAW_UNREACHABLE')
    truth = min(roots, key=lambda yaw: abs(yaw-actual_yaw))
    address = int(model.jnt_qposadr[free])
    return dict(status='PASS', model_verified=True, model_sha256=state['model_sha256'],
        actual_yaw_rad=float(actual_yaw), truth_yaw_rad=truth,
        absolute_error_deg=math.degrees(abs(actual_yaw-truth)), in_front=True,
        cup_pose=state['qpos'][address:address+7], cup_center=center.tolist())


def classify_functional_case(case, attempts):
    """Preserve all raw attempts; missing proof never becomes a functional PASS."""
    if not _case_valid(case) or type(attempts) is not list:
        raise ValueError('HEAD_FUNCTIONAL_CASE_INVALID')
    result = deepcopy(case)
    result.update(attempts=deepcopy(attempts), qualified=False)

    def finish(status, reason=None):
        result.update(status=status, reasons=[] if reason is None else [reason])
        return result

    if len(attempts) < case['expected_attempt_count']:
        return finish('NOT_RUN', 'ATTEMPT_NOT_RUN')
    if len(attempts) != case['expected_attempt_count']:
        return finish('INVALID', 'EXTRA_ATTEMPT')
    for facts in attempts:
        if type(facts) is not dict:
            return finish('INVALID', 'ATTEMPT_TYPE')
        identity = facts.get('identity', {})
        if (type(identity) is not dict or any(type(identity.get(k)) is not str or not identity[k]
                for k in ('run_id', 'session_id', 'epoch'))
                or type(identity.get('generation')) is not int or identity['generation'] <= 0):
            return finish('INVALID', 'ATTEMPT_IDENTITY')
        if facts.get('stop_confirmed') is False or facts.get('owned_children_exited') is False:
            return finish('FAIL', 'UNSAFE_STOP_OR_EXIT')
        if facts.get('stop_confirmed') is not True or facts.get('owned_children_exited') is not True:
            return finish('UNKNOWN', 'STOP_OR_EXIT_UNPROVEN')
        if facts.get('scene_verified') is not True:
            return finish('UNKNOWN', 'ACTUAL_SCENE_UNPROVEN')
        expected = 0 if facts.get('original_terminal') == 'TARGET_LOCKED' else 1
        if (type(facts.get('actual_os_return_code')) is not int
                or type(facts.get('business_rc')) is not int
                or facts['actual_os_return_code'] != expected or facts['business_rc'] != expected):
            return finish('INVALID', 'TERMINAL_RC_CONFLICT')
    if len(attempts) == 2:
        first, second = attempts
        if any(first['identity'][k] == second['identity'][k]
               for k in ('run_id', 'session_id', 'epoch', 'generation')):
            return finish('INVALID', 'REACQUISITION_IDENTITY_REUSED')
        injection = first.get('injection', {})
        expected_kind = ('camera_loss' if case['condition_class'] == 'fast_interruption'
                         else 'signal_stop')
        if (type(injection) is not dict or injection.get('kind') != expected_kind or injection.get('status') != 'PASS'
                or injection.get('before_locked') is not True):
            return finish('UNKNOWN', 'INTERRUPTION_UNPROVEN')
        if first['original_terminal'] != ('FAULT' if expected_kind == 'camera_loss' else 'INTERRUPTED'):
            return finish('FAIL', 'INTERRUPTION_TERMINAL_WRONG')
    final = attempts[-1]
    condition = case['condition_class']
    terminal = final.get('original_terminal')
    if condition == 'two_cups':
        return finish('PASS' if terminal == 'TARGET_AMBIGUOUS' else 'FAIL',
                      None if terminal == 'TARGET_AMBIGUOUS' else 'UNEXPECTED_TERMINAL')
    if condition == 'no_cup':
        correct = (terminal == 'TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL'
                   and final.get('bounded_search_completed') is True)
        return finish('PASS' if correct else 'FAIL', None if correct else 'SEARCH_NOT_COMPLETED')
    if terminal != 'TARGET_LOCKED':
        return finish('FAIL', 'TARGET_NOT_LOCKED')
    image, geometry, visual = (final.get(k) for k in ('final_image', 'geometry', 'visual'))
    if type(image) is not dict or type(geometry) is not dict or type(visual) is not dict:
        return finish('UNKNOWN', 'FINAL_PROOF_MISSING')
    if (type(final.get('final_source_ns')) is not int or final['final_source_ns'] <= 0
            or type(final.get('final_payload_sha256')) is not str
            or re.fullmatch('[0-9a-f]{64}', final['final_payload_sha256']) is None
            or type(final.get('final_yaw_rad')) not in (int, float)
            or not math.isfinite(final['final_yaw_rad'])
            or type(image.get('path')) is not str or not image['path']):
        return finish('UNKNOWN', 'FINAL_PROOF_MISSING')
    if (image.get('source_ns') != final.get('final_source_ns')
            or image.get('payload_sha256') != final.get('final_payload_sha256')
            or visual.get('reviewed_payload_sha256') != image.get('payload_sha256')
            or geometry.get('actual_yaw_rad') != final.get('final_yaw_rad')):
        return finish('INVALID', 'FINAL_PROOF_IDENTITY_CONFLICT')
    if (geometry.get('status') != 'PASS' or geometry.get('model_verified') is not True
            or geometry.get('actual_pose_stable') is not True):
        return finish('UNKNOWN', 'ACTUAL_GEOMETRY_UNPROVEN')
    error = geometry.get('absolute_error_deg')
    if type(error) not in (int, float) or not math.isfinite(error) or error < 0:
        return finish('INVALID', 'ANGLE_ERROR_INVALID')
    if error > 5:
        return finish('FAIL', 'ANGLE_ERROR_ABOVE_5_DEGREES')
    if visual.get('status') not in ('PASS', 'FAIL'):
        return finish('UNKNOWN', 'VISUAL_REVIEW_PENDING')
    centered = (visual['status'] == 'PASS' and visual.get('cup_visible') is True
                and visual.get('cup_centered') is True)
    return finish('PASS' if centered else 'FAIL', None if centered else 'CUP_NOT_VISIBLY_CENTERED')
