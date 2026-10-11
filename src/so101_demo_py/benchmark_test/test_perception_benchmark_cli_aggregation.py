"""Output preflight, the resource sample plans and the aggregate command."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from perception_benchmark_cli_support import (
    ARCHIVE_DIRNAME,
    ARCHIVE_FILENAME,
    ARCHIVE_SHA256,
    CONFIG,
    _calibration_arguments,
    _verified_val_run,
)
import pytest

from so101_demo.cli import perception_benchmark
from so101_demo.cli.benchmark import aggregate as perception_benchmark_aggregate
from so101_demo.cli.benchmark import assets as perception_benchmark_assets
from so101_demo.cli.benchmark import calibrate as perception_benchmark_calibrate
from so101_demo.cli.benchmark import collect as perception_benchmark_collect
from so101_demo.cli.benchmark import common as perception_benchmark_common
from so101_demo.cli.benchmark import dry_run as perception_benchmark_dry_run
from so101_demo.perception_benchmark.contracts import (
    RunKind,
)


def test_every_formal_subcommand_requires_the_frozen_config() -> None:
    parser = perception_benchmark.build_parser()
    commands = next(item for item in parser._actions if item.dest == "command").choices

    for name in (
        "verify-assets",
        "inspect-archive",
        "prepare-dataset",
        "unlock-test",
        "collect",
        "calibrate",
        "aggregate",
    ):
        config_action = next(item for item in commands[name]._actions if item.dest == "config")
        assert config_action.required is True


@pytest.mark.parametrize(
    ("field", "drift"),
    [
        ("model", "grounded_sam"),
        ("model_id", "different-model"),
        ("platform", "linux"),
        ("device", "cuda"),
        ("dtype", "float16"),
        ("run_kind", RunKind.TEST_RAW_FROZEN),
        ("source_commit", "7" * 40),
        ("config_sha256", "8" * 64),
        ("weights_sha256", "9" * 64),
    ],
)
def test_calibration_requires_every_frozen_run_provenance_field(
    tmp_path: Path, field: str, drift: object
) -> None:
    arguments = _calibration_arguments(tmp_path)
    run = _verified_val_run(
        arguments.mac_run_root,
        platform="macos",
        source_commit=arguments.source_commit,
        config_sha256=perception_benchmark_assets.sha256_bytes(CONFIG.read_bytes()),
    )
    setattr(run.manifest, field, drift)
    config = perception_benchmark_common._load_frozen_config(CONFIG)

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        perception_benchmark_calibrate._validate_val_run_provenance(
            run,
            platform_name="macos",
            device="mps",
            arguments=arguments,
            config=config,
        )

    assert caught.value.code == "RUN_PROVENANCE_MISMATCH"


def test_raw_adapter_result_must_match_registered_limits() -> None:
    config = perception_benchmark_common._load_frozen_config(CONFIG)
    delegate = SimpleNamespace(
        model_id="plastic-cup-yolo11s-seg-v2",
        runtime_device="mps",
        _weights_sha256=("f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781"),
        collect=lambda *args: SimpleNamespace(
            irreversible_limits={"nms_iou": 0.70, "max_det": 300},
            raw_candidates=(),
        ),
    )
    adapter = perception_benchmark_dry_run._FrozenRawAdapter(
        delegate,
        "yolo_seg",
        config["models"]["yolo_seg"],
    )

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        adapter.collect(object(), object())

    assert caught.value.code == "LOW_FLOOR_CONFIG_MISMATCH"


def test_output_preflight_accepts_only_the_known_macos_tmp_alias() -> None:
    output = Path("/tmp") / "so101-preflight-does-not-exist"
    assert not output.exists()

    assert perception_benchmark_common._preflight_output_root(output) == output


def test_output_preflight_rejects_user_created_symlink_parent(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    alias_parent = tmp_path / "user-alias"
    alias_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        perception_benchmark_common._preflight_output_root(alias_parent / "output")

    assert caught.value.code == "OUTPUT_ROOT_PARENT_INVALID"


def test_collect_uses_shared_output_preflight_before_dataset_or_adapter_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    alias_parent = tmp_path / "user-alias"
    alias_parent.symlink_to(real_parent, target_is_directory=True)
    arguments = SimpleNamespace(
        run_kind="VAL_RAW",
        allow_oracle_diagnostic=False,
        split="val",
        threshold_lock=None,
        platform="macos",
        device="mps",
        dtype="float32",
        model="yolo_seg",
        weights=tmp_path / "best.pt",
        weights_sha256=("f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781"),
        model_root=None,
        manifest_sha256=None,
        source_commit="6" * 40,
        config=CONFIG,
        dataset_archive_sha256=ARCHIVE_SHA256,
        output_root=alias_parent / "formal-run",
    )
    monkeypatch.setattr(
        perception_benchmark_collect,
        "_inventory",
        lambda *a, **k: pytest.fail("unsafe output reached dataset boundary"),
    )
    monkeypatch.setattr(
        perception_benchmark_dry_run,
        "_inventory",
        lambda *a, **k: pytest.fail("unsafe output reached dataset boundary"),
    )
    monkeypatch.setattr(
        perception_benchmark_collect,
        "_raw_adapter",
        lambda *a, **k: pytest.fail("unsafe output reached adapter boundary"),
    )
    monkeypatch.setattr(
        perception_benchmark_dry_run,
        "_raw_adapter",
        lambda *a, **k: pytest.fail("unsafe output reached adapter boundary"),
    )

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        perception_benchmark_collect._handle_collect(arguments)

    assert caught.value.code == "OUTPUT_ROOT_PARENT_INVALID"
    assert not arguments.output_root.exists()


def test_unlock_rechecks_output_after_archive_verify_before_access_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive = (
        tmp_path
        / ARCHIVE_DIRNAME
        / ARCHIVE_FILENAME
    )
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"placeholder")
    for name in ("yolo.json", "grounded.json", "sealed.json"):
        (tmp_path / name).write_text("{}")
    output = tmp_path / "test-open"
    sealed_sha = perception_benchmark_assets.sha256_bytes((tmp_path / "sealed.json").read_bytes())
    arguments = SimpleNamespace(
        config=CONFIG,
        archive=archive,
        expected_sha256=ARCHIVE_SHA256,
        sealed_member_inventory=tmp_path / "sealed.json",
        yolo_threshold_lock=tmp_path / "yolo.json",
        grounded_sam_threshold_lock=tmp_path / "grounded.json",
        access_log=tmp_path / "access.ndjson",
        output_root=output,
    )
    monkeypatch.setattr(
        perception_benchmark_assets,
        "sha256_file",
        lambda path: arguments.expected_sha256,
    )
    monkeypatch.setattr(
        perception_benchmark_dry_run,
        "sha256_file",
        lambda path: arguments.expected_sha256,
    )
    monkeypatch.setattr(
        perception_benchmark_aggregate,
        "sha256_file",
        lambda path: arguments.expected_sha256,
    )

    def verify_and_race(*args: object) -> object:
        output.mkdir()
        return SimpleNamespace(sealed_test_member_inventory_sha256=sealed_sha)

    monkeypatch.setattr(
        perception_benchmark_assets.DatasetArchiveVerifier,
        "verify_archive",
        verify_and_race,
    )
    monkeypatch.setattr(
        perception_benchmark_assets,
        "unlock_test_seal",
        lambda *a, **k: pytest.fail("access event appended after output race"),
    )

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        perception_benchmark_assets._handle_unlock_test(arguments)

    assert caught.value.code == "OUTPUT_ROOT_ALREADY_EXISTS"
    assert not arguments.access_log.exists()


def _aggregation_plan_document(tmp_path: Path) -> dict[str, object]:
    return {
        "schema_version": "so101-perception-benchmark/aggregation-plan-v1",
        "dataset": {
            "root": str(tmp_path / "test-dataset"),
            "archive_sha256": ARCHIVE_SHA256,
            "inventory_sha256": "1" * 64,
            "test_access_event_sha256": "2" * 64,
            "sealed_member_inventory_sha256": "3" * 64,
            "threshold_lock_sha256s": ["4" * 64, "5" * 64],
        },
        "threshold_locks": {
            "yolo_seg": {"path": str(tmp_path / "yolo-lock.json"), "sha256": "4" * 64},
            "grounded_sam": {
                "path": str(tmp_path / "grounded-lock.json"),
                "sha256": "5" * 64,
            },
        },
        "runs": [
            {
                "platform": "macos",
                "model": "yolo_seg",
                "config": "TEST_RAW_FROZEN",
                "run_root": str(tmp_path / "run"),
                "expectation": str(tmp_path / "expectation.json"),
                "expectation_sha256": "6" * 64,
                "cold_process_samples": [],
                "resource_trace": None,
            }
        ],
        "source_commit": "7" * 40,
    }


def _resource_sample_document() -> dict[str, object]:
    return {
        "process_rss_bytes": 4096,
        "process_cpu_percent": 10.0,
        "gpu_memory_allocated_bytes": 1024,
        "gpu_memory_reserved_bytes": 2048,
        "gpu_utilization_percent": 30.0,
        "gpu_temperature_celsius": 40.0,
        "gpu_power_watts": 50.0,
        "unavailable_reasons": {},
        "tool_versions": {"resource-probe": "1.0"},
    }


def _plan_with_resource_sample(tmp_path: Path) -> dict[str, object]:
    plan = _aggregation_plan_document(tmp_path)
    plan["runs"][0]["resource_trace"] = {  # type: ignore[index]
        "sampling_frequency_hz": 10.0,
        "observations": [
            {
                "phase": "load",
                "monotonic_ns": 1,
                "formal_sample_index": None,
                "sample": _resource_sample_document(),
            }
        ],
    }
    return plan


@pytest.mark.parametrize(
    "mapping_drifts",
    [
        {"unavailable_reasons": [["gpu_power_watts", "probe unavailable"]]},
        {"tool_versions": [["resource-probe", "1.0"]]},
        {
            "unavailable_reasons": [["gpu_power_watts", "probe unavailable"]],
            "tool_versions": [["resource-probe", "1.0"]],
        },
    ],
)
def test_aggregate_rejects_resource_list_pairs_before_external_loaders(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mapping_drifts: dict[str, object],
) -> None:
    plan_document = _plan_with_resource_sample(tmp_path)
    sample = plan_document["runs"][0]["resource_trace"]["observations"][0][  # type: ignore[index]
        "sample"
    ]
    if "unavailable_reasons" in mapping_drifts:
        sample["gpu_power_watts"] = None
    sample.update(mapping_drifts)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(plan_document))
    monkeypatch.setattr(
        perception_benchmark_collect,
        "verify_threshold_lock",
        lambda *a, **k: pytest.fail("resource type drift reached an external loader"),
    )
    monkeypatch.setattr(
        perception_benchmark_aggregate,
        "verify_threshold_lock",
        lambda *a, **k: pytest.fail("resource type drift reached an external loader"),
    )

    result = perception_benchmark.main(
        [
            "aggregate",
            "--config",
            str(CONFIG),
            "--aggregation-plan",
            str(plan),
            "--aggregation-plan-sha256",
            perception_benchmark_assets.sha256_bytes(plan.read_bytes()),
            "--output-root",
            str(tmp_path / "report"),
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "AGGREGATION_PLAN_INVALID:" in captured.err
    assert "Traceback" not in captured.err


def test_aggregation_plan_accepts_raw_resource_mappings(tmp_path: Path) -> None:
    plan = _plan_with_resource_sample(tmp_path)

    _, _, runs, _ = perception_benchmark_aggregate._validated_aggregation_plan(plan)

    assert runs[0]["resource_trace"] is not None


def test_aggregation_plan_rejects_resource_scalar_type_drift(tmp_path: Path) -> None:
    plan = _plan_with_resource_sample(tmp_path)
    sample = plan["runs"][0]["resource_trace"]["observations"][0][  # type: ignore[index]
        "sample"
    ]
    sample["process_rss_bytes"] = []

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        perception_benchmark_aggregate._validated_aggregation_plan(plan)

    assert caught.value.code == "AGGREGATION_PLAN_INVALID"


@pytest.mark.parametrize(
    ("field", "drift"),
    [
        ("platform", []),
        ("model", {}),
        ("config", 7),
        ("cold_process_samples", {}),
        ("resource_trace", {"sampling_frequency_hz": "fast", "observations": []}),
    ],
)
def test_aggregation_plan_recursively_rejects_nested_type_drift(
    tmp_path: Path, field: str, drift: object
) -> None:
    plan = _aggregation_plan_document(tmp_path)
    plan["runs"][0][field] = drift  # type: ignore[index]

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        perception_benchmark_aggregate._validated_aggregation_plan(plan)

    assert caught.value.code == "AGGREGATION_PLAN_INVALID"


def test_aggregate_platform_list_is_stable_exit2_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_document = _aggregation_plan_document(tmp_path)
    plan_document["runs"][0]["platform"] = []  # type: ignore[index]
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(plan_document))
    locks = iter(
        (
            SimpleNamespace(
                lock_sha256="4" * 64,
                model="yolo_seg",
                source_commit="7" * 40,
            ),
            SimpleNamespace(
                lock_sha256="5" * 64,
                model="grounded_sam",
                source_commit="7" * 40,
            ),
        )
    )
    monkeypatch.setattr(
        perception_benchmark_collect,
        "verify_threshold_lock",
        lambda *a, **k: next(locks),
    )
    monkeypatch.setattr(
        perception_benchmark_aggregate,
        "verify_threshold_lock",
        lambda *a, **k: next(locks),
    )
    monkeypatch.setattr(
        perception_benchmark_calibrate,
        "load_dataset_inventory",
        lambda *a, **k: SimpleNamespace(
            dataset_root=tmp_path / "test-dataset",
            archive_sha256=plan_document["dataset"]["archive_sha256"],  # type: ignore[index]
            inventory_sha256="1" * 64,
        ),
    )
    monkeypatch.setattr(
        perception_benchmark_dry_run,
        "load_dataset_inventory",
        lambda *a, **k: SimpleNamespace(
            dataset_root=tmp_path / "test-dataset",
            archive_sha256=plan_document["dataset"]["archive_sha256"],  # type: ignore[index]
            inventory_sha256="1" * 64,
        ),
    )
    monkeypatch.setattr(
        perception_benchmark_aggregate,
        "load_dataset_inventory",
        lambda *a, **k: SimpleNamespace(
            dataset_root=tmp_path / "test-dataset",
            archive_sha256=plan_document["dataset"]["archive_sha256"],  # type: ignore[index]
            inventory_sha256="1" * 64,
        ),
    )
    monkeypatch.setattr(perception_benchmark_calibrate, "load_truth_samples", lambda *a, **k: ())
    monkeypatch.setattr(perception_benchmark_aggregate, "load_truth_samples", lambda *a, **k: ())
    monkeypatch.setattr(perception_benchmark_aggregate, "_expectation", lambda *a, **k: object())
    monkeypatch.setattr(perception_benchmark_calibrate, "_expectation", lambda *a, **k: object())
    monkeypatch.setattr(
        perception_benchmark_calibrate,
        "load_verified_run_evidence",
        lambda *a, **k: SimpleNamespace(),
    )
    monkeypatch.setattr(
        perception_benchmark_aggregate,
        "load_verified_run_evidence",
        lambda *a, **k: SimpleNamespace(),
    )

    result = perception_benchmark.main(
        [
            "aggregate",
            "--config",
            str(CONFIG),
            "--aggregation-plan",
            str(plan),
            "--aggregation-plan-sha256",
            perception_benchmark_assets.sha256_bytes(plan.read_bytes()),
            "--output-root",
            str(tmp_path / "report"),
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "AGGREGATION_PLAN_INVALID:" in captured.err
    assert "Traceback" not in captured.err
