"""A delayed submission keeps its policy source and full path time axis."""

import pytest


def test_delayed_goals_keep_policy_source_and_bridge_interval():
    from so101_demo.act.path_proof import RelativePathRequest

    prefix = {
        "session_id": "session", "attempt_id": "attempt", "sequence": 0,
        "observation_time_s": 4.0, "first_target_delay_s": .1,
        "target_interval_s": .002, "target_times_s": (4.102, 4.104),
        "positions": ((.001,) * 6, (.002,) * 6),
    }
    request = RelativePathRequest.from_prefix(
        prefix, bridge_time_s=4.0, start_time_s=4.05,
        policy_received_wall_s=10.0,
    )

    goal = request.materialize(start_time_s=6.05, bridge_time_s=6.0)
    assert goal["policy_observation_time_s"] == 4.0
    assert goal["policy_received_wall_s"] == 10.0
    assert goal["target_times_s"] == pytest.approx((6.102, 6.104))
    assert goal["positions"] == prefix["positions"]

    with pytest.raises(ValueError, match="BRIDGE_INTERVAL_CHANGED"):
        request.materialize(start_time_s=6.05, bridge_time_s=6.001)


def test_fresh_physical_readback_does_not_renew_policy_observation():
    from so101_demo.act.path_proof import RelativePathRequest

    prefix = {
        "session_id": "session", "attempt_id": "attempt", "sequence": 0,
        "observation_time_s": 4.0, "target_times_s": (4.1,),
        "positions": ((.001,) * 6,),
    }
    request = RelativePathRequest.from_prefix(
        prefix, bridge_time_s=4.0, start_time_s=4.05,
        policy_received_wall_s=10.0,
    )

    request.require_policy_freshness(now_wall_s=10.18, max_age_s=.2,
                                     jitter_s=.01)
    with pytest.raises(ValueError, match="POLICY_OBSERVATION_STALE"):
        request.require_policy_freshness(now_wall_s=10.20, max_age_s=.2,
                                         jitter_s=.01)
