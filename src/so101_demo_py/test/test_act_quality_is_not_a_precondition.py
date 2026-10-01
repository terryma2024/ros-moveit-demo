"""E2: process-quality calibration is a measurement on this path, never a precondition for success."""

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
QUALITY = "task8_measurement_contract"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def test_the_first_episode_chain_does_not_consult_the_quality_contract():
    """The chain that produces the episode must not gate on the process-quality calibration contract."""

    chain = [SOURCE / "cli" / "act_first_episode.py",
             SOURCE / "act" / "episode_qc.py",
             SOURCE / "act" / "episode_audit.py",
             SOURCE / "act" / "pick_place_runner.py",
             SOURCE / "act" / "recorder.py",
             SOURCE / "act" / "result_store.py"]
    for path in chain:
        imports = _imports(path)
        offenders = sorted(name for name in imports if QUALITY in name)
        print("QUALITY", path.name, "->", offenders or "none")
        assert not offenders, (path.name, offenders)
