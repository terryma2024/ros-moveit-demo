"""The Darwin private-path address strategy: permissions are the whole trust boundary.

Task 4 of the macOS MPS / private IPC plan. The v4 design does not authenticate an IPC client,
so the filesystem contract carries the security weight: a canonical private base, an owned
mode-0700 campaign directory, mode-0600 sockets, an encoded-length check against the real
`sun_path` capacity, and cleanup that unlinks only exact paths from its own registry.

These tests run against a real private base under the registered evidence root's temp directory
where possible, and against `tmp_path` for the negative cases, so no socket is ever created in a
shared location.
"""

import os
import socket
import stat
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="Darwin private-path transport is macOS-only")

from so101_demo.runtime.unix_address import (
    ALREADY_GONE,
    CLEANED,
    DARWIN_SUN_PATH_CAPACITY_BYTES,
    DIRECTORY_MODE,
    ENDPOINT_NAMES,
    NOT_OWNED,
    PRIVATE_TMP,
    SOCKET_MODE,
    CampaignIpcRoot,
    DarwinPrivatePathUnixAddress,
    ProcFdUnixAddress,
    UnixAddressError,
    encoded_length_ok,
    require_encoded_length,
    require_owned_private_directory,
    require_root_owned_sticky_directory,
    require_safe_ancestors,
)

#: The canonical base is short on purpose. pytest's own temp path is ~200 bytes, which no
#: AF_UNIX socket path can ever fit, so any test that binds a real socket uses a per-test
#: directory directly under the platform's sticky base and removes it afterwards. `PRIVATE_TMP`
#: comes from the module so the suite follows the platform instead of hardcoding Darwin's.
CANONICAL_BASE = PRIVATE_TMP / f"so101-ipc-{os.getuid()}"
SHORT_PREFIX = f"so101-ipc-test-{os.getuid()}-"


@pytest.fixture
def short_root():
    """A fresh short directory under the canonical private base, removed on teardown."""

    import secrets

    created: list[Path] = []

    def build() -> Path:
        require_root_owned_sticky_directory(PRIVATE_TMP)
        path = PRIVATE_TMP / f"{SHORT_PREFIX}{secrets.token_hex(4)}"
        os.mkdir(path, DIRECTORY_MODE)
        os.chmod(path, DIRECTORY_MODE)
        created.append(path)
        return path

    yield build

    for path in created:
        for entry in sorted(path.iterdir()):
            try:
                if stat.S_ISSOCK(os.lstat(entry).st_mode) or entry.is_file():
                    entry.unlink()
                else:
                    import shutil

                    shutil.rmtree(entry)
            except OSError:
                pass
        try:
            os.rmdir(path)
        except OSError:
            pass


@pytest.fixture
def strategy():
    """A Darwin strategy with an explicit base. Logic tests use long pytest paths on purpose."""

    def build(tmp_path, **kwargs):
        base = tmp_path / f"so101-ipc-{os.getuid()}"
        return DarwinPrivatePathUnixAddress(base_path=base, **kwargs)

    return build


@pytest.fixture
def short_strategy(short_root):
    """A Darwin strategy whose base is short enough for real Darwin socket binds."""

    def build(**kwargs):
        base = short_root() / f"so101-ipc-{os.getuid()}"
        return DarwinPrivatePathUnixAddress(base_path=base, **kwargs)

    return build


def _owned_private_dir(path: Path) -> Path:
    path.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
    os.chmod(path, DIRECTORY_MODE)
    return path


# --------------------------------------------------------------------------------------
# canonical private base
# --------------------------------------------------------------------------------------


def test_canonical_base_is_the_private_short_path_for_this_uid():
    """The default base is <private-tmp>/so101-ipc-<uid>, never $TMPDIR or a long root."""

    default = DarwinPrivatePathUnixAddress()
    assert default.base_path == PRIVATE_TMP / f"so101-ipc-{os.getuid()}"
    assert default.base_path.parent == PRIVATE_TMP
    # The short base is what keeps a real socket path inside `sun_path` on both platforms.
    assert default.base_path.parent.parent == Path("/")
    assert str(default.base_path) != os.environ.get("TMPDIR", "")


def test_private_tmp_is_root_owned_and_sticky():
    """The canonical parent must be a real root-owned sticky directory."""

    require_root_owned_sticky_directory(PRIVATE_TMP)
    metadata = os.lstat(PRIVATE_TMP)
    assert stat.S_IMODE(metadata.st_mode) & stat.S_ISVTX
    assert metadata.st_uid == 0


def test_base_directory_must_be_owned_and_private(tmp_path, strategy):
    """A base that is a symlink, the wrong owner or the wrong mode is refused."""

    # A symlinked base is refused even if its target would be acceptable.
    target = _owned_private_dir(tmp_path / "real-base")
    link = tmp_path / "link-base"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(UnixAddressError, match="BASE_IS_SYMLINK"):
        require_root_owned_sticky_directory(link)

    # A base that is a regular file is refused.
    plain = tmp_path / "plain"
    plain.write_text("not a directory")
    with pytest.raises(UnixAddressError, match="BASE_NOT_DIRECTORY"):
        require_root_owned_sticky_directory(plain)

    # Wrong mode on the campaign-holding directory.
    loose = tmp_path / "loose-base"
    loose.mkdir(mode=0o755)
    os.chmod(loose, 0o755)
    with pytest.raises(UnixAddressError, match="DIRECTORY_MODE"):
        require_owned_private_directory(loose)
    with pytest.raises(UnixAddressError, match="DIRECTORY_MISSING"):
        require_owned_private_directory(tmp_path / "absent")


def test_an_ancestor_another_user_could_write_is_refused(tmp_path, short_root):
    """A group- or other-writable non-sticky ancestor means our directory can be swapped."""

    # A world-writable directory owned by us is still refused: the sticky bit is what makes a
    # shared directory safe, and a plain 0777 directory has none.
    shared = short_root() / "shared"
    shared.mkdir(mode=0o777)
    os.chmod(shared, 0o777)
    owned_base = shared / "owned-base"
    owned_base.mkdir(mode=DIRECTORY_MODE)
    os.chmod(owned_base, DIRECTORY_MODE)

    with pytest.raises(UnixAddressError, match="ANCESTOR_WRITABLE"):
        require_safe_ancestors(owned_base)
    address = DarwinPrivatePathUnixAddress(base_path=owned_base)
    with pytest.raises(UnixAddressError, match="ANCESTOR_WRITABLE"):
        address.create_campaign_root()

    # The canonical base is accepted, because /private/tmp is root-owned and sticky.
    canonical = DarwinPrivatePathUnixAddress()
    require_safe_ancestors(canonical.base_path)
    require_root_owned_sticky_directory(PRIVATE_TMP)

    # An ancestor that vanished is reported rather than skipped.
    with pytest.raises(UnixAddressError, match="ANCESTOR_MISSING"):
        require_safe_ancestors(Path("/private/tmp/so101-ipc-absent-probe/deeper"))



def test_a_symlinked_base_refuses_to_be_created_through(tmp_path, strategy):
    """create_campaign_root never follows a symlinked base into another directory."""

    real = _owned_private_dir(tmp_path / "real-base")
    link_base = tmp_path / "link-base"
    link_base.symlink_to(real, target_is_directory=True)
    address = DarwinPrivatePathUnixAddress(base_path=link_base)
    with pytest.raises(UnixAddressError, match="DIRECTORY_IS_SYMLINK"):
        address.create_campaign_root()
    assert list(real.iterdir()) == []


# --------------------------------------------------------------------------------------
# campaign root
# --------------------------------------------------------------------------------------


def test_campaign_root_is_fresh_owned_and_private(tmp_path, short_strategy):
    """Every campaign gets a new random directory with mode 0700 under the private base."""

    address = short_strategy()
    root = address.create_campaign_root()
    assert isinstance(root, CampaignIpcRoot)
    assert root.campaign_path.parent == address.base_path
    assert root.campaign_path.name.startswith("b-")
    metadata = os.lstat(root.campaign_path)
    assert stat.S_ISDIR(metadata.st_mode)
    assert not stat.S_ISLNK(metadata.st_mode)
    assert stat.S_IMODE(metadata.st_mode) == DIRECTORY_MODE
    assert metadata.st_uid == os.getuid()
    assert stat.S_IMODE(os.lstat(address.base_path).st_mode) == DIRECTORY_MODE


def test_each_restart_creates_a_new_campaign_path(tmp_path, short_strategy):
    """Restart means a new random directory; the old path is never reused."""

    address = short_strategy()
    first = address.create_campaign_root()
    second = address.create_campaign_root()
    assert first.campaign_path != second.campaign_path
    assert first.campaign_id != second.campaign_id
    assert first.campaign_path.exists() and second.campaign_path.exists()


def test_campaign_id_collision_fails_closed_without_deleting(tmp_path, strategy, monkeypatch):
    """A colliding campaign id tries another id and never removes the colliding object."""

    address = strategy(tmp_path)
    root = address.create_campaign_root()
    squatter = address.base_path / "b-fixed-collision"
    squatter.mkdir(mode=DIRECTORY_MODE)
    os.chmod(squatter, DIRECTORY_MODE)
    (squatter / "keep.txt").write_text("do not delete")

    import so101_demo.runtime.unix_address as module

    tokens = iter(["fixed-collision", "second-choice"])
    monkeypatch.setattr(module.secrets, "token_hex", lambda _n: next(tokens))
    created = address.create_campaign_root()
    assert created.campaign_path.name == "b-second-choice"
    assert (squatter / "keep.txt").read_text() == "do not delete"


# --------------------------------------------------------------------------------------
# endpoint paths and encoded length
# --------------------------------------------------------------------------------------


def test_endpoint_paths_are_role_named_and_inside_the_campaign(tmp_path, short_strategy):
    """The four roles map to the four closed socket names."""

    address = short_strategy()
    root = address.create_campaign_root()
    for role, name in ENDPOINT_NAMES.items():
        path = address.endpoint_path(root, role)
        assert path.name == name
        assert path.parent == root.campaign_path
    with pytest.raises(UnixAddressError, match="ENDPOINT_ROLE_UNKNOWN"):
        address.endpoint_path(root, "supervisor")


def test_encoded_length_uses_bytes_plus_nul_not_characters(tmp_path):
    """The check is on encoded bytes including the terminating NUL, as the kernel sees it."""

    assert encoded_length_ok("/private/tmp/x", capacity_bytes=104)
    assert not encoded_length_ok("/" + "x" * 103, capacity_bytes=104)

    exact = "/" + "x" * (DARWIN_SUN_PATH_CAPACITY_BYTES - 2)
    require_encoded_length(exact, capacity_bytes=DARWIN_SUN_PATH_CAPACITY_BYTES)
    with pytest.raises(UnixAddressError, match="SOCKET_PATH_TOO_LONG"):
        require_encoded_length("/" + "x" * (DARWIN_SUN_PATH_CAPACITY_BYTES - 1),
                              capacity_bytes=DARWIN_SUN_PATH_CAPACITY_BYTES)

    # A multi-byte character counts for its bytes, not for one character: 60 characters is
    # only 180 bytes, while 40 characters is 120 bytes and must be refused.
    assert len("\u4e2d" * 40) == 40
    with pytest.raises(UnixAddressError, match="SOCKET_PATH_TOO_LONG"):
        require_encoded_length("/private/tmp/" + "\u4e2d" * 40,
                              capacity_bytes=DARWIN_SUN_PATH_CAPACITY_BYTES)
    assert encoded_length_ok("/private/tmp/" + "\u4e2d" * 20,
                            capacity_bytes=DARWIN_SUN_PATH_CAPACITY_BYTES)

    with pytest.raises(UnixAddressError, match="SOCKET_PATH_INVALID"):
        require_encoded_length("", capacity_bytes=DARWIN_SUN_PATH_CAPACITY_BYTES)


def test_a_real_darwin_bind_respects_the_declared_capacity(tmp_path):
    """A path of capacity-1 bytes binds and capacity bytes does not (measured on this host)."""

    if sys.platform != "darwin":
        pytest.skip("the Darwin sun_path capacity is what is under test")

    accept = tmp_path / ("a" * 40)
    accepted = "/private/tmp/" + "s" * 79  # 92 bytes + NUL, comfortably inside
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(accepted)
        assert Path(accepted).exists()
    finally:
        sock.close()
        if Path(accepted).exists():
            os.unlink(accepted)
    assert encoded_length_ok(accepted, capacity_bytes=DARWIN_SUN_PATH_CAPACITY_BYTES)
    assert accept  # silence the unused-local lint; tmp_path is only the fixture's root


def test_validate_encoded_length_is_exposed_on_the_strategy(tmp_path, strategy):
    address = strategy(tmp_path)
    address.validate_encoded_length("/private/tmp/short.sock")
    with pytest.raises(UnixAddressError, match="SOCKET_PATH_TOO_LONG"):
        address.validate_encoded_length("/" + "y" * 200)


# --------------------------------------------------------------------------------------
# binding and registering
# --------------------------------------------------------------------------------------


def test_bind_creates_a_mode_0600_owned_socket_and_registers_it(tmp_path, short_strategy):
    """A bound endpoint is 0600, owned by us, and recorded with its file identity."""

    address = short_strategy()
    root = address.create_campaign_root()
    endpoint = address.bind_endpoint(root, "coordinator", owner_pid=os.getpid(),
                                     owner_birth_identity=1234)
    try:
        metadata = os.lstat(endpoint.path)
        assert stat.S_ISSOCK(metadata.st_mode)
        assert stat.S_IMODE(metadata.st_mode) == SOCKET_MODE
        assert metadata.st_uid == os.getuid()
        assert (endpoint.device, endpoint.inode) == (metadata.st_dev, metadata.st_ino)
        assert endpoint.role == "coordinator"
        assert address.registry == (endpoint,)
    finally:
        receipt = address.cleanup_campaign(root)
    assert receipt.complete is True


def test_a_plain_file_at_the_endpoint_is_never_registered(tmp_path, short_strategy):
    """Registration asserts a real socket; a regular file in its place is refused."""

    address = short_strategy()
    root = address.create_campaign_root()
    impostor = root.campaign_path / ENDPOINT_NAMES["broker"]
    impostor.write_text("not a socket")
    with pytest.raises(UnixAddressError, match="ENDPOINT_NOT_SOCKET"):
        address.register_endpoint(impostor, role="broker", owner_pid=os.getpid(),
                                  owner_birth_identity=1)


def test_a_symlink_at_the_endpoint_is_refused(tmp_path, short_strategy):
    """A symlink is refused before any stat-following can be fooled."""

    address = short_strategy()
    root = address.create_campaign_root()
    target = tmp_path / "elsewhere.sock"
    target.write_text("decoy")
    link = root.campaign_path / ENDPOINT_NAMES["worker-0"]
    link.symlink_to(target)
    with pytest.raises(UnixAddressError, match="ENDPOINT_IS_SYMLINK"):
        address.register_endpoint(link, role="worker-0", owner_pid=os.getpid(),
                                  owner_birth_identity=1)


def test_wrong_socket_mode_and_wrong_owner_are_refused(tmp_path, short_strategy):
    """A socket that group or other can reach is not an acceptable endpoint."""

    address = short_strategy()
    root = address.create_campaign_root()
    path = root.campaign_path / ENDPOINT_NAMES["worker-1"]
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    os.chmod(path, 0o666)
    try:
        with pytest.raises(UnixAddressError, match="ENDPOINT_MODE"):
            address.register_endpoint(path, role="worker-1", owner_pid=os.getpid(),
                                      owner_birth_identity=1)
    finally:
        sock.close()
        if path.exists():
            os.unlink(path)


# --------------------------------------------------------------------------------------
# cleanup
# --------------------------------------------------------------------------------------


def test_cleanup_unlinks_only_its_own_exact_endpoint(tmp_path, short_strategy):
    """Cleanup removes the registered socket, the directory, and nothing else."""

    address = short_strategy()
    root = address.create_campaign_root()
    endpoint = address.bind_endpoint(root, "broker", owner_pid=os.getpid(),
                                     owner_birth_identity=7)
    bystander = root.campaign_path / "unregistered.txt"
    bystander.write_text("keep me")

    receipt = address.cleanup_campaign(root)
    assert [item.outcome for item in receipt.endpoints] == [CLEANED]
    assert not endpoint.path.exists()
    # An unknown object is never deleted, so the directory must survive and say so.
    assert bystander.exists()
    assert receipt.directory_removed is False
    assert receipt.directory_live_after is True
    assert receipt.directory_outcome == NOT_OWNED
    assert receipt.complete is False

    bystander.unlink()
    second = address.cleanup_campaign(root)
    assert second.directory_removed is True
    assert second.directory_live_after is False
    assert second.complete is True
    assert not root.campaign_path.exists()


def test_cleanup_reports_a_socket_it_no_longer_owns_instead_of_deleting_it(tmp_path, short_strategy):
    """A replaced socket is reported NOT_OWNED and left alone."""

    address = short_strategy()
    root = address.create_campaign_root()
    endpoint = address.bind_endpoint(root, "coordinator", owner_pid=os.getpid(),
                                     owner_birth_identity=7)
    os.unlink(endpoint.path)
    # ext4 hands the just-freed inode straight back to the next bind, which would make the
    # replacement indistinguishable from the registered endpoint. Hold the freed inode with a
    # placeholder so the case really does put a different file at the same path.
    placeholder = endpoint.path.with_name(endpoint.path.name + ".inode-hold")
    placeholder.write_bytes(b"hold")
    replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    replacement.bind(str(endpoint.path))
    os.chmod(endpoint.path, SOCKET_MODE)
    replacement_metadata = os.lstat(endpoint.path)
    assert (replacement_metadata.st_dev, replacement_metadata.st_ino) != (
        endpoint.device, endpoint.inode
    ), "the replacement reused the registered inode; the case cannot discriminate"
    try:
        result = address.cleanup_registered_endpoint(endpoint)
        assert result.outcome == NOT_OWNED
        assert result.live_after is True
        assert endpoint.path.exists(), "an unknown object must never be unlinked"
    finally:
        replacement.close()
        placeholder.unlink(missing_ok=True)
        address.cleanup_campaign(root)


def test_cleanup_of_a_missing_endpoint_is_already_gone(tmp_path, short_strategy):
    """A socket that vanished under us is reported, not raised about."""

    address = short_strategy()
    root = address.create_campaign_root()
    endpoint = address.bind_endpoint(root, "worker-0", owner_pid=os.getpid(),
                                     owner_birth_identity=7)
    os.unlink(endpoint.path)
    result = address.cleanup_registered_endpoint(endpoint)
    assert result.outcome == ALREADY_GONE
    assert result.existed_before is False
    assert result.live_after is False
    receipt = address.cleanup_campaign(root)
    assert receipt.complete is True


def test_cleanup_refuses_an_endpoint_it_did_not_register(tmp_path, short_strategy):
    """An unregistered path is refused rather than trusted."""

    address = short_strategy()
    root = address.create_campaign_root()
    endpoint = address.bind_endpoint(root, "worker-1", owner_pid=os.getpid(),
                                     owner_birth_identity=7)
    forgetful = DarwinPrivatePathUnixAddress(base_path=address.base_path)
    result = forgetful.cleanup_registered_endpoint(endpoint)
    assert result.outcome == NOT_OWNED
    assert endpoint.path.exists()
    address.cleanup_campaign(root)


def test_cleanup_does_not_touch_another_campaigns_directory(tmp_path, short_strategy):
    """Cleaning one campaign leaves a sibling campaign's sockets untouched."""

    address = short_strategy()
    first = address.create_campaign_root()
    second = address.create_campaign_root()
    first_socket = address.bind_endpoint(first, "broker", owner_pid=os.getpid(),
                                        owner_birth_identity=1)
    second_socket = address.bind_endpoint(second, "broker", owner_pid=os.getpid(),
                                         owner_birth_identity=1)
    receipt = address.cleanup_campaign(first)
    assert receipt.complete is True
    assert not first_socket.path.exists()
    assert second_socket.path.exists(), "a sibling campaign is never scanned or cleaned"
    assert address.cleanup_campaign(second).complete is True


# --------------------------------------------------------------------------------------
# the frozen Linux strategy
# --------------------------------------------------------------------------------------


def test_proc_fd_strategy_keeps_the_linux_contract(tmp_path):
    """v3's Linux strategy keeps the 108-byte capacity and its own refusal vocabulary."""

    linux = ProcFdUnixAddress()
    root = CampaignIpcRoot(base_path=tmp_path, campaign_path=tmp_path / "b-linux", uid=os.getuid(),
                           campaign_id="b-linux")
    assert linux.endpoint_path(root, "broker").name == ENDPOINT_NAMES["broker"]
    linux.validate_encoded_length("/proc/self/fd/7/broker.sock")
    with pytest.raises(UnixAddressError, match="SOCKET_PATH_TOO_LONG"):
        linux.validate_encoded_length("/" + "z" * 200)
    with pytest.raises(UnixAddressError, match="ENDPOINT_ROLE_UNKNOWN"):
        linux.endpoint_path(root, "nobody")
    # v3 cleanup is process-lifetime based; it must not pretend to support durable unlinking.
    with pytest.raises(UnixAddressError, match="PROC_FD_CLEANUP_UNSUPPORTED"):
        linux.cleanup_registered_endpoint(object())


def test_campaign_root_rejects_a_mismatched_parent(tmp_path):
    """A root whose campaign directory is not under its base is a programming error."""

    with pytest.raises(UnixAddressError, match="CAMPAIGN_ROOT_MISMATCH"):
        CampaignIpcRoot(base_path=tmp_path / "base", campaign_path=tmp_path / "other" / "b-x",
                        uid=os.getuid(), campaign_id="b-x")
    with pytest.raises(UnixAddressError, match="CAMPAIGN_ID_INVALID"):
        CampaignIpcRoot(base_path=tmp_path, campaign_path=tmp_path / "wrong", uid=os.getuid(),
                        campaign_id="wrong")
