from so101_gazebo_demo.grasp.stabilizer import GraspSample, PhysicalGraspStabilizer


def sample(session="s", fingerprint="f"):
    return GraspSample(session, fingerprint, 1.0, True, True, "wall_near", frozenset(), .0007, -.04, 0.0, .03, (0, 0, .2))


def test_capture_requires_fresh_session_and_fingerprint() -> None:
    samples = iter([sample("old"), sample(), sample()])
    result = PhysicalGraspStabilizer(lambda: next(samples, None), "f").capture("s", .01)
    assert result.failure is None
    assert result.sample_count == 2
    wrong = PhysicalGraspStabilizer(lambda: sample(fingerprint="other"), "f").capture("s", .001)
    assert wrong.failure.code == "PHYSICAL_GRASP_EVIDENCE_FINGERPRINT_MISMATCH"
