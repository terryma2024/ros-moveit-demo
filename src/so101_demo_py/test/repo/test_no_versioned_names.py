"""No new versioned name enters the code base, and the allowlist of existing ones only shrinks.

A versioned name is a whole snake_case, kebab-case or CamelCase segment ``v<digits>`` in a file or directory
name, a module-level ``def`` / ``class`` / constant name, or a console script name. Locals and parameters are
never scanned. Every current hit is listed with a classification and a reason in ``style_allowlist.tsv``;
each phase of the refactor deletes the entries it renames away, and the companion check fails on an entry no
hit uses any more, so the list cannot go stale. The versioned-name allowlist must be empty, except for
reasoned ``permanent`` entries, at the end of phase B.
"""

import ast

import pytest
import style_inventory as inventory
from paths import TEST_ROOT

ALLOWLIST = TEST_ROOT / "repo" / "style_allowlist.tsv"


@pytest.mark.parametrize(
    "name",
    ["parallel_batch_v3.yaml", "BatchRequestV2", "SCHEMA_V3", "_V2_BOUND_KEYS", "load_config_v4", "v1", "Task_V2Runner"],
)
def test_a_version_segment_is_detected(name):
    assert inventory.versioned_segments(name) != []


@pytest.mark.parametrize(
    "name",
    ["x1", "q6", "dq1", "p1", "SO101_PORT", "version", "vision", "uv", "H264", "overview", "V", "ev3x", "IMAGENET1K"],
)
def test_names_that_only_contain_a_v_or_digits_are_not_versions(name):
    assert inventory.versioned_segments(name) == []


def test_only_module_level_definitions_are_scanned():
    source = (
        "def outer_v1(param_v2):\n"
        "    local_v3 = 1\n"
        "    def inner_v4():\n"
        "        pass\n"
        "class Holder:\n"
        "    member_v5 = 1\n"
        "    def method_v6(self):\n"
        "        pass\n"
        "CONSTANT_V7 = 1\n"
        "if True:\n"
        "    GUARDED_V8 = 2\n"
        "ANNOTATED_V9: int = 3\n"
    )

    names = {name for _kind, name in inventory._module_level_names(ast.parse(source))}

    assert names == {"outer_v1", "Holder", "CONSTANT_V7", "GUARDED_V8", "ANNOTATED_V9"}


def test_the_allowlist_is_well_formed():
    _entries, problems = inventory.load_allowlist(ALLOWLIST)

    assert problems == []


def test_every_versioned_name_is_in_the_allowlist():
    missing, _unused, _problems = inventory.compare_with_allowlist(inventory.SCAN_VERSIONED, ALLOWLIST)

    assert missing == [], (
        "new versioned names (rename them by meaning; a format that needs a version carries a schema_version field): "
        + ", ".join(f"{hit.path}::{hit.name}" for hit in missing[:25])
    )


def test_the_allowlist_has_no_versioned_entry_without_a_hit():
    _missing, unused, _problems = inventory.compare_with_allowlist(inventory.SCAN_VERSIONED, ALLOWLIST)

    assert unused == [], "delete these entries from style_allowlist.tsv, their names are gone: " + ", ".join(unused[:25])
