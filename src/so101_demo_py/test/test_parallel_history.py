"""History reading is pure: it decodes retained documents and grants nothing.

Task 3 of the lightweight start guard plan. The active budget/measurement implementation is
being deleted; historical v1/v2 records must stay readable without dragging any of it back
into the process, and without touching the sealed bytes on disk.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from so101_demo.parallel_batch import history

PACKAGE = Path(__file__).resolve().parents[1]
V1_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v1.yaml"
V2_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v2.yaml"
V3_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v3.yaml"

RETIRED_MODULES = (
    "so101_demo.parallel_batch.resource_budget",
    "so101_demo.parallel_batch.resource_measurement",
    "so101_demo.parallel_batch.measurement_control",
    "so101_demo.parallel_batch.owned_resources",
    "so101_demo.parallel_batch.start_guard_probe",
    "so101_demo.parallel_batch.start_guard",
)


@pytest.mark.parametrize("path", [V1_CONFIG, V2_CONFIG, V3_CONFIG])
def test_history_reads_every_generation_without_authorizing(path):
    view = history.load_history(path)
    raw = path.read_bytes()
    assert view["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert view["bytes"] == len(raw)
    assert view["readonly"] is True
    assert view["authorizes_execution"] is False
    assert view["schema_version"] in history.history_versions()
    assert view["kind"] in ("LEGACY_V1", "CERTIFIED_V2", "ACTIVE_V3")


def test_history_rejects_unknown_versions_and_malformed_documents(tmp_path):
    unknown = tmp_path / "v9.yaml"
    unknown.write_text("schema_version: 9\n")
    with pytest.raises(history.HistoryError, match="HISTORY_SCHEMA_VERSION"):
        history.load_history(unknown)

    scalar = tmp_path / "scalar.yaml"
    scalar.write_text("- 1\n- 2\n")
    with pytest.raises(history.HistoryError, match="HISTORY_MAPPING"):
        history.load_history(scalar)

    missing = tmp_path / "missing.yaml"
    with pytest.raises(history.HistoryError, match="HISTORY_READ_FAILED"):
        history.load_history(missing)

    broken = tmp_path / "broken.yaml"
    broken.write_text("schema_version: [1, 2\n")
    with pytest.raises(history.HistoryError, match="HISTORY_DECODE_FAILED"):
        history.load_history(broken)


def test_history_keeps_the_sealed_bytes_unchanged(tmp_path):
    copy = tmp_path / "retained-v2.yaml"
    original = V2_CONFIG.read_bytes()
    copy.write_bytes(original)
    before = sorted(p.name for p in tmp_path.iterdir())
    digest_before = hashlib.sha256(copy.read_bytes()).hexdigest()

    view = history.load_history(copy)

    assert hashlib.sha256(copy.read_bytes()).hexdigest() == digest_before
    assert copy.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert view["raw_sha256"] == digest_before


def test_history_projection_is_read_only():
    view = history.load_history(V2_CONFIG)
    assert view["payload"]["schema_version"] == 2
    with pytest.raises(TypeError):
        view["payload"]["schema_version"] = 3
    with pytest.raises(TypeError):
        view["schema_version"] = 3


def test_history_import_pulls_in_no_retired_module():
    """Importing and using history must not import the retired budget/measurement chain."""

    script = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from so101_demo.parallel_batch import history\n"
        f"view = history.load_history(Path({str(V2_CONFIG)!r}))\n"
        "loaded = sorted(name for name in sys.modules if 'parallel_batch' in name)\n"
        "print(json.dumps({'schema_version': view['schema_version'], 'modules': loaded}))\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                            env=dict(os.environ))
    assert result.returncode == 0, result.stderr
    import json

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["schema_version"] == 2
    for module in RETIRED_MODULES:
        assert module not in payload["modules"], payload["modules"]


def test_history_jsonl_reader_is_lossless(tmp_path):
    record = tmp_path / "samples.jsonl"
    lines = ['{"sequence": 1, "monotonic_s": 10.0}', '', '{"sequence": 2, "monotonic_s": 10.05}']
    record.write_text("\n".join(lines) + "\n")
    entries = history.load_jsonl_history(record)
    assert [entry["sequence"] for entry in entries] == [1, 2]

    broken = tmp_path / "broken.jsonl"
    broken.write_text('{"sequence": 1}\nnot json\n')
    with pytest.raises(history.HistoryError, match="HISTORY_JSONL_INVALID"):
        history.load_jsonl_history(broken)


def test_history_and_contracts_agree_on_the_active_version():
    from so101_demo.parallel_batch import contracts

    view = history.load_history(V3_CONFIG)
    config = contracts.load_parallel_runtime_config_v3(V3_CONFIG)
    assert view["schema_version"] == config.schema_version == 3
    assert view["kind"] == "ACTIVE_V3"
