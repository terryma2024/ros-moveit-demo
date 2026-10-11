"""Splitting a large module must not introduce an import-time cycle between the new modules."""

import import_graph
import pytest


def test_the_source_packages_have_no_import_time_cycle():
    cycles = import_graph.import_cycles(import_graph.import_graph())

    assert cycles == [], "import-time cycles (move the shared names down into a lower module): " + "; ".join(
        " <-> ".join(cycle) for cycle in cycles[:5]
    )


def test_a_cycle_is_detected():
    graph = {"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": {"a"}}

    assert import_graph.import_cycles(graph) == [["a", "b", "c"]]


def test_a_chain_is_not_a_cycle():
    graph = {"a": {"b"}, "b": {"c"}, "c": set()}

    assert import_graph.import_cycles(graph) == []


@pytest.mark.parametrize("package", ["so101_demo", "so101_teleop"])
def test_every_source_package_is_in_the_graph(package):
    assert any(name == package or name.startswith(package + ".") for name in import_graph.module_files())
