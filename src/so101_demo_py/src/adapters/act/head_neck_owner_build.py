"""Build the run's Head neck owner from the sealed inputs (the provider's one construction point)."""

import os
from pathlib import Path

from so101_demo.act import head_neck_limits as limits

CONTROLLER_PARAMETER_PATH = ('neck_controller', 'ros__parameters', 'head_deadman_directory')


def deadman_directory_from_controllers(controller_config_path):
    """The dead-man directory the sealed controllers file gives the neck controller."""
    import yaml
    document = yaml.safe_load(Path(controller_config_path).read_text(encoding='utf-8'))
    value = document
    for key in CONTROLLER_PARAMETER_PATH:
        value = value.get(key) if isinstance(value, dict) else None
    if type(value) is not str or not os.path.isabs(value):
        raise PermissionError('HEAD_NECK_DEADMAN_DIRECTORY_UNDECLARED')
    return value


def build_head_neck_owner(*, node, inputs, policy, emit=None, allowed_node_names=(), python=None,
                          helper_factory=None, services=None, graph=None, window=None):
    """The neck owner of one run on its owned node. Every collaborator may be injected by a directed test."""
    from .head_deadman_client import DeadmanHelper
    from .head_graph_check import HeadGraphCheck, RclpyGraph
    from .head_neck_owner import HeadNeckOwner
    from .head_neck_services import NeckControllerServices
    from .head_stop_window_subscriber import StopWindowSubscriber

    directory = HeadNeckOwner.ensure_directory(
        deadman_directory_from_controllers(inputs.refs['controller_config']['path']))
    owned_services = services is None
    services = NeckControllerServices(node) if services is None else services
    graph = HeadGraphCheck(graph=RclpyGraph(node), own_node_name=node.get_name(),
                           allowed_node_names=allowed_node_names) if graph is None else graph
    window = StopWindowSubscriber(context=node.context) if window is None else window
    return HeadNeckOwner(
        services=services, directory=directory, session_id=inputs.run['session_id'],
        generation=inputs.run['generation'], policy=policy, node_name=node.get_name(), graph=graph,
        window=window, helper_factory=helper_factory or (lambda **keywords: DeadmanHelper(
            python=python, **keywords)), emit=emit,
        closers=(services.close,) if owned_services else ())
