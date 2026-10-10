"""Deterministic affinity and work-stealing tests for adaptive pools."""

def test_twenty_points_seed_eight_workers_as_three_three_three_three_two_two_two_two():
    from so101_demo.parallel_batch.adaptive_queue import AdaptivePointSelector

    selector = AdaptivePointSelector(
        tuple(f"p{number:02d}" for number in range(1, 21)),
        tuple(f"worker-{number:02d}" for number in range(1, 9)),
        initial_points_per_worker=3,
    )

    assert tuple(map(len, selector.preferred.values())) == (3, 3, 3, 3, 2, 2, 2, 2)
    assert selector.global_points == ()


def test_idle_worker_steals_an_unleased_point_after_its_preferred_deque_is_empty():
    from so101_demo.parallel_batch.adaptive_queue import AdaptivePointSelector

    selector = AdaptivePointSelector(("p1", "p2", "p3"), ("w1", "w2"), 1)

    assert selector.choose("w1", {"p1", "p2", "p3"}) == "p1"
    assert selector.choose("w1", {"p2", "p3"}) == "p3"


def test_global_queue_precedes_stealing_and_stale_hints_are_skipped():
    from so101_demo.parallel_batch.adaptive_queue import AdaptivePointSelector

    selector = AdaptivePointSelector(
        ("p1", "p2", "p3", "p4", "p5"), ("w1", "w2"), 1
    )

    assert selector.choose("w1", {"p2", "p4", "p5"}) == "p4"
    assert selector.choose("w1", {"p2", "p5"}) == "p5"
    assert selector.choose("w1", {"p2"}) == "p2"
    assert selector.choose("w1", set()) is None
