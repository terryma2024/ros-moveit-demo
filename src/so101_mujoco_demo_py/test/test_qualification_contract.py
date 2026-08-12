from __future__ import annotations

import copy

import pytest

from so101_mujoco_demo_py.qualification import (
    InvalidRun,
    Lifecycle,
    ProductionQualificationRunner,
    RunStatus,
    StackHandle,
    summarize_records,
    validate_fingerprint,
)

FINGERPRINT = {
    "source_commit": "1" * 40,
    "dependency_sha256": "2" * 64,
    "task_scene_sha256": "8" * 64,
    "scene_sha256": "3" * 64,
    "robot_mjcf_sha256": "4" * 64,
    "urdf_sha256": "5" * 64,
    "motion_policy_sha256": "6" * 64,
    "contact_policy_sha256": "7" * 64,
}


def record(index: int, *, lifecycle: Lifecycle = Lifecycle.FULL_RESTART) -> dict:
    return {
        "experiment_id": f"EXP-{index}",
        "lifecycle": lifecycle.value,
        "status": RunStatus.SUCCESS.value,
        "fingerprint": dict(FINGERPRINT),
        "simulation_session_id": (
            f"full-{index}" if lifecycle is Lifecycle.FULL_RESTART else "reset-shared"
        ),
        "reset_epoch": index,
        "physical_outcome": {"primary_failure": None},
        "clean_shutdown": {"passed": True},
        "artifact_sha256": {"manifest": "a" * 64},
    }


def summarize(records: list[dict], lifecycle: Lifecycle = Lifecycle.FULL_RESTART) -> dict:
    return summarize_records(records, lifecycle=lifecycle, fingerprint=FINGERPRINT, target_count=5)


def test_exact_five_successes_are_required() -> None:
    assert summarize([record(index) for index in range(1, 6)])["qualified"] is True
    assert summarize([record(index) for index in range(1, 5)])["qualified"] is False


def test_valid_failure_resets_consecutive_count() -> None:
    records = [record(index) for index in range(1, 6)]
    records[3]["status"] = RunStatus.VALID_FAILURE.value
    assert summarize(records)["consecutive_successes"] == 1


def test_invalid_run_terminates_batch() -> None:
    records = [record(index) for index in range(1, 6)]
    records[1]["status"] = RunStatus.INVALID.value
    records[1]["failure"] = "wrong overlay"
    result = summarize(records)
    assert result["batch_invalid"] is True
    assert result["invalid_reason"] == "wrong overlay"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda item: item["fingerprint"].update({"scene_sha256": "b" * 64}),
        lambda item: item.update({"simulation_session_id": "full-1"}),
        lambda item: item.update({"clean_shutdown": {"passed": False}}),
        lambda item: item.pop("physical_outcome"),
        lambda item: item.update({"artifact_sha256": {"manifest": "short"}}),
    ],
)
def test_contamination_invalidates_batch(mutation) -> None:
    records = [record(index) for index in range(1, 6)]
    mutation(records[1])
    assert summarize(records)["batch_invalid"] is True


def test_reset_world_requires_one_session_and_increasing_epoch() -> None:
    records = [record(index, lifecycle=Lifecycle.RESET_WORLD) for index in range(1, 6)]
    assert summarize(records, Lifecycle.RESET_WORLD)["qualified"] is True
    contaminated = copy.deepcopy(records)
    contaminated[2]["reset_epoch"] = contaminated[1]["reset_epoch"]
    assert summarize(contaminated, Lifecycle.RESET_WORLD)["batch_invalid"] is True


def test_fingerprint_rejects_truncated_values() -> None:
    fingerprint = dict(FINGERPRINT)
    fingerprint["motion_policy_sha256"] = "short"
    with pytest.raises(RuntimeError, match="full lowercase SHA-256"):
        validate_fingerprint(fingerprint)


class DummyRunner(ProductionQualificationRunner):
    def __init__(self, evidence_root) -> None:
        super().__init__(evidence_root=evidence_root, fingerprint=FINGERPRINT)
        self.starts: list[tuple[str, int, int]] = []
        self.execution_count = 0

    def start_stack(self, *, session_id, domain_id, port, run_root):
        self.starts.append((session_id, domain_id, port))
        log_path = run_root / "launch.log"
        log_path.write_text("SO101_MOVE_GROUP_ORDERED_SHUTDOWN_OK\n")
        return StackHandle(
            process=None,  # type: ignore[arg-type]
            process_group_id=123,
            log_path=log_path,
            environment={},
            base_url=f"http://127.0.0.1:{port}",
            session_id=session_id,
        )

    @staticmethod
    def stop_stack(handle, *, timeout_s=60.0):
        return {"passed": True, "returncode": 0, "ordered_shutdown_marker": True}

    def execute_workflow(self, handle, *, experiment_id, run_root):
        self.execution_count += 1
        actions = run_root / "actions.json"
        owner = run_root / "owner.json"
        actions.write_text("{}")
        owner.write_text("{}")
        return {
            "experiment_id": experiment_id,
            "simulation_session_id": handle.session_id,
            "reset_epoch": self.execution_count,
            "simulation_step": 0,
            "physical_outcome": {"primary_failure": None},
            "artifact_paths": {"actions": str(actions), "owner": str(owner)},
        }


def test_full_restart_orchestration_creates_five_stacks(tmp_path) -> None:
    runner = DummyRunner(tmp_path)
    manifest = runner.run_batch(
        batch_id="full-batch",
        lifecycle=Lifecycle.FULL_RESTART,
        count=5,
        base_domain_id=170,
        base_port=8010,
    )
    assert manifest["summary"]["qualified"] is True
    assert len(runner.starts) == 5
    assert len({session for session, _, _ in runner.starts}) == 5
    assert [domain for _, domain, _ in runner.starts] == [170, 171, 172, 173, 174]


def test_reset_world_orchestration_reuses_one_stack_with_fresh_epochs(tmp_path) -> None:
    runner = DummyRunner(tmp_path)
    manifest = runner.run_batch(
        batch_id="reset-batch",
        lifecycle=Lifecycle.RESET_WORLD,
        count=5,
        base_domain_id=180,
        base_port=8020,
    )
    assert manifest["summary"]["qualified"] is True
    assert len(runner.starts) == 1
    assert [item["reset_epoch"] for item in manifest["records"]] == [1, 2, 3, 4, 5]


def test_pre_workflow_backend_failure_is_invalid(tmp_path) -> None:
    runner = ProductionQualificationRunner(evidence_root=tmp_path, fingerprint=FINGERPRINT)
    runner._request = lambda *args, **kwargs: {
        "http": 503,
        "response": {"succeeded": False, "code": "BACKEND_OPERATION_FAILED"},
    }
    handle = StackHandle(
        process=None,  # type: ignore[arg-type]
        process_group_id=123,
        log_path=tmp_path / "launch.log",
        environment={},
        base_url="http://127.0.0.1:1",
        session_id="session",
    )
    with pytest.raises(InvalidRun, match="BACKEND_OPERATION_FAILED"):
        runner._post_command(handle, "/simulation/reset", "lease")


class ExitedProcess:
    returncode = 0

    @staticmethod
    def poll():
        return 0

    @staticmethod
    def wait(timeout):
        return 0


def test_shutdown_rejects_child_process_death(tmp_path) -> None:
    log_path = tmp_path / "launch.log"
    log_path.write_text("SO101_MOVE_GROUP_ORDERED_SHUTDOWN_OK\nprocess has died [exit code -2]\n")
    handle = StackHandle(
        process=ExitedProcess(),  # type: ignore[arg-type]
        process_group_id=123,
        log_path=log_path,
        environment={},
        base_url="http://127.0.0.1:1",
        session_id="session",
    )
    result = ProductionQualificationRunner.stop_stack(handle)
    assert result["passed"] is False
    assert result["process_died"] is True
