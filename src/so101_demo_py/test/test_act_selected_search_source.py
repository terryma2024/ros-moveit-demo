"""The selected SEARCH sample has one stable physical and image identity."""

import copy

import pytest

from test_act_task8_search_port import bind, fixture, observation, request


def test_freeze_uses_original_receipts_and_changes_with_image_or_state():
    from so101_demo.adapters.act.selected_search_source import freeze_selected_search_source

    selected = observation()
    frozen = freeze_selected_search_source(selected, max_skew_s=.02)
    raw = selected.physical_readback
    assert frozen['session_id'] == raw['world'].simulation_session_id
    assert frozen['reset_epoch'] == raw['world'].reset_epoch
    assert frozen['physics_step'] == raw['world'].simulation_step
    assert frozen['simulation_time_s'] == raw['world'].simulation_time_s
    assert frozen['source_received_wall_s'] == raw['source_received_wall_s']
    assert frozen['phase'] == 'SEARCH'
    assert len(frozen['observation_sha256']) == 64

    changed = copy.deepcopy(selected)
    changed.physical_readback['observation']['head'][0, 0, 0] = 1
    assert freeze_selected_search_source(
        changed, max_skew_s=.02)['observation_sha256'] != frozen['observation_sha256']
    changed = copy.deepcopy(selected)
    changed.physical_readback['scene']['qpos'] = (1.0,)
    assert freeze_selected_search_source(
        changed, max_skew_s=.02)['observation_sha256'] != frozen['observation_sha256']
    changed = copy.deepcopy(selected)
    changed.physical_readback['observation']['wrist'][0, 0, 0] = 1
    assert freeze_selected_search_source(
        changed, max_skew_s=.02)['observation_sha256'] != frozen['observation_sha256']
    changed = copy.deepcopy(selected)
    changed.physical_readback['scene']['qvel'] = (1.0,)
    assert freeze_selected_search_source(
        changed, max_skew_s=.02)['observation_sha256'] != frozen['observation_sha256']


@pytest.mark.parametrize('changed', ('step', 'epoch', 'future_stamp', 'planning'))
def test_freeze_refuses_mismatched_physical_source(changed):
    from so101_demo.adapters.act.selected_search_source import freeze_selected_search_source

    selected = observation()
    if changed == 'step':
        selected.physical_readback['scene']['simulation_step'] += 1
    elif changed == 'epoch':
        selected.physical_readback['contact']['reset_epoch'] += 1
    elif changed == 'planning':
        selected.planning_scene.evidence['mismatches'].append('cup')
    else:
        selected.physical_readback['source_stamps_s']['head'] += .01
    with pytest.raises(ValueError, match='SELECTED_SEARCH_SOURCE_INVALID'):
        freeze_selected_search_source(selected, max_skew_s=.02)


def test_search_port_exposes_only_validated_selected_source():
    port, _ = fixture()
    with pytest.raises(RuntimeError, match='PICK_PLACE_SEARCH_OBSERVATION_UNAVAILABLE'):
        port.selected_prefix_source(max_skew_s=.02)
    bind(port)
    scope = request()
    port.begin(scope)
    port.run_phase('SEARCH', scope)
    frozen = port.selected_prefix_source(max_skew_s=.02)
    assert frozen['physics_step'] == 2
    assert frozen['source_received_wall_s']['world'] == 10.0
