from types import SimpleNamespace

from so101_mujoco_demo_py import cli


def test_dry_run_cli_prints_machine_comparable_result(capsys, tmp_path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    assert cli.main(["--mode", "dry_run", "--checkpoint", str(checkpoint)]) == 0
    output = capsys.readouterr().out
    assert "status=DONE" in output
    assert "current_state=DONE" in output
    assert "transition_count=19" in output
    assert "state_trace=IDLE,PREPARE_OPEN_GRIPPER,MOVE_ABOVE_OBJECT" in output
    assert checkpoint.is_file()


def test_injected_failure_has_nonzero_exit_and_stable_code(capsys) -> None:
    assert cli.main(["--mode", "dry_run", "--fail-at", "DESCEND"]) == 1
    assert "failure=INJECTED_FAILURE" in capsys.readouterr().out


def test_plan_only_runs_offline_and_execute_requires_explicit_live_gate(capsys) -> None:
    assert cli.main(["--mode", "plan_only", "--plan-only-state", "LIFT"]) == 0
    assert "status=PLAN_ONLY_COMPLETE" in capsys.readouterr().out
    assert cli.main(["--mode", "execute"]) == 1
    output = capsys.readouterr().out
    assert "failure=EXPLICIT_EXECUTE_REQUIRED" in output


def test_execute_uses_the_production_live_runtime(monkeypatch, capsys, tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("release_retreat: {}\n", encoding="utf-8")
    evidence_root = tmp_path / "evidence"
    contact_policy = tmp_path / "contact.yaml"
    contact_policy.write_text("approval: {}\n", encoding="utf-8")
    manifest = evidence_root / "live-runtime-manifest.json"
    observed = []

    def run(config):
        observed.append(config)
        return SimpleNamespace(
            success=True,
            failed_phase=None,
            failure=None,
            completed_phases=("staged_approach", "release_retreat"),
            manifest_path=manifest,
        )

    monkeypatch.setattr(cli, "run_live_workflow", run)

    assert (
        cli.main(
            [
                "--mode",
                "execute",
                "--execute",
                "--session-id",
                "live-session",
                "--expected-reset-epoch",
                "4",
                "--evidence-root",
                str(evidence_root),
                "--motion-policy",
                str(policy),
                "--contact-policy",
                str(contact_policy),
            ]
        )
        == 0
    )

    assert len(observed) == 1
    assert observed[0].simulation_session_id == "live-session"
    assert observed[0].expected_reset_epoch == 4
    assert observed[0].contact_policy == contact_policy
    output = capsys.readouterr().out
    assert "status=DONE" in output
    assert "current_state=DONE" in output
    assert f"evidence_manifest={manifest}" in output


def test_execute_propagates_live_failure(monkeypatch, capsys, tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("release_retreat: {}\n", encoding="utf-8")
    contact_policy = tmp_path / "contact.yaml"
    contact_policy.write_text("approval: {}\n", encoding="utf-8")

    monkeypatch.setattr(
        cli,
        "run_live_workflow",
        lambda _config: SimpleNamespace(
            success=False,
            failed_phase="micro_lift",
            failure="PHASE_EXIT_NONZERO",
            completed_phases=("staged_approach", "contact_hold"),
            manifest_path=tmp_path / "manifest.json",
        ),
    )

    assert (
        cli.main(
            [
                "--mode",
                "execute",
                "--execute",
                "--session-id",
                "live-session",
                "--expected-reset-epoch",
                "4",
                "--evidence-root",
                str(tmp_path / "evidence"),
                "--motion-policy",
                str(policy),
                "--contact-policy",
                str(contact_policy),
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "status=ERROR" in output
    assert "failure=PHASE_EXIT_NONZERO" in output
    assert "failed_phase=micro_lift" in output
