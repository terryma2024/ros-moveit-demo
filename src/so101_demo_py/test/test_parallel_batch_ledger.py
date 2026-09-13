"""Consistency checks for the long-running parallel qualification ledger."""

from pathlib import Path
import re


REPOSITORY = Path(__file__).resolve().parents[3]
LEDGER = (
    REPOSITORY
    / "docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md"
)


def _header(document: str) -> str:
    return document.split("```yaml", 1)[1].split("```", 1)[0]


def _field(document: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}: (\S+)$", document, re.MULTILINE)
    assert match is not None, f"missing ledger field: {name}"
    return match.group(1)


def test_parallel_batch_ledger_recovery_index_matches_latest_body_record():
    document = LEDGER.read_text(encoding="utf-8")
    header = _header(document)
    checkpoints = tuple(
        int(value)
        for value in re.findall(r"^checkpoint_id: CP-(\d+)$", document, re.MULTILINE)
    )
    experiment_sections = tuple(
        (int(number), body)
        for number, body in re.findall(
            r"^## EXP-(\d+)[^\n]*\n\n```yaml\n(.*?)\n```",
            document,
            re.MULTILINE | re.DOTALL,
        )
    )
    assert checkpoints
    assert experiment_sections
    latest_number, latest_body = max(experiment_sections)
    latest_status = _field(latest_body, "status")
    expected_next = latest_number if latest_status in {"PLANNED", "RUNNING"} else latest_number + 1

    assert _field(header, "latest_checkpoint") == f"CP-{max(checkpoints):03d}"
    assert _field(header, "next_experiment") == f"EXP-{expected_next:03d}"
    assert re.fullmatch(r"[0-9a-f]{40}", _field(header, "current_commit"))
