"""Namespace only addresses and parameter node selectors; preserve robot values."""

import copy
import importlib

import pytest


def module():
    return importlib.import_module("so101_demo.runtime.container_campaign.ros_namespace")


def test_absolute_endpoint_and_parameter_selectors_are_scoped():
    mod = module()
    namespace = "/act/campaign/w00"
    assert mod.qualified_name(namespace, "/arm_controller/follow_joint_trajectory") == namespace+"/arm_controller/follow_joint_trajectory"
    assert mod.qualified_name("/", "/joint_states") == "/joint_states"
    original = {"controller_manager": {"ros__parameters": {"update_rate": 500}},
                "arm_controller": {"ros__parameters": {"joints": ["1", "2"], "open_loop_control": False}},
                "/**": {"ros__parameters": {"publish_rate": 100.0}}}
    before = copy.deepcopy(original)
    scoped = mod.namespaced_parameters(original, namespace)
    assert scoped == {namespace+"/controller_manager": original["controller_manager"],
                      namespace+"/arm_controller": original["arm_controller"],
                      namespace+"/**": original["/**"]}
    assert original == before
    scoped[namespace+"/arm_controller"]["ros__parameters"]["joints"].append("3")
    assert original == before


@pytest.mark.parametrize("namespace", ["", "/", "relative", "/bad-name", "/act/../other", True])
def test_container_namespace_must_be_nonroot_and_canonical(namespace):
    with pytest.raises(ValueError, match="CONTAINER_ROS_NAMESPACE_INVALID"):
        module().validate_container_namespace(namespace)


def test_remap_targets_do_not_reprefix_already_scoped_names():
    mod = module()
    mappings = dict(mod.namespace_remappings("/act/campaign/w00"))
    assert mappings["/clock"] == "/act/campaign/w00/clock"
    assert mappings["/neck_controller/**"] == "/act/campaign/w00/neck_controller/\\1"
    assert all(not source.startswith("/act/campaign/w00/") for source in mappings)
