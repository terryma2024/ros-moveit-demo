from so101_demo.backends.mujoco.transport_observer import RELIABLE_QOS_DEPTH


def test_reliable_consumer_retains_at_least_the_producer_history() -> None:
    assert RELIABLE_QOS_DEPTH >= 100
