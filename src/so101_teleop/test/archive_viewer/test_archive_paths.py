import json
from pathlib import Path
import pytest


def test_path_resolution_relocates_only_the_recorded_root(archive):
    from so101_teleop.archive_viewer.paths import resolve_package_path
    root=archive.package;old=Path('/old/collection')
    assert resolve_package_path(root,old,'/old/collection/collection-index.json')==root/'collection-index.json'
    for value in ['/old/collection-extra/secret','../secret','/etc/passwd']:
        with pytest.raises(Exception) as exc:resolve_package_path(root,old,value)
        assert getattr(exc.value,'status_code',None)==409


def test_symlink_escape_is_refused_after_resolution(archive):
    from so101_teleop.archive_viewer.paths import resolve_package_path
    (archive.package/'escape').symlink_to(archive.root/'SEALED-ROOTS.json')
    with pytest.raises(Exception) as exc:resolve_package_path(archive.package,archive.package,'escape')
    assert getattr(exc.value,'status_code',None)==409
