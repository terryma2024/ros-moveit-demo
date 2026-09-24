"""Contract tests for the short macOS test scratch (remediation Task 4).

Darwin refuses an AF_UNIX endpoint longer than 104 bytes, and an evidence-root ``TMPDIR`` is longer
than that before a fixture adds anything. The scratch therefore lives under ``/opt/data/tmp``, is
created once per run, and is handed to the test process through ``TMPDIR``/``TMP``/``TEMP``. The
helper never deletes it: it is a deletion candidate that the operator can review.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import stat
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="the short /opt/data/tmp scratch and Darwin socket budget require macOS",
)


def _scratch_module():
    spec = importlib.util.spec_from_file_location(
        "so101_demo.runtime.macos_test_scratch",
        Path(__file__).resolve().parents[1] / "src/runtime/macos_test_scratch.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def short_parent() -> Path:
    """A private parent that is itself short: the endpoint budget is a property of the path.

    pytest's own ``tmp_path`` under this scratch is already too deep for a Darwin endpoint, which is
    exactly the failure this module exists to prevent, so the fixture makes its own short directory
    under the registered scratch parent and leaves it as a deletion candidate.
    """

    parent = Path("/opt/data/tmp") / f"so101-sp-{uuid.uuid4().hex[:8]}"
    parent.mkdir(mode=0o700)
    parent.chmod(0o700)
    return parent


def test_long_evidence_root_uses_independent_short_macos_scratch(tmp_path: Path) -> None:
    module = _scratch_module()
    run_root = tmp_path / ("very-long-evidence-component-" * 4)

    result = module.prepare_macos_test_scratch(
        run_root, scratch_parent=Path("/opt/data/tmp"))

    assert result.scratch_path.parent == Path("/opt/data/tmp")
    assert not result.scratch_path.is_symlink()
    assert result.receipt_path.is_relative_to(run_root)
    assert result.max_endpoint_bytes < result.sun_path_limit
    assert result.scratch_path.is_dir()


def test_scratch_is_private_and_points_every_temp_variable_at_itself(
    tmp_path: Path, short_parent: Path
) -> None:
    module = _scratch_module()
    run_root = tmp_path / "run-root"

    result = module.prepare_macos_test_scratch(run_root, scratch_parent=short_parent)

    assert stat.S_IMODE(result.scratch_path.stat().st_mode) == 0o700
    assert result.owner_uid == os.getuid()
    assert result.mode == 0o700
    assert result.environment() == {
        "TMPDIR": str(result.scratch_path),
        "TMP": str(result.scratch_path),
        "TEMP": str(result.scratch_path),
    }
    assert result.endpoint_headroom_bytes > 0

    receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert receipt["scratch_path"] == str(result.scratch_path)
    assert receipt["deletion_candidate"] is True
    assert receipt["owner_uid"] == os.getuid()


def test_scratch_fails_closed_on_reuse_wrong_owner_wrong_mode_and_symlinked_parent(
    tmp_path: Path, short_parent: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _scratch_module()
    parent = short_parent

    first = module.prepare_macos_test_scratch(
        tmp_path / "run-root", scratch_parent=parent, run_id="fixed")
    with pytest.raises(module.MacOSTestScratchError) as error:
        module.prepare_macos_test_scratch(
            tmp_path / "run-root", scratch_parent=parent, run_id="fixed")
    assert error.value.code == "SCRATCH_ALREADY_EXISTS"
    assert first.scratch_path.is_dir()

    # A foreign owner is refused wherever it shows up on the path: this host cannot chown a
    # directory, so the check is exercised by claiming a different effective uid.
    real_getuid = module.os.getuid
    monkeypatch.setattr(module.os, "getuid", lambda: real_getuid() + 1)
    with pytest.raises(module.MacOSTestScratchError) as error:
        module.prepare_macos_test_scratch(
            tmp_path / "run-root", scratch_parent=parent, run_id="owner")
    assert error.value.code in {"SCRATCH_PARENT_OWNER", "SCRATCH_OWNER_MISMATCH"}
    monkeypatch.undo()

    real_mkdir = module.os.mkdir

    def loose_mkdir(path, mode=0o777, *args, **kwargs):
        return real_mkdir(path, 0o755, *args, **kwargs)

    monkeypatch.setattr(module.os, "mkdir", loose_mkdir)
    with pytest.raises(module.MacOSTestScratchError) as error:
        module.prepare_macos_test_scratch(
            tmp_path / "run-root", scratch_parent=parent, run_id="mode")
    assert error.value.code == "SCRATCH_MODE_MISMATCH"
    monkeypatch.undo()

    alias = Path("/opt/data/tmp") / f"so101-sp-alias-{uuid.uuid4().hex[:8]}"
    alias.symlink_to(parent)
    with pytest.raises(module.MacOSTestScratchError) as error:
        module.prepare_macos_test_scratch(tmp_path / "run-root", scratch_parent=alias)
    assert error.value.code == "SCRATCH_PARENT_SYMLINK"

    world_readable = Path("/opt/data/tmp") / f"so101-sp-open-{uuid.uuid4().hex[:8]}"
    world_readable.mkdir(mode=0o755)
    world_readable.chmod(0o755)
    with pytest.raises(module.MacOSTestScratchError) as error:
        module.prepare_macos_test_scratch(
            tmp_path / "run-root", scratch_parent=world_readable)
    assert error.value.code == "SCRATCH_PARENT_MODE"


def test_scratch_fails_closed_when_the_longest_endpoint_would_overflow(
    tmp_path: Path, short_parent: Path
) -> None:
    module = _scratch_module()
    deep = short_parent / ("padding-" * 6)
    deep.mkdir(mode=0o700)
    deep.chmod(0o700)

    with pytest.raises(module.MacOSTestScratchError) as error:
        module.prepare_macos_test_scratch(tmp_path / "run-root", scratch_parent=deep)
    assert error.value.code == "SCRATCH_ENDPOINT_TOO_LONG"
    assert not list(deep.glob("so101-service-gate-*"))


def test_endpoint_probe_binds_a_real_socket_at_the_longest_known_shape(
    tmp_path: Path, short_parent: Path
) -> None:
    module = _scratch_module()
    result = module.prepare_macos_test_scratch(tmp_path / "run-root", scratch_parent=short_parent)

    observed = module.probe_endpoint_bind(result.scratch_path, module.KNOWN_ENDPOINT_SUFFIXES[-1])

    assert observed <= result.sun_path_limit - 1
    assert observed >= result.max_endpoint_bytes - len(module.KNOWN_ENDPOINT_SUFFIXES[-1]) + 1


def test_the_helper_never_deletes_the_scratch_it_created(
    tmp_path: Path, short_parent: Path
) -> None:
    module = _scratch_module()
    parent = short_parent

    result = module.prepare_macos_test_scratch(tmp_path / "run-root", scratch_parent=parent)
    marker = result.scratch_path / "keep-me"
    marker.write_text("still here\n", encoding="utf-8")

    again = module.prepare_macos_test_scratch(tmp_path / "run-root", scratch_parent=parent)

    assert result.scratch_path.is_dir()
    assert marker.read_text(encoding="utf-8") == "still here\n"
    assert again.scratch_path != result.scratch_path
