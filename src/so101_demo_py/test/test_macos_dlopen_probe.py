"""Closed current-product Gate A controls for the macOS MuJoCo station."""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _module():
    spec = importlib.util.find_spec("so101_demo.runtime.macos_dlopen_probe")
    assert spec is not None, "macOS Gate A control tooling is not implemented yet"
    return importlib.import_module("so101_demo.runtime.macos_dlopen_probe")


def _attested(module, *, marker="DLOPEN_SUCCEEDED", first_bad=None):
    return module.GateAControlObservation(
        invariants_valid=True,
        collector_healthy=True,
        process_identity_stable=True,
        controller_role_attested=True,
        controller_executable_attested=True,
        dlopen_marker=marker,
        loader_error=None,
        exact_vendor_missing=False,
        plugin_image_attested=marker == "DLOPEN_SUCCEEDED",
        vendor_image_attested=marker == "DLOPEN_SUCCEEDED",
        ros_instance_markers=(
            "PLUGIN_RESOLVED",
            "SIMULATION_ENDPOINT_READY",
            "HARDWARE_INITIALIZING",
            "HARDWARE_READY",
            "CONTROLLER_MANAGER_SERVICES_READY",
            "CONTROLLERS_ACTIVE",
        )
        if first_bad is None and marker == "DLOPEN_SUCCEEDED"
        else (),
        ready=first_bad is None and marker == "DLOPEN_SUCCEEDED",
        first_bad_phase=first_bad,
        timed_out=False,
        cleanup_complete=True,
        invalid_reasons=(),
    )


def _missing(module, *, collector=True, identity=True):
    return module.GateAControlObservation(
        invariants_valid=True,
        collector_healthy=collector,
        process_identity_stable=identity,
        controller_role_attested=identity,
        controller_executable_attested=identity,
        dlopen_marker="DLOPEN_FAILED",
        loader_error=(
            "Library not loaded: @rpath/libmujoco.3.4.0.dylib"
        ),
        exact_vendor_missing=True,
        plugin_image_attested=False,
        vendor_image_attested=False,
        ros_instance_markers=(),
        ready=False,
        first_bad_phase=None,
        timed_out=False,
        cleanup_complete=True,
        invalid_reasons=(),
    )


def test_closed_verdict_axes_match_the_reviewed_design() -> None:
    module = _module()

    assert [item.value for item in module.CurrentBoundaryVerdict] == [
        "UNCONFIRMED_CURRENT",
        "CONFIRMED_RPATH",
        "CURRENT_CLOSURE_ALREADY_VALID",
        "CURRENT_NON_RPATH_FAILURE",
        "INVALID_CONTROL",
    ]
    assert [item.value for item in module.ControllerVerdict] == [
        "NOT_EXCLUDED",
        "EXCLUDED_BEFORE_ROS_PLUGIN_INSTANCE_INIT",
        "CURRENT_CONTROLLER_PATH_OPERATIONAL",
    ]
    assert [item.value for item in module.LegacyAttribution] == [
        "LEGACY_TRACEABLE",
        "LEGACY_PROVENANCE_UNRECOVERABLE",
    ]


def test_valid_n_missing_and_p_pass_confirms_rpath() -> None:
    module = _module()

    decision = module.reduce_gate_a_controls(_missing(module), _attested(module))

    assert decision.current is module.CurrentBoundaryVerdict.CONFIRMED_RPATH
    assert (
        decision.controller
        is module.ControllerVerdict.EXCLUDED_BEFORE_ROS_PLUGIN_INSTANCE_INIT
    )


def test_same_loader_surface_without_collector_or_process_identity_is_invalid() -> None:
    module = _module()

    decision = module.reduce_gate_a_controls(
        _missing(module, collector=False, identity=False), _attested(module)
    )

    assert decision.current is module.CurrentBoundaryVerdict.INVALID_CONTROL
    assert decision.controller is module.ControllerVerdict.NOT_EXCLUDED


def test_both_pass_selects_current_closure_without_product_edit() -> None:
    module = _module()

    decision = module.reduce_gate_a_controls(_attested(module), _attested(module))

    assert (
        decision.current
        is module.CurrentBoundaryVerdict.CURRENT_CLOSURE_ALREADY_VALID
    )
    assert (
        decision.controller
        is module.ControllerVerdict.CURRENT_CONTROLLER_PATH_OPERATIONAL
    )


@pytest.mark.parametrize(
    "mutation",
    ["timeout", "cleanup", "identity", "missing-marker", "semantic"],
)
def test_control_invariants_win_before_surface_classification(mutation: str) -> None:
    module = _module()
    document = _missing(module).as_document()
    if mutation == "timeout":
        document["timed_out"] = True
    elif mutation == "cleanup":
        document["cleanup_complete"] = False
    elif mutation == "identity":
        document["process_identity_stable"] = False
    elif mutation == "missing-marker":
        document["dlopen_marker"] = None
    else:
        document["invariants_valid"] = False
    invalid_n = module.GateAControlObservation.from_document(document)

    decision = module.reduce_gate_a_controls(invalid_n, _attested(module))

    assert decision.current is module.CurrentBoundaryVerdict.INVALID_CONTROL


def test_non_rpath_failure_stops_at_the_first_bad_ros_phase() -> None:
    module = _module()
    non_rpath = _attested(module, first_bad="HARDWARE_READY")

    decision = module.reduce_gate_a_controls(non_rpath, _attested(module))

    assert decision.current is module.CurrentBoundaryVerdict.CURRENT_NON_RPATH_FAILURE
    assert decision.controller is module.ControllerVerdict.NOT_EXCLUDED


def test_frozen_semantics_allow_only_the_manifest_vendor_dyld_delta(tmp_path: Path) -> None:
    module = _module()
    vendor = tmp_path / "closure/opt/mujoco_vendor/lib"
    vendor.mkdir(parents=True)
    base = {
        "PATH": "/usr/bin:/bin",
        "PYTHONNOUSERSITE": "1",
        "LANG": "C.UTF-8",
    }
    n = module.FrozenSemanticLaunchContract(
        argv=("ros2", "launch", "so101_demo_py", "so101_mujoco_task_station.launch.py"),
        environment=base,
        vendor_library_directory=vendor,
    )
    p = module.FrozenSemanticLaunchContract(
        argv=n.argv,
        environment={**base, "DYLD_LIBRARY_PATH": str(vendor)},
        vendor_library_directory=vendor,
    )

    module.validate_np_semantic_delta(n, p)

    with pytest.raises(module.GateAControlError) as error:
        module.validate_np_semantic_delta(
            n,
            module.FrozenSemanticLaunchContract(
                argv=(*n.argv, "headless:=true"),
                environment=p.environment,
                vendor_library_directory=vendor,
            ),
        )
    assert error.value.code == "CONTROL_SEMANTIC_DIFF"


def test_gate_a_binding_validates_domain_session_and_containment(tmp_path: Path) -> None:
    module = _module()
    root = tmp_path / "run"
    root.mkdir()

    binding = module.GateARunBinding.create(
        run_root=root,
        session_id="gate-a-safe-1",
        ros_domain_id=232,
    )

    assert binding.tmpdir == binding.tmp == binding.temp
    assert binding.report_path.is_relative_to(root)
    assert binding.task_evidence_root.is_relative_to(root)
    for domain in (-1, 233):
        with pytest.raises(module.GateAControlError) as error:
            module.GateARunBinding.create(
                run_root=root, session_id="gate-a-safe-2", ros_domain_id=domain
            )
        assert error.value.code == "CONTROL_BINDING_INVALID"
    with pytest.raises(module.GateAControlError):
        module.GateARunBinding.create(
            run_root=root, session_id="../escape", ros_domain_id=22
        )


def test_create_binding_accepts_precreated_empty_plan_run_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    run_root = tmp_path / "negative"
    run_root.mkdir()
    output = run_root / "run-binding.json"
    fake_binding = SimpleNamespace(as_document=lambda: {"control": "N"})
    monkeypatch.setattr(module, "load_manifest", lambda _path: object())
    monkeypatch.setattr(module, "_next_domain", lambda _root, _session: 117)
    monkeypatch.setattr(
        module.GateARunBinding, "create", lambda **_kwargs: fake_binding
    )

    result = module.main(
        [
            "--create-run-binding",
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--control",
            "N",
            "--run-root",
            str(run_root),
            "--session-id",
            "gate-a-plan-n",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert output.read_text(encoding="utf-8") == '{\n  "control": "N"\n}\n'


def test_create_binding_refuses_reused_nonempty_plan_run_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    run_root = tmp_path / "negative"
    run_root.mkdir()
    (run_root / "foreign.txt").write_text("occupied", encoding="utf-8")
    monkeypatch.setattr(module, "load_manifest", lambda _path: object())

    with pytest.raises(module.GateAControlError) as error:
        module.main(
            [
                "--create-run-binding",
                "--manifest",
                str(tmp_path / "manifest.json"),
                "--control",
                "N",
                "--run-root",
                str(run_root),
                "--session-id",
                "gate-a-plan-n",
                "--output",
                str(run_root / "run-binding.json"),
            ]
        )

    assert error.value.code == "CONTROL_BINDING_INVALID"


def test_direct_probe_observation_preserves_markers_and_raw_dlerror(tmp_path: Path) -> None:
    module = _module()
    plugin = tmp_path / "libplugin.dylib"
    plugin.write_bytes(b"not a dylib")

    observation = module.run_direct_dlopen(plugin)

    assert observation.markers[0] == "DLOPEN_STARTED"
    assert observation.markers[-1] == "DLOPEN_FAILED"
    assert observation.dlerror
    assert observation.plugin_path == plugin.resolve()
    assert observation.plugin_sha256
