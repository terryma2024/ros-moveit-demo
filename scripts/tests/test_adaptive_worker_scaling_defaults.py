"""The adaptive worker-scaling script defaults to the frozen perception models."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

SCRIPTS = Path(__file__).resolve().parents[1]
REPOSITORY = SCRIPTS.parent
SCALING = SCRIPTS / "run_so101_adaptive_worker_scaling.zsh"
FROZEN_MODELS = (
    REPOSITORY / "src/so101_demo_py/src/parallel_batch/frozen_models.py"
)


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _dry_run_command() -> list[str]:
    result = subprocess.run(
        [
            "zsh", str(SCALING), "--worker-counts", "2",
            "--evidence-root", "/tmp/so101-adaptive-defaults-dry-run", "--dry-run",
        ],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip().split()


def _option_value(command: list[str], option: str) -> str:
    return command[command.index(option) + 1]


def test_the_dry_run_names_the_frozen_model_hashes() -> None:
    frozen = _module(FROZEN_MODELS, "so101_frozen_models_for_scaling_defaults")
    command = _dry_run_command()

    assert _option_value(command, "--yolo-weights-sha256") == frozen.FROZEN_YOLO_WEIGHTS_SHA256
    assert _option_value(command, "--grounded-manifest-sha256") == frozen.FROZEN_GROUNDED_SAM_MANIFEST_SHA256


def test_the_dry_run_names_the_model_paths_of_the_installed_service() -> None:
    service = _module(SCRIPTS / "so101-teleop-service.py", "so101_teleop_service_for_scaling_defaults")
    linux = service.defaults("linux")
    command = _dry_run_command()

    assert _option_value(command, "--yolo-weights") == linux["yolo_weights"]
    assert _option_value(command, "--grounded-root") == linux["grounded_root"]
