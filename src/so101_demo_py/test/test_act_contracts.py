"""Strict policy input boundaries and immutable attempt budget."""

import subprocess
import sys

import numpy as np
import pytest

from so101_demo.act.contracts import (
    ContractError, validate_action, validate_action_prefix, validate_observation,
    validate_scenario, validate_search_result, validate_collection_result,
    validate_run_result,
)
from so101_demo.act.deadline import Deadline


def observation():
    return dict(session_id="s", attempt_id="a", sim_time_s=1.,
                head=np.zeros((480, 640, 3), dtype=np.uint8),
                wrist=np.zeros((480, 640, 3), dtype=np.uint8),
                state=(0.,) * 6 + (0., 1.))


@pytest.mark.parametrize("values", [(0.,)*5, (0.,)*7, (0.,)*5+(True,),
                                     (0.,)*5+(float("nan"),),
                                     (0.,)*5+(float("inf"),)])
def test_action_rejects_invalid(values):
    with pytest.raises(ContractError):
        validate_action(values)


def test_observation_only_accepts_rgb_state8():
    sample = observation()
    assert validate_observation(sample)["state"] == sample["state"]
    for key in ("truth", "depth", "task_camera", "cup_pose"):
        with pytest.raises(ContractError):
            validate_observation(dict(sample, **{key: 0}))
    for image in (np.zeros((640, 480, 3), dtype=np.uint8),
                  np.zeros((480, 640, 3), dtype=float),
                  np.zeros((480, 640, 4), dtype=np.uint8)):
        with pytest.raises(ContractError):
            validate_observation(dict(sample, head=image))
    for state in ((0.,)*7, (0.,)*9, (0.,)*7+(True,)):
        with pytest.raises(ContractError):
            validate_observation(dict(sample, state=state))
    with pytest.raises(ContractError):
        validate_observation(dict(sample, session_id=""))


def test_prefix_preserves_causal_grid():
    prefix = dict(session_id="s", attempt_id="a", sequence=0,
                  observation_time_s=1., target_times_s=(1.1, 1.2),
                  positions=((0.,)*6, (0.,)*6))
    assert validate_action_prefix(prefix)["target_times_s"] == (1.1, 1.2)
    for changes in (dict(target_times_s=(1.2, 1.3)),
                    dict(target_times_s=(1.1, 1.3)), dict(sequence=True),
                    dict(positions=((0.,)*6,)), dict(unknown=1)):
        with pytest.raises(ContractError):
            validate_action_prefix(dict(prefix, **changes))


def test_fixed_deadline_rejects_bad_and_backwards_time():
    budget = Deadline(started_wall_s=10.)
    assert not budget.expired(129.999)
    assert budget.expired(130.)
    assert budget.expired(131.)
    with pytest.raises(ContractError):
        budget.expired(129.)
    for value in (True, float("nan"), float("inf"), -1.):
        with pytest.raises(ContractError):
            Deadline(value)


def test_pure_modules_do_not_import_robotics_or_training():
    code = ("import sys; import so101_demo.act.contracts, so101_demo.act.deadline; "
            "assert not any(x in sys.modules for x in ('rclpy','torch','mujoco'))")
    subprocess.run([sys.executable, "-c", code], check=True)


def test_search_and_scenario_identity_boundaries():
    result = dict(found=False, status="TARGET_NOT_FOUND", bearing_rad=None,
                  frame_id="base", ray_origin_frame_id="head_optical",
                  neck_yaw_rad=0., confidence=None, timestamp=1., attempt_id="a")
    validate_search_result(result)
    with pytest.raises(ContractError):
        validate_search_result(dict(result, bearing_rad=1.))
    scenario = dict(scene_id="scene", split="train", xy=(.1,.2), arm_q=(0.,)*6,
                    search_start_rad=0., seed=1, config_sha256="a"*64)
    validate_scenario(scenario)
    with pytest.raises(ContractError):
        validate_scenario(dict(scenario, seed=True))


def test_result_schemas_reject_extra_fields_and_inconsistent_outcomes():
    result = dict(scene_id="x", split="train", status="PASSED", business_failure=None,
                  infra_attempts=0, episode_root="/tmp/x", episode_sha256="a"*64,
                  worker_id="w1", pool_generation=0, worker_count=1)
    validate_collection_result(result)
    for changes in (dict(status="FAILED"), dict(worker_count=True), dict(truth=1)):
        with pytest.raises(ContractError):
            validate_collection_result(dict(result, **changes))
    run = dict(scene_id="x", split="train", search_locked=True, done=True,
               interventions=0, failure=None, elapsed_wall_s=119., elapsed_sim_s=50.,
               checkpoint_sha256="a"*64, config_sha256="b"*64)
    validate_run_result(run)
    for changes in (dict(done=1), dict(elapsed_wall_s=120.), dict(failure="TIMEOUT")):
        with pytest.raises(ContractError):
            validate_run_result(dict(run, **changes))
