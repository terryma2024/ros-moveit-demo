"""Fixture-only checks of scripts/images/image_content_manifest.py on synthetic layer tars built here."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

TOOL = Path(__file__).resolve().parents[1] / "images" / "image_content_manifest.py"
SHIPPED_EXCLUSIONS = TOOL.parent / "image-content-exclusions.txt"
spec = importlib.util.spec_from_file_location("image_content_manifest", TOOL)
icm = importlib.util.module_from_spec(spec)
sys.modules["image_content_manifest"] = icm
spec.loader.exec_module(icm)

EXCLUSIONS = "/var/log/** | logs vary | 2026-10-21\n/tmp/** | temp files vary | 2026-10-21\n"


# --- fixture builders -------------------------------------------------------------------------------------------------

def f(path, data=b"", mode=0o644, uid=0, gid=0, mtime=0):
    return ("file", path, data, mode, uid, gid, mtime, None)


def d(path, mode=0o755, mtime=0):
    return ("dir", path, b"", mode, 0, 0, mtime, None)


def sym(path, target):
    return ("symlink", path, b"", 0o777, 0, 0, 0, target)


def hard(path, target):
    return ("hardlink", path, b"", 0o644, 0, 0, 0, target)


def dev(path, kind, major, minor):
    return (kind, path, b"", 0o600, 0, 0, 0, (major, minor))


def wh(path):
    parent, _, name = path.rpartition("/")
    return f(f"{parent}/.wh.{name}")


def opaque(directory):
    return f(f"{directory}/.wh..wh..opq")


def layer_tar(members, compress=False):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for kind, path, data, mode, uid, gid, mtime, extra in members:
            info = tarfile.TarInfo(path.lstrip("/"))
            info.mode, info.uid, info.gid, info.mtime = mode, uid, gid, mtime
            if kind == "file":
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
                continue
            info.type = {"dir": tarfile.DIRTYPE, "symlink": tarfile.SYMTYPE, "hardlink": tarfile.LNKTYPE,
                         "char": tarfile.CHRTYPE, "block": tarfile.BLKTYPE, "fifo": tarfile.FIFOTYPE}[kind]
            if kind in ("symlink", "hardlink"):
                info.linkname = extra
            if kind in ("char", "block"):
                info.devmajor, info.devminor = extra
            tar.addfile(info)
    data = buffer.getvalue()
    return gzip.compress(data, mtime=0) if compress else data


def add_bytes(tar, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


CONFIG = {"architecture": "amd64", "config": {"Env": ["A=1"], "Cmd": ["/bin/sh"], "WorkingDir": "/act", "User": "1000",
                                               "Labels": {"k": "v"}, "Ignored": 1}}


def docker_archive(layers, compress=None, config=CONFIG, order=None):
    """`layers` are member lists; layer blobs are plain unless compress[i]."""
    compress = compress or [False] * len(layers)
    blobs = [layer_tar(members, compress[i]) for i, members in enumerate(layers)]
    names = [f"{hashlib.sha256(blob).hexdigest()}/layer.tar" for blob in blobs]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for index in (order or range(len(blobs))):
            add_bytes(tar, names[index], blobs[index])
        add_bytes(tar, "abc.json", json.dumps(config).encode())
        add_bytes(tar, "manifest.json", json.dumps([{"Config": "abc.json", "RepoTags": ["t:1"], "Layers": names}]).encode())
        add_bytes(tar, "repositories", b'{"t":{"1":"x"}}')
    return buffer.getvalue()


def oci_archive(layers, compress=None, config=CONFIG):
    compress = compress or [False] * len(layers)
    blobs = [layer_tar(members, compress[i]) for i, members in enumerate(layers)]
    digests = ["sha256:" + hashlib.sha256(blob).hexdigest() for blob in blobs]
    config_bytes = json.dumps(config).encode()
    config_digest = "sha256:" + hashlib.sha256(config_bytes).hexdigest()
    manifest = json.dumps({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                           "config": {"digest": config_digest, "size": len(config_bytes)},
                           "layers": [{"digest": digest, "size": 1} for digest in digests]}).encode()
    manifest_digest = "sha256:" + hashlib.sha256(manifest).hexdigest()
    attestation = b'{"schemaVersion":2,"config":{"digest":"sha256:00"},"layers":[]}'
    index = json.dumps({"schemaVersion": 2, "manifests": [
        {"digest": manifest_digest, "mediaType": "application/vnd.oci.image.manifest.v1+json",
         "platform": {"os": "linux", "architecture": "amd64"}},
        {"digest": "sha256:" + hashlib.sha256(attestation).hexdigest(), "platform": {"os": "unknown", "architecture": "unknown"}}]}).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for digest, blob in zip(digests, blobs):
            add_bytes(tar, "blobs/sha256/" + digest.split(":")[1], blob)
        add_bytes(tar, "blobs/sha256/" + config_digest.split(":")[1], config_bytes)
        add_bytes(tar, "blobs/sha256/" + manifest_digest.split(":")[1], manifest)
        add_bytes(tar, "oci-layout", b'{"imageLayoutVersion":"1.0.0"}')
        add_bytes(tar, "index.json", index)
    return buffer.getvalue()


@pytest.fixture
def exclusions(tmp_path):
    path = tmp_path / "exclusions.txt"
    path.write_text(EXCLUSIONS)
    return path


def run_manifest(tmp_path, archive, exclusions, name="m.json"):
    tar_path = tmp_path / (name + ".tar")
    tar_path.write_bytes(archive)
    out = tmp_path / name
    code = icm.main(["manifest", str(tar_path), "--exclusions", str(exclusions), "--output", str(out)])
    assert code == 0
    return json.loads(out.read_bytes()), out


def entries(archive, exclusions, tmp_path):
    return run_manifest(tmp_path, archive, exclusions)[0]["content"]["entries"]


# --- merge rules ------------------------------------------------------------------------------------------------------

def test_a_later_layer_replaces_an_earlier_file(tmp_path, exclusions):
    result = entries(docker_archive([[d("/etc"), f("/etc/a", b"one")], [f("/etc/a", b"two!", mode=0o600)]]), exclusions, tmp_path)
    assert result["/etc/a"] == {"type": "file", "mode": "0600", "uid": 0, "gid": 0, "size": 4,
                                "sha256": hashlib.sha256(b"two!").hexdigest()}


def test_a_whiteout_removes_a_file_and_a_nested_subtree(tmp_path, exclusions):
    lower = [d("/opt"), d("/opt/x"), d("/opt/x/y"), f("/opt/x/y/deep", b"1"), f("/opt/x/top", b"2"), f("/opt/keep", b"3"),
             f("/etc-file", b"4")]
    result = entries(docker_archive([lower, [wh("/opt/x"), wh("/etc-file")]]), exclusions, tmp_path)
    assert set(result) == {"/opt", "/opt/keep"}


def test_a_whiteout_does_not_remove_a_sibling_with_the_same_prefix(tmp_path, exclusions):
    result = entries(docker_archive([[d("/opt"), d("/opt/x"), d("/opt/xy"), f("/opt/xy/a", b"1")], [wh("/opt/x")]]), exclusions, tmp_path)
    assert "/opt/xy/a" in result and "/opt/x" not in result


def test_an_opaque_directory_clears_the_lower_content_but_keeps_its_own(tmp_path, exclusions):
    lower = [d("/srv"), f("/srv/old", b"1"), d("/srv/sub"), f("/srv/sub/old2", b"2")]
    upper = [d("/srv"), opaque("/srv"), f("/srv/new", b"3")]
    result = entries(docker_archive([lower, upper]), exclusions, tmp_path)
    assert set(result) == {"/srv", "/srv/new"}


def test_a_type_change_replaces_the_entry_and_drops_old_children(tmp_path, exclusions):
    lower = [d("/a"), f("/a/child", b"1"), sym("/b", "/x"), f("/c", b"1")]
    upper = [f("/a", b"now a file"), d("/b"), sym("/c", "/target")]
    result = entries(docker_archive([lower, upper]), exclusions, tmp_path)
    assert result["/a"]["type"] == "file" and "/a/child" not in result
    assert result["/b"]["type"] == "dir"
    assert result["/c"]["type"] == "symlink" and result["/c"]["link"] == "/target" and "sha256" not in result["/c"]


def test_a_hard_link_resolves_to_its_target_in_the_same_and_in_a_lower_layer(tmp_path, exclusions):
    lower = [f("/bin/tool", b"binary", mode=0o755), hard("/bin/alias", "bin/tool")]
    upper = [hard("/bin/later", "bin/tool"), hard("/bin/chain", "bin/later")]
    result = entries(docker_archive([lower, upper]), exclusions, tmp_path)
    digest = hashlib.sha256(b"binary").hexdigest()
    for name in ("alias", "later", "chain"):
        entry = result[f"/bin/{name}"]
        assert (entry["type"], entry["size"], entry["sha256"], entry["mode"]) == ("hardlink", 6, digest, "0755")
    assert result["/bin/chain"]["target"] == "/bin/later"


def test_a_hard_link_keeps_the_content_it_had_when_the_target_is_replaced_later(tmp_path, exclusions):
    lower = [f("/bin/tool", b"old"), hard("/bin/alias", "bin/tool")]
    result = entries(docker_archive([lower, [f("/bin/tool", b"newer")]]), exclusions, tmp_path)
    assert result["/bin/alias"]["sha256"] == hashlib.sha256(b"old").hexdigest()
    assert result["/bin/tool"]["sha256"] == hashlib.sha256(b"newer").hexdigest()


def test_a_dangling_hard_link_is_refused_with_a_named_error(tmp_path, exclusions, capsys):
    archive = tmp_path / "a.tar"
    archive.write_bytes(docker_archive([[hard("/bin/alias", "bin/nothing")]]))
    code = icm.main(["manifest", str(archive), "--exclusions", str(exclusions), "--output", str(tmp_path / "o.json")])
    assert code == 2 and "DanglingHardlinkError" in capsys.readouterr().err


def test_symlinks_devices_fifos_and_directories_are_recorded(tmp_path, exclusions):
    layer = [d("/dev", mode=0o755), dev("/dev/null", "char", 1, 3), dev("/dev/loop0", "block", 7, 0),
             ("fifo", "/run/pipe", b"", 0o600, 0, 0, 0, None), sym("/bin", "usr/bin"), d("/run")]
    result = entries(docker_archive([layer]), exclusions, tmp_path)
    assert result["/dev/null"] == {"type": "char", "mode": "0600", "uid": 0, "gid": 0, "major": 1, "minor": 3}
    assert (result["/dev/loop0"]["type"], result["/dev/loop0"]["major"], result["/dev/loop0"]["minor"]) == ("block", 7, 0)
    assert result["/run/pipe"]["type"] == "fifo"
    assert result["/bin"] == {"type": "symlink", "mode": "0777", "uid": 0, "gid": 0, "link": "usr/bin"}
    assert result["/dev"]["type"] == "dir"


# --- layouts ----------------------------------------------------------------------------------------------------------

LAYERS = [[d("/etc"), f("/etc/a", b"1"), f("/etc/gone", b"x")], [f("/etc/b", b"2"), wh("/etc/gone")]]


def test_both_archive_layouts_and_compression_give_the_same_manifest(tmp_path, exclusions):
    results = []
    for number, archive in enumerate([docker_archive(LAYERS), docker_archive(LAYERS, [True, False]),
                                      docker_archive(LAYERS, [True, True]), oci_archive(LAYERS), oci_archive(LAYERS, [False, True])]):
        manifest, _ = run_manifest(tmp_path, archive, exclusions, f"m{number}.json")
        results.append(manifest["content_sha256"])
        assert set(manifest["content"]["entries"]) == {"/etc", "/etc/a", "/etc/b"}
    assert len(set(results)) == 1


def test_the_layer_blobs_may_come_after_the_manifest_in_the_tar(tmp_path, exclusions):
    # The reader makes one pass, so a layer is summarized before the manifest says it is one.
    one, _ = run_manifest(tmp_path, docker_archive(LAYERS), exclusions, "a.json")
    two, _ = run_manifest(tmp_path, docker_archive(LAYERS, order=[1, 0]), exclusions, "b.json")
    assert one["content_sha256"] == two["content_sha256"]


def test_the_config_subset_is_recorded_and_other_fields_are_not(tmp_path, exclusions):
    config = run_manifest(tmp_path, docker_archive(LAYERS), exclusions)[0]["content"]["config"]
    assert set(config) == set(icm.CONFIG_FIELDS)
    assert config["Env"] == ["A=1"] and config["WorkingDir"] == "/act" and config["Labels"] == {"k": "v"} and config["Shell"] is None


def test_the_manifest_is_read_from_stdin(tmp_path, exclusions):
    out = tmp_path / "stdin.json"
    done = subprocess.run([sys.executable, "-I", str(TOOL), "manifest", "-", "--exclusions", str(exclusions), "--output", str(out)],
                          input=docker_archive(LAYERS), capture_output=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.decode().strip() == json.loads(out.read_bytes())["content_sha256"]
    assert b"entries=3" in done.stderr


# --- canonical bytes --------------------------------------------------------------------------------------------------

def test_the_hash_does_not_depend_on_tar_member_order_or_mtime(tmp_path, exclusions):
    one = [d("/a"), f("/a/x", b"1", mtime=100), f("/a/y", b"2", mtime=200), sym("/a/z", "x")]
    two = [sym("/a/z", "x"), f("/a/y", b"2", mtime=999999), d("/a", mtime=5), f("/a/x", b"1", mtime=1234567)]
    first = run_manifest(tmp_path, docker_archive([one]), exclusions, "one.json")
    second = run_manifest(tmp_path, docker_archive([two]), exclusions, "two.json")
    assert first[0]["content_sha256"] == second[0]["content_sha256"]
    assert first[1].read_bytes() == second[1].read_bytes()


def test_the_content_sha256_is_the_sha256_of_the_canonical_content_bytes(tmp_path, exclusions):
    manifest, path = run_manifest(tmp_path, docker_archive(LAYERS), exclusions)
    content = json.dumps(manifest["content"], sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(content).hexdigest() == manifest["content_sha256"]
    assert icm.load_manifest(path)["content_sha256"] == manifest["content_sha256"]
    assert b"mtime" not in path.read_bytes()


def test_floats_are_refused_in_canonical_bytes():
    with pytest.raises(icm.ImageManifestError):
        icm.canonical_bytes({"a": 1.5})


def test_different_content_gives_a_different_hash(tmp_path, exclusions):
    first = run_manifest(tmp_path, docker_archive([[f("/a", b"1")]]), exclusions, "1.json")[0]["content_sha256"]
    second = run_manifest(tmp_path, docker_archive([[f("/a", b"2")]]), exclusions, "2.json")[0]["content_sha256"]
    third = run_manifest(tmp_path, docker_archive([[f("/a", b"1", mode=0o600)]]), exclusions, "3.json")[0]["content_sha256"]
    assert len({first, second, third}) == 3


def test_a_tampered_manifest_is_refused(tmp_path, exclusions, capsys):
    _, path = run_manifest(tmp_path, docker_archive(LAYERS), exclusions)
    path.write_bytes(path.read_bytes().replace(b'"/etc/a"', b'"/etc/z"'))
    assert icm.main(["diff", str(path), str(path)]) == 2
    assert "ManifestIntegrityError" in capsys.readouterr().err


# --- exclusions -------------------------------------------------------------------------------------------------------

def test_excluded_paths_leave_the_hash_and_are_listed_with_rule_and_hash(tmp_path, exclusions):
    base = [d("/var"), d("/var/log"), d("/tmp"), f("/etc/a", b"1")]
    with_logs = base + [f("/var/log/apt.log", b"run one"), f("/tmp/x", b"1"), d("/tmp/sub")]
    other_logs = base + [f("/var/log/apt.log", b"run TWO"), f("/var/log/extra", b"y")]
    first, _ = run_manifest(tmp_path, docker_archive([with_logs]), exclusions, "a.json")
    second, _ = run_manifest(tmp_path, docker_archive([other_logs]), exclusions, "b.json")
    assert first["content_sha256"] == second["content_sha256"]
    assert set(first["content"]["entries"]) == {"/var", "/var/log", "/tmp", "/etc/a"}
    listed = first["excluded"]["entries"]
    assert set(listed) == {"/var/log/apt.log", "/tmp/x", "/tmp/sub"}
    assert listed["/var/log/apt.log"]["rule"] == "/var/log/**"
    expected = {"type": "file", "mode": "0644", "uid": 0, "gid": 0, "size": 7, "sha256": hashlib.sha256(b"run one").hexdigest()}
    assert listed["/var/log/apt.log"]["entry_sha256"] == hashlib.sha256(icm.canonical_bytes(expected)).hexdigest()
    assert first["excluded"]["counts_by_rule"] == {"/var/log/**": 1, "/tmp/**": 2}
    assert second["excluded"]["entries"]["/var/log/apt.log"]["entry_sha256"] != listed["/var/log/apt.log"]["entry_sha256"]


def test_a_changed_exclusion_set_changes_the_hash(tmp_path, exclusions):
    archive = docker_archive(LAYERS)
    other = tmp_path / "other.txt"
    other.write_text("/tmp/** | temp | 2026-10-21\n")
    assert run_manifest(tmp_path, archive, exclusions, "1.json")[0]["content_sha256"] != \
        run_manifest(tmp_path, archive, other, "2.json")[0]["content_sha256"]


def test_the_shipped_exclusion_list_loads_and_has_the_five_initial_rules():
    rules = icm.load_exclusions(SHIPPED_EXCLUSIONS)
    assert [r["glob"] for r in rules] == ["/var/log/**", "/var/cache/**", "/var/lib/apt/lists/**", "/tmp/**", "/root/.cache/**"]
    assert all(r["added"] == "2026-10-21" and r["reason"] for r in rules)


@pytest.mark.parametrize("glob", ["/act/**", "/act/venv/lib/**", "/opt/ros/**", "/opt/ros/jazzy/lib/*.so", "/usr/lib/**",
                                  "/usr/lib/python3/*.pyc", "/usr/bin/*", "/usr/bin/python3", "/**", "/*", "/**/site-packages/**",
                                  "/a*/venv/**", "/usr/**", "/act", "/opt/ros", "/usr/lib"])
def test_a_rule_that_could_reach_a_protected_tree_is_refused(tmp_path, glob):
    path = tmp_path / "x.txt"
    path.write_text(f"{glob} | no | 2026-10-21\n")
    with pytest.raises(icm.ExclusionError, match="protected tree"):
        icm.load_exclusions(path)


@pytest.mark.parametrize("glob", ["/var/log/**", "/tmp/**", "/root/.cache/**", "/usr/share/doc/**", "/usr/local/**", "/opt/other/**",
                                  "/actual/**", "/usr/libexec/**", "/var/cache/**"])
def test_a_rule_elsewhere_is_accepted(tmp_path, glob):
    path = tmp_path / "x.txt"
    path.write_text(f"{glob} | fine | 2026-10-21\n")
    assert icm.load_exclusions(path)[0]["glob"] == glob


@pytest.mark.parametrize("line", ["/tmp/**", "/tmp/** | reason", "/tmp/** | reason | 21-10-2026", "tmp/** | reason | 2026-10-21",
                                  "/tmp/** |  | 2026-10-21"])
def test_a_malformed_exclusion_line_is_refused(tmp_path, line):
    path = tmp_path / "x.txt"
    path.write_text(line + "\n")
    with pytest.raises(icm.ExclusionError):
        icm.load_exclusions(path)


def test_the_protected_tree_guard_runs_before_any_archive_is_read(tmp_path, capsys):
    bad = tmp_path / "bad.txt"
    bad.write_text("/act/venv/** | oops | 2026-10-21\n")
    code = icm.main(["manifest", str(tmp_path / "missing.tar"), "--exclusions", str(bad), "--output", str(tmp_path / "o.json")])
    assert code == 2 and "ExclusionError" in capsys.readouterr().err


# --- malformed input --------------------------------------------------------------------------------------------------

def test_a_non_tar_input_is_refused_with_a_named_error(tmp_path, exclusions, capsys):
    archive = tmp_path / "bad.tar"
    archive.write_bytes(b"this is not a tar archive at all" * 100)
    code = icm.main(["manifest", str(archive), "--exclusions", str(exclusions), "--output", str(tmp_path / "o.json")])
    assert code == 2
    assert "error: ArchiveFormatError" in capsys.readouterr().err
    assert not (tmp_path / "o.json").exists()


def test_a_tar_without_a_manifest_is_refused_with_a_named_error(tmp_path, exclusions, capsys):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        add_bytes(tar, "random.txt", b"hello")
    archive = tmp_path / "bad.tar"
    archive.write_bytes(buffer.getvalue())
    assert icm.main(["manifest", str(archive), "--exclusions", str(exclusions), "--output", str(tmp_path / "o.json")]) == 2
    assert "error: ArchiveFormatError" in capsys.readouterr().err


def test_a_missing_layer_and_a_damaged_layer_are_refused(tmp_path, exclusions, capsys):
    good = docker_archive(LAYERS)
    with tarfile.open(fileobj=io.BytesIO(good)) as tar:
        members = {m.name: tar.extractfile(m).read() for m in tar.getmembers()}
    layer_name = json.loads(members["manifest.json"])[0]["Layers"][0]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, data in members.items():
            if name != layer_name:
                add_bytes(tar, name, data)
    (tmp_path / "missing.tar").write_bytes(buffer.getvalue())
    assert icm.main(["manifest", str(tmp_path / "missing.tar"), "--exclusions", str(exclusions), "--output", str(tmp_path / "o")]) == 2
    assert "MissingBlobError" in capsys.readouterr().err
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, data in members.items():
            add_bytes(tar, name, gzip.compress(b"x" * 5000)[:40] if name == layer_name else data)
    (tmp_path / "damaged.tar").write_bytes(buffer.getvalue())
    assert icm.main(["manifest", str(tmp_path / "damaged.tar"), "--exclusions", str(exclusions), "--output", str(tmp_path / "o")]) == 2
    assert "LayerParseError" in capsys.readouterr().err


def test_an_archive_with_two_images_is_refused(tmp_path, exclusions, capsys):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        add_bytes(tar, "manifest.json", json.dumps([{"Config": "a", "Layers": []}, {"Config": "b", "Layers": []}]).encode())
    (tmp_path / "two.tar").write_bytes(buffer.getvalue())
    assert icm.main(["manifest", str(tmp_path / "two.tar"), "--exclusions", str(exclusions), "--output", str(tmp_path / "o")]) == 2
    assert "AmbiguousImageError" in capsys.readouterr().err


# --- diff -------------------------------------------------------------------------------------------------------------

def package_layers(version):
    dpkg_list = b"/.\n/usr\n/usr/lib\n/usr/lib/libfoo.so\n/usr/share/foo/data\n"
    record = b"foo/__init__.py,sha256=aa,10\nfoo-1.0.dist-info/RECORD,,\n"
    site = "/act/venv/lib/python3.12/site-packages"
    return [[d("/var/lib/dpkg/info"), f("/var/lib/dpkg/info/libfoo:amd64.list", dpkg_list), d("/usr/lib"), d("/usr/share/foo"),
             f("/usr/lib/libfoo.so", b"lib " + version), f("/usr/share/foo/data", b"data"), f("/usr/share/other", b"same"),
             d(f"{site}/foo-1.0.dist-info"), d(f"{site}/foo"),
             f(f"{site}/foo-1.0.dist-info/RECORD", record),
             f(f"{site}/foo/__init__.py", b"code " + version),
             f("/opt/unowned", b"u" + version)]]


def test_diff_lists_paths_groups_them_and_attributes_dpkg_and_pip(tmp_path, exclusions, capsys):
    _, a = run_manifest(tmp_path, docker_archive(package_layers(b"1")), exclusions, "a.json")
    _, b = run_manifest(tmp_path, docker_archive(package_layers(b"2") + [[f("/etc/new", b"n")]]), exclusions, "b.json")
    capsys.readouterr()
    assert icm.main(["diff", str(a), str(b)]) == 1
    out = capsys.readouterr().out
    assert "== /usr (1 differing) ==" in out and "== /act (1 differing) ==" in out and "== /etc (1 differing) ==" in out
    assert "M /usr/lib/libfoo.so  [dpkg:libfoo:amd64]" in out
    assert "M /act/venv/lib/python3.12/site-packages/foo/__init__.py  [pip:foo-1.0]" in out
    assert "M /opt/unowned\n" in out and "+ /etc/new" in out
    assert "A: " in out and "B: " in out and "(absent)" in out
    assert "/usr/share/other" not in out and "/usr/share/foo/data" not in out
    assert "dpkg:libfoo:amd64" in out.split("== by package ==")[1]


def test_diff_of_equal_manifests_is_empty_and_exits_zero(tmp_path, exclusions, capsys):
    _, a = run_manifest(tmp_path, docker_archive(LAYERS), exclusions, "a.json")
    _, b = run_manifest(tmp_path, docker_archive(LAYERS, [True, True]), exclusions, "b.json")
    capsys.readouterr()
    assert icm.main(["diff", str(a), str(b)]) == 0
    assert "differing=0" in capsys.readouterr().out


def test_diff_reports_config_changes(tmp_path, exclusions, capsys):
    other = {"config": {**CONFIG["config"], "Env": ["A=2"]}}
    _, a = run_manifest(tmp_path, docker_archive(LAYERS), exclusions, "a.json")
    _, b = run_manifest(tmp_path, docker_archive(LAYERS, config=other), exclusions, "b.json")
    capsys.readouterr()
    assert icm.main(["diff", str(a), str(b)]) == 1
    assert "== image config ==" in capsys.readouterr().out


# --- check-no-pyc -----------------------------------------------------------------------------------------------------

def pyc_layers():
    base = [d("/usr/lib/python3/dist-packages"), f("/usr/lib/python3/site-packages/old.pyc", b"1")]
    ours = [f("/usr/lib/python3/site-packages/new.pyc", b"2"), f("/usr/lib/python3/site-packages/mod.py", b"3"),
            f("/opt/venv/lib/site-packages/x/y.pyc", b"4"), f("/act/source/pkg/mod.cpython-312.pyc", b"5"),
            f("/act/venv/lib/python3.12/site-packages/z.pyc", b"6")]
    return base, ours


def test_check_no_pyc_without_a_base_flags_act_and_every_site_packages_pyc(tmp_path, exclusions, capsys):
    base, ours = pyc_layers()
    _, manifest = run_manifest(tmp_path, docker_archive([base, ours]), exclusions)
    capsys.readouterr()
    assert icm.main(["check-no-pyc", str(manifest)]) == 1
    out = capsys.readouterr().out
    assert "pyc_under_act=2 pyc_under_act_venv=1 pyc_site_packages_added=3" in out
    assert "pyc: /usr/lib/python3/site-packages/old.pyc" in out


def test_check_no_pyc_with_a_base_flags_only_added_site_packages_pyc(tmp_path, exclusions, capsys):
    base, ours = pyc_layers()
    _, base_manifest = run_manifest(tmp_path, docker_archive([base]), exclusions, "base.json")
    _, manifest = run_manifest(tmp_path, docker_archive([base, ours]), exclusions, "img.json")
    capsys.readouterr()
    assert icm.main(["check-no-pyc", str(manifest), "--base", str(base_manifest)]) == 1
    out = capsys.readouterr().out
    assert "pyc_site_packages_added=2" in out and "old.pyc" not in out
    assert "pyc: /usr/lib/python3/site-packages/new.pyc" in out and "pyc: /opt/venv/lib/site-packages/x/y.pyc" in out
    assert "pyc: /act/source/pkg/mod.cpython-312.pyc" in out and "pyc: /act/venv/lib/python3.12/site-packages/z.pyc" in out


def test_check_no_pyc_passes_when_only_base_pyc_exist(tmp_path, exclusions, capsys):
    base, _ = pyc_layers()
    _, base_manifest = run_manifest(tmp_path, docker_archive([base]), exclusions, "base.json")
    clean = [f("/usr/lib/python3/site-packages/mod.py", b"3")]
    _, manifest = run_manifest(tmp_path, docker_archive([base, clean]), exclusions, "img.json")
    capsys.readouterr()
    assert icm.main(["check-no-pyc", str(manifest), "--base", str(base_manifest)]) == 0
    assert "pyc_under_act=0 pyc_under_act_venv=0 pyc_site_packages_added=0" in capsys.readouterr().out


# --- tree: the same rule for a directory (the mounted install and source trees) ---------------------------------------

def make_tree(root, files, mtime=1_000_000):
    import os
    for relative, data in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.utime(path, (mtime, mtime))
    return root


def tree_hash(root, tmp_path, name="t.json"):
    out = tmp_path / name
    code = icm.main(["tree", str(root), "--output", str(out)])
    return code, (json.loads(out.read_text())["tree_sha256"] if out.exists() else None)


def test_tree_hash_ignores_mtimes_and_owners_but_not_content_mode_names_or_symlink_targets(tmp_path):
    import os
    a = make_tree(tmp_path / "a", {"lib/x.so": b"x", "share/p/package.xml": b"<p/>"}, mtime=1)
    b = make_tree(tmp_path / "b", {"lib/x.so": b"x", "share/p/package.xml": b"<p/>"}, mtime=999)
    assert tree_hash(a, tmp_path, "a.json") == tree_hash(b, tmp_path, "b.json") != (0, None)
    (b / "lib/x.so").write_bytes(b"y")
    assert tree_hash(a, tmp_path, "a2.json")[1] != tree_hash(b, tmp_path, "b2.json")[1]
    (b / "lib/x.so").write_bytes(b"x")
    original = (b / "lib/x.so").stat().st_mode & 0o777
    os.chmod(b / "lib/x.so", 0o755)
    assert tree_hash(a, tmp_path, "a3.json")[1] != tree_hash(b, tmp_path, "b3.json")[1]
    os.chmod(b / "lib/x.so", original)
    (b / "lib/link").symlink_to("x.so")
    (a / "lib/link").symlink_to("other.so")
    assert tree_hash(a, tmp_path, "a4.json")[1] != tree_hash(b, tmp_path, "b4.json")[1]
    (a / "lib/link").unlink()
    (a / "lib/link").symlink_to("x.so")
    assert tree_hash(a, tmp_path, "a5.json")[1] == tree_hash(b, tmp_path, "b5.json")[1]


def test_tree_hash_counts_empty_directories_and_rejects_bytecode_instead_of_skipping_it(tmp_path, capsys):
    a = make_tree(tmp_path / "a", {"m.py": b"1"})
    b = make_tree(tmp_path / "b", {"m.py": b"1"})
    (b / "empty").mkdir()
    assert tree_hash(a, tmp_path, "a.json")[1] != tree_hash(b, tmp_path, "b.json")[1]
    make_tree(a, {"__pycache__/m.cpython-312.pyc": b"\x00"})
    capsys.readouterr()
    code, digest = tree_hash(a, tmp_path, "c.json")
    assert code == 1 and digest is None
    assert "__pycache__/m.cpython-312.pyc" in capsys.readouterr().out


def test_tree_hash_refuses_special_files(tmp_path):
    import os
    a = make_tree(tmp_path / "a", {"m.py": b"1"})
    os.mkfifo(a / "pipe")
    assert icm.main(["tree", str(a), "--output", str(tmp_path / "o.json")]) == 2
