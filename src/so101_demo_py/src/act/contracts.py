"""Closed ACT schemas. Simulation audit fields never enter observations."""

import math
import re


class ContractError(ValueError):
    """An input or sealed artifact violates the data contract."""


SPLITS = frozenset({"train", "validation", "offline_test", "rollout_validation",
                    "rollout_test", "qualification", "comparison"})


def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ContractError("FIELDS_INVALID")


def finite(value, *, nonnegative=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (nonnegative and value < 0)):
        raise ContractError("NUMBER_INVALID")
    return float(value)


def identifier(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ContractError("ID_INVALID")
    return value


def integer(value, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ContractError("INTEGER_INVALID")
    return value


def vector(values, size):
    if not isinstance(values, (tuple, list)) or len(values) != size:
        raise ContractError("VECTOR_INVALID")
    return tuple(finite(v) for v in values)


def sha256(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ContractError("SHA256_INVALID")
    return value


def validate_action(values):
    return vector(values, 6)


def validate_observation(value):
    fields(value, ("session_id", "attempt_id", "sim_time_s", "head", "wrist", "state"))
    identifier(value["session_id"])
    identifier(value["attempt_id"])
    finite(value["sim_time_s"], nonnegative=True)
    state = vector(value["state"], 8)
    if not math.isclose(state[6] ** 2 + state[7] ** 2, 1., abs_tol=1e-6):
        raise ContractError("NECK_ENCODING_INVALID")
    # Array inspection is local; this module has no robotics or training imports.
    import numpy as np

    for key in ("head", "wrist"):
        image = value[key]
        if (not isinstance(image, np.ndarray) or image.dtype != np.uint8
                or image.shape != (480, 640, 3)):
            raise ContractError("RGB_INVALID")
    return dict(value, state=state)


def validate_action_prefix(value):
    fields(value, ("session_id", "attempt_id", "sequence", "observation_time_s",
                   "target_times_s", "positions"))
    identifier(value["session_id"])
    identifier(value["attempt_id"])
    integer(value["sequence"])
    origin = finite(value["observation_time_s"], nonnegative=True)
    times, positions = value["target_times_s"], value["positions"]
    if (not isinstance(times, (tuple, list)) or not times
            or not isinstance(positions, (tuple, list)) or len(times) != len(positions)):
        raise ContractError("PREFIX_INVALID")
    times = tuple(finite(t, nonnegative=True) for t in times)
    for i, t in enumerate(times):
        if not math.isclose(t, origin + .1 * (i + 1), rel_tol=0., abs_tol=1e-6):
            raise ContractError("PREFIX_TIME_GRID_INVALID")
    return dict(value, target_times_s=times,
                positions=tuple(validate_action(row) for row in positions))


def validate_search_result(value):
    fields(value, ("found", "status", "bearing_rad", "frame_id", "ray_origin_frame_id",
                   "neck_yaw_rad", "confidence", "timestamp", "attempt_id"))
    if type(value["found"]) is not bool:
        raise ContractError("SEARCH_INVALID")
    for key in ("status", "frame_id", "ray_origin_frame_id", "attempt_id"):
        identifier(value[key])
    finite(value["timestamp"], nonnegative=True)
    if value["neck_yaw_rad"] is not None:
        finite(value["neck_yaw_rad"])
    if value["found"]:
        if (value["status"] != "TARGET_LOCKED" or value["neck_yaw_rad"] is None
                or not -math.pi <= finite(value["bearing_rad"]) < math.pi
                or not 0. <= finite(value["confidence"]) <= 1.):
            raise ContractError("SEARCH_INVALID")
    elif (value["status"] == "TARGET_LOCKED" or value["bearing_rad"] is not None
          or value["confidence"] is not None):
        raise ContractError("SEARCH_INVALID")
    return dict(value)


def validate_scenario(value):
    fields(value, ("scene_id", "split", "xy", "arm_q", "search_start_rad", "seed",
                   "config_sha256"))
    identifier(value["scene_id"])
    if value["split"] not in SPLITS:
        raise ContractError("SPLIT_INVALID")
    integer(value["seed"])
    sha256(value["config_sha256"])
    return dict(value, xy=vector(value["xy"], 2), arm_q=validate_action(value["arm_q"]),
                search_start_rad=finite(value["search_start_rad"]))


def validate_collection_result(value):
    fields(value, ("scene_id", "split", "status", "business_failure", "infra_attempts",
                   "episode_root", "episode_sha256", "worker_id", "pool_generation",
                   "worker_count"))
    for key in ("scene_id", "episode_root", "worker_id"):
        identifier(value[key])
    if value["split"] not in {"train", "validation", "offline_test", "qualification"}:
        raise ContractError("SPLIT_INVALID")
    sha256(value["episode_sha256"])
    integer(value["infra_attempts"])
    integer(value["pool_generation"])
    integer(value["worker_count"], minimum=1)
    if value["status"] == "PASSED":
        if value["business_failure"] is not None:
            raise ContractError("RESULT_INVALID")
    elif value["status"] == "FAILED":
        identifier(value["business_failure"])
    else:
        raise ContractError("RESULT_INVALID")
    return dict(value)


def validate_run_result(value):
    fields(value, ("scene_id", "split", "search_locked", "done", "interventions",
                   "failure", "elapsed_wall_s", "elapsed_sim_s", "checkpoint_sha256",
                   "config_sha256"))
    identifier(value["scene_id"])
    if value["split"] not in SPLITS:
        raise ContractError("SPLIT_INVALID")
    if type(value["done"]) is not bool or type(value["search_locked"]) is not bool:
        raise ContractError("RESULT_INVALID")
    integer(value["interventions"])
    wall = finite(value["elapsed_wall_s"], nonnegative=True)
    finite(value["elapsed_sim_s"], nonnegative=True)
    sha256(value["checkpoint_sha256"])
    sha256(value["config_sha256"])
    if value["done"]:
        if not value["search_locked"] or wall >= 120. or value["failure"] is not None:
            raise ContractError("RESULT_INVALID")
    elif value["failure"] is not None:
        identifier(value["failure"])
    return dict(value)
