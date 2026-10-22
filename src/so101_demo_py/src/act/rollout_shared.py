"""Pieces of the closed-loop rollout that the native tool and the parallel shards share.

They live here, and not in `so101_demo.cli.act_rollout_native`, so that the policy service (which runs in the training interpreter,
without ROS) and the shard task builder can use them without importing the native command. The native module re-exports each name.
"""

from __future__ import annotations

import time


def warm_up_policy(policy, observation: dict, *, calls: int = 3, monotonic=time.monotonic) -> list:
    """Run the model on synthetic observations of the bundle's shapes before the first episode; returns the call latencies.

    The first call of a CUDA model costs far more than the frozen `max_reply_age_s`, so without this the first request of a run
    would always be refused as stale. Nothing of the result is used; the policy is reset afterwards, so no model state reaches
    the first episode."""

    import numpy as np

    sample = {"sim_time_s": 0.0, "state": [0.0] * observation["state_dim"]}
    height, width, _channels = observation["image_shape"]
    for camera in observation["cameras"]:
        sample[camera] = np.zeros((height, width, 3), dtype=np.uint8)
    latencies = []
    for _ in range(calls):
        started = monotonic()
        policy.infer(sample)
        latencies.append(round(monotonic() - started, 6))
    policy.reset()
    return latencies
