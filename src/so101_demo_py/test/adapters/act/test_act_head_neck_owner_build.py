"""The provider's one construction point for the neck owner."""

import os
from types import SimpleNamespace

import pytest

from head_owner_support import FakeGraph, FakeHelper, FakeServices, FakeWindow, policy
from so101_demo.adapters.act.head_neck_owner_build import (
    build_head_neck_owner, deadman_directory_from_controllers)


def controllers(tmp_path, directory):
    path = tmp_path / 'controllers.yaml'
    path.write_text(f'neck_controller:\n  ros__parameters:\n    head_deadman_directory: {directory}\n'
                    'arm_controller:\n  ros__parameters:\n    joints: ["1"]\n')
    return path


def test_the_dead_man_directory_comes_from_the_sealed_controllers_file(tmp_path):
    assert deadman_directory_from_controllers(controllers(tmp_path, '/tmp/x')) == '/tmp/x'


@pytest.mark.parametrize('text', ['neck_controller:\n  ros__parameters: {}\n', 'arm_controller: {}\n',
                                  'neck_controller:\n  ros__parameters:\n    head_deadman_directory: rel\n'])
def test_a_missing_or_relative_directory_refuses(tmp_path, text):
    path = tmp_path / 'c.yaml'
    path.write_text(text)
    with pytest.raises(PermissionError, match='HEAD_NECK_DEADMAN_DIRECTORY_UNDECLARED'):
        deadman_directory_from_controllers(path)


def test_the_owner_is_built_with_a_private_directory_and_the_run_scope(tmp_path):
    import tempfile
    directory = os.path.join(tempfile.mkdtemp(prefix='dmb'), 'neck')
    inputs = SimpleNamespace(run=dict(session_id='s1', generation=9),
                             refs=dict(controller_config=dict(path=str(controllers(tmp_path, directory)))))
    events = []
    owner = build_head_neck_owner(
        node=SimpleNamespace(get_name=lambda: 'head_run_x', context=None), inputs=inputs, policy=policy(),
        emit=lambda kind, record: events.append(kind), services=FakeServices(), graph=FakeGraph(),
        window=FakeWindow(), helper_factory=FakeHelper)
    assert owner.directory == directory and oct(os.stat(directory).st_mode & 0o777) == '0o700'
    assert (owner.generation, owner.session_id, owner.node_name) == (9, 's1', 'head_run_x')
    owner.close()
