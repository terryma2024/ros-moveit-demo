"""E2: process-quality calibration is a measurement on this path, never a precondition for success."""

import ast
from pathlib import Path
from paths import PACKAGE_ROOT

SOURCE = PACKAGE_ROOT / "src"
QUALITY = "pick_place_calibration_measurement_contract"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def test_the_diagnostic_episode_chain_does_not_consult_the_quality_contract():
    """The chain that produces the episode must not gate on the process-quality calibration contract."""

    chain = [SOURCE / "cli" / "act_diagnostic_episode.py",
             SOURCE / "act" / "episode_qc.py",
             SOURCE / "act" / "episode_audit.py",
             SOURCE / "act" / "pick_place_runner.py",
             SOURCE / "act" / "recorder.py",
             SOURCE / "act" / "result_store.py"]
    expanded = []
    for path in chain:
        package = path.with_suffix("")
        expanded += sorted(package.rglob("*.py")) if not path.exists() and package.is_dir() else [path]
    for path in expanded:
        imports = _imports(path)
        offenders = sorted(name for name in imports if QUALITY in name)
        print("QUALITY", path.name, "->", offenders or "none")
        assert not offenders, (path.name, offenders)
