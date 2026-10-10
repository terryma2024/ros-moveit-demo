"""No new process name enters a wire identifier, and the allowlist of existing ones only shrinks.

Wire identifiers are the strings that cross a process or file boundary: error codes, environment variables,
sealed file names, ``kind`` values. The scan reads the string values (never docstrings) of package source and
of ``config/`` documents for ``TASK<n>_``, ``SO101_TASK<n>``, ``task<n>-`` / ``task<n>_`` and whole-string
``...-v<n>`` kind literals. The wire allowlist must be empty, except for reasoned ``permanent`` entries (model
and dataset ids, references to frozen history), at the end of phase D.
"""

import ast

import pytest
import style_inventory as inventory
from paths import TEST_ROOT

ALLOWLIST = TEST_ROOT / "repo" / "style_allowlist.tsv"


@pytest.mark.parametrize(
    "value",
    ["TASK8_MODE_INVALID", "SO101_TASK8_BOTTOM_IO_SEAM", "task8-live", "task8_phase", "so101-dynamic-mujoco-execute-v2",
     "ACT_TASK8_STARTUP_OWNER_UNBOUND", "config/act/task8-live-anchors.yaml"],
)
def test_a_process_wire_string_is_detected(value):
    assert inventory.is_wire_string(value)


@pytest.mark.parametrize(
    "value",
    ["TASK_MODE_INVALID", "pick_place_validation", "a sentence about version v2 of nothing", "so101-run-result",
     "SO101_PORT", "task", "tasks8", "retask8x"],
)
def test_ordinary_strings_are_not_wire_hits(value):
    assert not inventory.is_wire_string(value)


def test_docstrings_are_not_wire_values():
    tree = ast.parse('"""task8-live in a module docstring."""\n\ndef f():\n    """TASK8_X in a docstring."""\n    return "TASK8_REAL"\n')

    docstrings = inventory._docstring_nodes(tree)
    strings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]

    assert strings == ["TASK8_REAL"]


def test_the_allowlist_is_well_formed():
    _entries, problems = inventory.load_allowlist(ALLOWLIST)

    assert problems == []


def test_every_process_wire_string_is_in_the_allowlist():
    missing, _unused, _problems = inventory.compare_with_allowlist(inventory.SCAN_WIRE, ALLOWLIST)

    assert missing == [], (
        "new process names on the wire (give error codes, env vars and kinds a business name): "
        + ", ".join(f"{hit.path}::{hit.name}" for hit in missing[:25])
    )


def test_the_allowlist_has_no_wire_entry_without_a_hit():
    _missing, unused, _problems = inventory.compare_with_allowlist(inventory.SCAN_WIRE, ALLOWLIST)

    assert unused == [], "delete these entries from style_allowlist.tsv, their strings are gone: " + ", ".join(unused[:25])
