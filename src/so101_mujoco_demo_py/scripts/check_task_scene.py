#!/usr/bin/env python3
"""Step the independent task scene headlessly and emit one JSON report."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
from pathlib import Path

import yaml

LIBRARY = "/opt/ros/jazzy/opt/mujoco_vendor/lib/libmujoco.so"
STATE_TIME_QPOS_QVEL = (1 << 0) | (1 << 1) | (1 << 2)
ROBOT_NQ = 6
CUP_NQ = 7
CUP_NV = 6


def state(library: ctypes.CDLL, model: int, data: int) -> list[float]:
    size = library.mj_stateSize(model, STATE_TIME_QPOS_QVEL)
    values = (ctypes.c_double * size)()
    library.mj_getState(model, data, values, STATE_TIME_QPOS_QVEL)
    return list(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    scene = args.config.parent.parent / config["scene"]

    library = ctypes.CDLL(LIBRARY)
    library.mj_loadXML.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    library.mj_loadXML.restype = ctypes.c_void_p
    library.mj_makeData.argtypes = [ctypes.c_void_p]
    library.mj_makeData.restype = ctypes.c_void_p
    library.mj_stateSize.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    library.mj_stateSize.restype = ctypes.c_int
    library.mj_getState.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_uint,
    ]
    library.mj_step.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    library.mj_deleteData.argtypes = [ctypes.c_void_p]
    library.mj_deleteModel.argtypes = [ctypes.c_void_p]

    error = ctypes.create_string_buffer(2048)
    model = library.mj_loadXML(str(scene).encode(), None, error, len(error))
    if not model:
        raise SystemExit(error.value.decode(errors="replace"))
    data = library.mj_makeData(model)
    if not data:
        library.mj_deleteModel(model)
        raise SystemExit("mj_makeData failed")

    timestep = float(config["initial_inputs"]["timestep_s"])
    steps = math.ceil(float(config["simulation_seconds"]) / timestep)
    settle_step = math.ceil(2.0 / timestep)
    sample_start_step = math.ceil(8.0 / timestep)
    sample_stride = max(1, math.ceil(0.01 / timestep))
    settled: list[float] | None = None
    final_window_positions: list[list[float]] = []
    try:
        for step_index in range(steps):
            library.mj_step(model, data)
            if step_index + 1 == settle_step:
                settled = state(library, model, data)
            if step_index + 1 >= sample_start_step and (step_index + 1) % sample_stride == 0:
                sampled = state(library, model, data)
                final_window_positions.append(sampled[1 + ROBOT_NQ : 1 + ROBOT_NQ + 3])
        final = state(library, model, data)
    finally:
        library.mj_deleteData(data)
        library.mj_deleteModel(model)

    assert settled is not None
    nq = ROBOT_NQ + CUP_NQ
    cup_position_start = 1 + ROBOT_NQ
    cup_velocity_start = 1 + nq + (nq - CUP_NQ)
    drift = math.dist(
        settled[cup_position_start : cup_position_start + 3],
        final[cup_position_start : cup_position_start + 3],
    )
    speed = math.sqrt(
        sum(value * value for value in final[cup_velocity_start : cup_velocity_start + 3])
    )
    settled_position = settled[cup_position_start : cup_position_start + 3]
    final_position = final[cup_position_start : cup_position_start + 3]
    cup_velocity = final[cup_velocity_start : cup_velocity_start + CUP_NV]
    coordinate_ranges = [
        max(position[axis] for position in final_window_positions)
        - min(position[axis] for position in final_window_positions)
        for axis in range(3)
    ]
    final_window_envelope = math.sqrt(sum(value * value for value in coordinate_ranges))
    final_window_net_speed = math.dist(final_window_positions[0], final_window_positions[-1]) / 2.0
    report = {
        "cup_final_position_m": final_position,
        "cup_final_velocity": cup_velocity,
        "cup_horizontal_translation_after_settle_m": math.dist(
            settled_position[:2], final_position[:2]
        ),
        "cup_quaternion_norm": math.sqrt(
            sum(value * value for value in final[cup_position_start + 3 : cup_position_start + 7])
        ),
        "cup_settled_position_m": settled_position,
        "cup_speed_m_per_s": speed,
        "cup_translation_after_settle_m": drift,
        "finite_state": all(math.isfinite(value) for value in final),
        "final_two_second_net_speed_m_per_s": final_window_net_speed,
        "final_two_second_sample_count": len(final_window_positions),
        "final_two_second_translation_envelope_m": final_window_envelope,
        "simulation_seconds": final[0],
        "state_size": len(final),
        "table_dofs": 0,
    }
    print(json.dumps(report, sort_keys=True))
    stationary = (
        drift <= 1.0e-5 and final_window_envelope <= 1.0e-5 and final_window_net_speed <= 1.0e-5
    )
    return 0 if report["finite_state"] and stationary else 1


if __name__ == "__main__":
    raise SystemExit(main())
