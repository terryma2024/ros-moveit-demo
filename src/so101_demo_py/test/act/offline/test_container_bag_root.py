"""Where a bag may live in an ACT instance: the owned root, or the fixed output mount proven to be its `output`.

A bind mount is the same directory reached through two paths, and an unprivileged test cannot create one. So the identity
check is a small pure function over two directory paths, tested here with real directories (the same directory twice,
different directories, a symlink, a missing and a non-canonical path), and the bag decision is tested with that function
injected. The real bind mount of `<owned_root>/output` at `/act/output` is exercised only in a real container; the recorder
writes the decision and both directories' `st_dev`/`st_ino` into its ready record so that run proves it.
"""

import importlib
import json
import os

import pytest



def bag_root():
    return importlib.import_module('so101_demo.act.offline.bag_root')


def paths():
    return importlib.import_module('so101_demo.runtime.container_campaign.paths')


def instance(tmp_path):
    root = tmp_path / 'w00/g1'
    (root / 'output').mkdir(parents=True)
    return root


def bag_under(directory):
    raw = directory / 'tasks/task-1/attempts/default/lease/working/raw'
    raw.mkdir(parents=True)
    return raw / 'bag'


def verdict(same):
    return lambda mount, owned_output: dict(same=same, mount=str(mount), owned_output=str(owned_output))


def test_the_fixed_mount_is_the_one_the_role_mounts_declare():
    assert str(paths().TASK_OUTPUT_MOUNT) == '/act/output'


def test_identity_accepts_one_directory_and_refuses_everything_else(tmp_path):
    real = tmp_path / 'a/output'
    real.mkdir(parents=True)
    other = tmp_path / 'b/output'
    other.mkdir(parents=True)
    link = tmp_path / 'link'
    link.symlink_to(real)

    assert paths().task_output_identity(real, real)['same'] is True               # the same directory
    assert paths().task_output_identity(real, other)['same'] is False             # two directories
    assert paths().task_output_identity(link, real)['same'] is False              # a symlink to the right one
    assert paths().task_output_identity(real, link)['same'] is False
    assert paths().task_output_identity(tmp_path / 'missing', real)['same'] is False
    assert paths().task_output_identity(real, tmp_path / 'missing')['same'] is False
    assert paths().task_output_identity(tmp_path / 'a/x/../output', real)['same'] is False
    assert paths().task_output_identity('a/output', real)['same'] is False        # relative
    (tmp_path / 'file').write_text('x')
    assert paths().task_output_identity(tmp_path / 'file', tmp_path / 'file')['same'] is False   # not a directory


def test_identity_reports_both_directories_for_the_evidence(tmp_path):
    real = tmp_path / 'output'
    real.mkdir()
    result = paths().task_output_identity(real, real)

    info = os.lstat(real)
    for label in ('mount', 'owned_output'):
        assert result[label] == dict(path=str(real), directory=True, st_dev=info.st_dev, st_ino=info.st_ino)
    missing = paths().task_output_identity(tmp_path / 'nowhere', real)
    assert missing['mount'] == dict(path=str(tmp_path / 'nowhere'), directory=False, st_dev=None, st_ino=None)


def test_a_bag_under_the_output_mount_needs_the_mount_to_be_this_instances_output(tmp_path):
    root = instance(tmp_path)
    mount = tmp_path / 'mount'
    mount.mkdir()
    bag = bag_under(mount)

    accepted = bag_root().bag_root_decision(bag, root, output_mount=mount, output_identity=verdict(True))
    refused = bag_root().bag_root_decision(bag, root, output_mount=mount, output_identity=verdict(False))

    assert accepted['code'] is None and accepted['location'] == 'task_output'
    assert refused['code'] == 'CONTAINER_BAG_OUTPUT_NOT_INSTANCE' and refused['location'] is None


def test_a_bag_under_the_mount_is_refused_with_the_real_identity_when_it_is_not_this_instances_output(tmp_path):
    root = instance(tmp_path)
    mount = tmp_path / 'mount'          # a different directory than <root>/output: a foreign output or a tmpfs
    mount.mkdir()

    decision = bag_root().bag_root_decision(bag_under(mount), root, output_mount=mount)

    assert decision['code'] == 'CONTAINER_BAG_OUTPUT_NOT_INSTANCE'
    assert decision['output_identity']['same'] is False


def test_a_bag_under_neither_root_is_refused_even_when_the_mount_is_proven(tmp_path):
    root = instance(tmp_path)
    mount = tmp_path / 'mount'
    mount.mkdir()
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()

    decision = bag_root().bag_root_decision(bag_under(elsewhere), root, output_mount=mount,
                                            output_identity=verdict(True))
    assert decision['code'] == 'CONTAINER_BAG_ROOT_MISMATCH'
    # a sibling that only shares the mount's name prefix is not under the mount
    sibling = tmp_path / 'mount-other'
    sibling.mkdir()
    decision = bag_root().bag_root_decision(bag_under(sibling), root, output_mount=mount, output_identity=verdict(True))
    assert decision['code'] == 'CONTAINER_BAG_ROOT_MISMATCH'


def test_a_bag_under_the_owned_root_is_accepted_and_traversal_stays_refused(tmp_path):
    root = instance(tmp_path)

    accepted = bag_root().bag_root_decision(bag_under(root), root)
    assert accepted['code'] is None and accepted['location'] == 'owned_root'
    mount = tmp_path / 'mount'
    mount.mkdir()
    traversal = mount / 'tasks/../../elsewhere/bag'
    decision = bag_root().bag_root_decision(traversal, root, output_mount=mount, output_identity=verdict(True))
    assert decision['code'] == 'CONTAINER_BAG_ROOT_MISMATCH' and decision['location'] is None


def run_recorder(tmp_path, monkeypatch, bag, *, container):
    raw_recorder = importlib.import_module('so101_demo.act.offline.raw_recorder')
    monkeypatch.delenv('SO101_ACT_CONTAINER_NAMESPACE', raising=False)
    monkeypatch.delenv('ROS_NAMESPACE', raising=False)
    if container:
        monkeypatch.setenv('SO101_ACT_INSTANCE_ROOT', str(tmp_path / 'w00/g1'))
    else:
        monkeypatch.delenv('SO101_ACT_INSTANCE_ROOT', raising=False)
    ready, stats = tmp_path / 'ready.json', tmp_path / 'stats.json'
    code = raw_recorder.main(['--bag-dir', str(bag), '--scene-reads', str(tmp_path / 'scene.jsonl'),
                              '--ready-file', str(ready), '--stats-file', str(stats)])
    return code, json.loads(ready.read_text())


def test_the_recorders_ready_record_carries_the_bag_location_decision_for_the_instance_marker_alone(tmp_path, monkeypatch):
    instance(tmp_path)
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()

    code, ready = run_recorder(tmp_path, monkeypatch, bag_under(elsewhere), container=True)
    assert not (elsewhere / 'tasks/task-1/attempts/default/lease/working/raw/bag-topic-map.json').exists()

    assert code == 3 and ready['state'] == 'FAILED' and 'CONTAINER_BAG_ROOT_MISMATCH' in ready['error']
    decision = ready['bag_root']
    assert decision['code'] == 'CONTAINER_BAG_ROOT_MISMATCH' and decision['output_mount'] == '/act/output'
    assert set(decision['output_identity']['mount']) == {'path', 'directory', 'st_dev', 'st_ino'}
    assert decision['output_identity']['owned_output']['st_ino'] == os.lstat(tmp_path / 'w00/g1/output').st_ino


def test_outside_an_instance_the_ready_record_is_unchanged(tmp_path, monkeypatch):
    def refuse(self):
        raise RuntimeError('no ROS in this test')

    monkeypatch.setattr(importlib.import_module('so101_demo.act.offline.raw_recorder').RawRecorder, 'start', refuse)
    code, ready = run_recorder(tmp_path, monkeypatch, tmp_path / 'missing/bag', container=False)

    assert 'bag_root' not in ready


def test_the_decision_carries_the_readback_whether_or_not_it_accepts(tmp_path):
    root = instance(tmp_path)
    mount = tmp_path / 'mount'
    mount.mkdir()
    bag = bag_under(mount)

    refused = bag_root().bag_root_decision(bag, root, output_mount=mount)
    accepted = bag_root().bag_root_decision(bag, root, output_mount=mount, output_identity=verdict(True))

    assert refused['code'] == 'CONTAINER_BAG_OUTPUT_NOT_INSTANCE' and refused['location'] is None
    assert refused['output_identity']['mount']['st_ino'] is not None
    assert refused['output_identity']['owned_output']['st_ino'] is not None
    assert accepted['code'] is None and accepted['location'] == 'task_output'
