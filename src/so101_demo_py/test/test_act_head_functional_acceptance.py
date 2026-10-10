"""Final geometry and reviewed original image determine functional lock acceptance."""

import copy
import math

import mujoco
import pytest

from test_act_head_search_campaign_scene import _baseline, _case


def scene_state(tmp_path):
    from so101_demo.adapters.act.physics import model_sha256
    baseline = _baseline(tmp_path)
    model = mujoco.MjModel.from_xml_path(baseline['refs']['scene']['path'])
    data = mujoco.MjData(model)
    return model, dict(model_sha256=model_sha256(model), qpos=data.qpos.tolist(),
                       qvel=data.qvel.tolist())


@pytest.mark.parametrize('turns', [-2, 0, 3])
def test_geometric_yaw_uses_camera_and_actual_cup_pose_on_nearest_branch(tmp_path, turns):
    from so101_demo.act.head_search_functional_acceptance import calculate_final_yaw
    model, state = scene_state(tmp_path)
    actual = .23 + turns * 2 * math.pi
    result = calculate_final_yaw(model, state, actual)
    assert result['truth_yaw_rad'] == pytest.approx(.23109066719450466 + turns * 2 * math.pi)
    # An independent analytic value for this fixed, upright scene.
    assert result['absolute_error_deg'] == pytest.approx(math.degrees(math.atan2(.08, .34)-.23))
    assert result['cup_pose'][:3] == [.02, -.28, .165]
    assert result['in_front'] is True


@pytest.mark.parametrize('damage', ['identity', 'short_state', 'nan'])
def test_geometry_refuses_unproven_actual_state(tmp_path, damage):
    from so101_demo.act.head_search_functional_acceptance import calculate_final_yaw
    model, state = scene_state(tmp_path)
    if damage == 'identity':
        state['model_sha256'] = 'a' * 64
    elif damage == 'short_state':
        state['qpos'].pop()
    else:
        state['qpos'][0] = float('nan')
    with pytest.raises(ValueError):
        calculate_final_yaw(model, state, .23)


def locked_facts():
    return dict(identity=dict(run_id='r', session_id='s', epoch='e', generation=1),
        actual_os_return_code=0, business_rc=0, original_terminal='TARGET_LOCKED',
        stop_confirmed=True, owned_children_exited=True, scene_verified=True,
        final_yaw_rad=.23, final_source_ns=100, final_payload_sha256='b' * 64,
        final_image=dict(source_ns=100, payload_sha256='b' * 64, path='/e/final.png'),
        geometry=dict(status='PASS', actual_yaw_rad=.23, absolute_error_deg=5.,
                      actual_pose_stable=True, model_verified=True),
        visual=dict(status='PASS', reviewed_payload_sha256='b' * 64, cup_visible=True,
                    cup_centered=True))


@pytest.mark.parametrize('damage,expected', [
    ('none', 'PASS'), ('angle_above', 'FAIL'), ('no_visual', 'UNKNOWN'),
    ('wrong_image', 'INVALID'), ('wrong_review', 'INVALID'), ('moving_cup', 'UNKNOWN'),
    ('uncentered', 'FAIL'), ('stop_unknown', 'UNKNOWN'), ('exit_failed', 'FAIL')])
def test_functional_lock_requires_reviewed_final_original_and_five_degree_bound(damage, expected):
    from so101_demo.act.head_search_functional_acceptance import classify_functional_case
    facts = locked_facts()
    if damage == 'angle_above': facts['geometry']['absolute_error_deg'] = 5.0001
    elif damage == 'no_visual': facts.pop('visual')
    elif damage == 'wrong_image': facts['final_image']['source_ns'] = 101
    elif damage == 'wrong_review': facts['visual']['reviewed_payload_sha256'] = 'c' * 64
    elif damage == 'moving_cup': facts['geometry']['actual_pose_stable'] = False
    elif damage == 'uncentered': facts['visual']['cup_centered'] = False
    elif damage == 'stop_unknown': facts.pop('stop_confirmed')
    elif damage == 'exit_failed': facts['owned_children_exited'] = False
    before = copy.deepcopy(facts)
    assert classify_functional_case(_case(0), [facts])['status'] == expected
    assert facts == before


def test_no_cup_requires_actual_bounded_search_completion():
    from so101_demo.act.head_search_functional_acceptance import classify_functional_case
    facts = locked_facts()
    facts.update(actual_os_return_code=1, business_rc=1,
                 original_terminal='TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL',
                 bounded_search_completed=True)
    assert classify_functional_case(_case(5), [facts])['status'] == 'PASS'
    facts['original_terminal'] = 'SEARCH_TIMEOUT'
    assert classify_functional_case(_case(5), [facts])['status'] == 'FAIL'


@pytest.mark.parametrize('damage', ['identity_type', 'missing_source', 'missing_hash'])
def test_malformed_final_proof_cannot_pass(damage):
    from so101_demo.act.head_search_functional_acceptance import classify_functional_case
    facts = locked_facts()
    if damage == 'identity_type':
        facts['identity'] = None
    elif damage == 'missing_source':
        facts.pop('final_source_ns')
        facts['final_image'].pop('source_ns')
    else:
        facts.pop('final_payload_sha256')
        facts['final_image'].pop('payload_sha256')
        facts['visual'].pop('reviewed_payload_sha256')
    assert classify_functional_case(_case(0), [facts])['status'] in ('INVALID', 'UNKNOWN')


def test_functional_fixture_keeps_reset_and_disables_native_paired_truth(tmp_path):
    import yaml
    from pathlib import Path
    from so101_demo.act.head_search_campaign_scene import prepare_case_fixture
    baseline = _baseline(tmp_path)
    prepared = prepare_case_fixture(_case(0), baseline, tmp_path/'functional',
                                    paired_truth_enabled=False)
    plugin = yaml.safe_load(Path(prepared['refs']['mujoco_plugin']['path']).read_text())
    camera = plugin['/**']['ros__parameters']['mujoco_plugins']['mujoco_camera_plugin']['head_camera']
    assert camera.get('truth_enabled', False) is False
    assert prepared['fixture']['reset_free_bodies']['plastic_cup']['xyz'] == [.02, -.28, .165]


def test_explicit_disabled_campaign_collector_creates_no_ros_or_writer_resources():
    from types import SimpleNamespace
    from so101_demo.adapters.act.head_campaign_truth_collector import create_campaign_truth_collector
    inputs = SimpleNamespace(refs={'scenario_fixture': {}},
                             document={'campaign_truth_enabled': False})
    assert create_campaign_truth_collector(node=None, inputs=inputs, writer=None) is None


@pytest.mark.parametrize('index', [0, 6, 7])
def test_disabled_truth_omits_unused_ros_parameters_including_untyped_empty_arrays(tmp_path, index):
    import yaml
    from pathlib import Path
    from so101_demo.act.head_search_campaign_scene import prepare_case_fixture
    prepared = prepare_case_fixture(_case(index), _baseline(tmp_path), tmp_path/'fixture',
                                    paired_truth_enabled=False)
    camera = yaml.safe_load(Path(prepared['refs']['mujoco_plugin']['path']).read_text())[
        '/**']['ros__parameters']['mujoco_plugins']['mujoco_camera_plugin']['head_camera']
    assert camera['truth_enabled'] is False
    assert all(not key.startswith('truth_') or key == 'truth_enabled' for key in camera)
