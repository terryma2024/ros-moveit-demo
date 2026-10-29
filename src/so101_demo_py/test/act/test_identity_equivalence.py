"""The identity-equivalence rule of `act_merge_collections` and the proof command `act_identity_equivalence`.

Real: the merge, the proof builder and verifier, the git difference (a small repository made here), the tree comparison, the ELF build-id
check and the container-reach analysis. Controlled: everything is a fixture made in `tmp_path` -- the repository (two or three commits of a
few python files), the mounted trees built from it (a `git archive` snapshot, installed copies of the modules, a setup script that names the
mount root, a minimal ELF object whose only difference is its build-id, a debug provenance manifest), the sealed inputs roots with their
`mount-inputs/` records, and the sealed run roots of the merge tests. No host path is read."""

import hashlib
import json
import os
import shutil
import struct
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

from so101_demo.act import identity_equivalence as ie
from so101_demo.act.collection_merge import MergeRefused, MergeSource, merge_collections, sha256_file
from so101_demo.cli import act_identity_equivalence as proof_cli
from so101_demo.cli import act_merge_collections as merge_cli
from test_collection_merge import IDENTITY, make_source, scene_list, seal

SERVICE_OWNER_A = '''import os


def _write(path, data):
    with open(path, "wb") as stream:
        stream.write(data)


class ContainerServiceOwner:
    def __init__(self, stage=None):
        self.stage = stage
        self._tail = "" if stage is None else "-" + stage
'''
#: only the class the host runs changes (a new `attempt` argument); `_write`, which the containers import, does not
SERVICE_OWNER_B = SERVICE_OWNER_A.replace("def __init__(self, stage=None):", "def __init__(self, stage=None, attempt=1):").replace(
    '"-" + stage', '"-" + stage + ("" if attempt == 1 else f"-a{attempt}")')
#: what the containers import changes
SERVICE_OWNER_WRITE_CHANGED = SERVICE_OWNER_A.replace('open(path, "wb")', 'open(path, "ab")')
SERVICE_OWNER_IMPORT_TIME_CHANGED = SERVICE_OWNER_A + "\nRETRIES = 3\n"
SHARD_A = "from so101_demo.runtime.container_campaign.service_owner import _write\n\n\ndef main():\n    return _write\n"
SHARD_WHOLE = ("from so101_demo.runtime.container_campaign import service_owner\n\n\ndef main():\n    return service_owner\n")
SHARD_STRING = 'ARGV = ["python", "-m", "so101_demo.runtime.container_campaign.service_owner"]\n'

BASE_FILES = {
    "src/so101_demo_py/src/cli/campaign_shard.py": SHARD_A,
    "src/so101_demo_py/src/cli/campaign_inference.py": "X = 1\n",
    "src/so101_demo_py/src/cli/campaign_processor.py": "X = 2\n",
    "src/so101_demo_py/src/runtime/container_campaign/image_bootstrap.py": "X = 3\n",
    "src/so101_demo_py/src/runtime/container_campaign/service_owner.py": SERVICE_OWNER_A,
    "src/so101_demo_py/src/runtime/container_campaign/owner.py": "def stage_retry():\n    return 1\n",
    "src/so101_demo_py/src/runtime/container_campaign/other.py": "VALUE = 1\n",
    "src/so101_demo_py/test/test_owner.py": "def test_a():\n    assert True\n",
    "docs/note.md": "note\n",
}
HEAD_EDITS = {
    "src/so101_demo_py/src/runtime/container_campaign/service_owner.py": SERVICE_OWNER_B,
    "src/so101_demo_py/src/runtime/container_campaign/owner.py": "def stage_retry():\n    return 2\n",
    "src/so101_demo_py/test/test_owner.py": "def test_a():\n    assert 1 == 1\n",
    "docs/note.md": "note 2\n",
}
HOST_EDIT = {"src/so101_demo_py/src/runtime/container_campaign/owner.py": "def stage_retry():\n    return 3\n"}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def commit_files(repo, files, message):
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def make_repo(tmp_path, *, edits=None, base=None):
    """A repository with commit `a` and, on top of it, `b` (the host-orchestration edits) and `c` (a further host edit)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    a = commit_files(repo, dict(BASE_FILES, **(base or {})), "a")
    b = commit_files(repo, dict(HEAD_EDITS if edits is None else edits), "b")
    c = commit_files(repo, HOST_EDIT, "c")
    return repo, a, b, c


def elf_object(root_text: str, build_id: bytes) -> bytes:
    """A minimal little-endian ELF64 object: some body naming the mount root, a GNU build-id note and the section name table."""
    body = f"RPATH={root_text}\0".encode().ljust(64, b"\0")
    note = struct.pack("<III", 4, 20, 3) + b"GNU\0" + build_id
    names = b"\0.note.gnu.build-id\0.shstrtab\0"
    note_offset = 64 + len(body)
    names_offset = note_offset + len(note)
    headers_offset = (names_offset + len(names) + 7) & ~7
    header = bytearray(64)
    header[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<Q", header, 0x28, headers_offset)
    struct.pack_into("<HHH", header, 0x3A, 64, 3, 2)
    null = bytes(64)
    note_header = struct.pack("<IIQQQQIIQQ", 1, 7, 0, 0, note_offset, len(note), 0, 0, 4, 0)
    names_header = struct.pack("<IIQQQQIIQQ", 20, 3, 0, 0, names_offset, len(names), 0, 0, 1, 0)
    data = bytes(header) + body + note + names
    return data.ljust(headers_offset, b"\0") + null + note_header + names_header


def derived(commit):
    return ie.derived_hash(commit)


def file_entry(root: Path, path: Path):
    relative = str(path.relative_to(root))
    if path.is_symlink():
        return dict(path=relative, symlink=os.readlink(path))
    return dict(path=relative, bytes=path.stat().st_size, sha256=sha256_file(path))


def build_mount_tree(tmp_path, repo, commit):
    """`<tmp>/mount/<commit12>/{install,source}` the way `build_mount_tree.zsh` makes them, in miniature."""
    root = tmp_path / "mount" / commit[:12]
    (root / "source").mkdir(parents=True)
    archive = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", commit], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=BytesIO(archive)) as tar:
        tar.extractall(root / "source", filter="data")
    package = root / "install/so101_demo_py/lib/python3.12/site-packages/so101_demo"
    artifacts = []
    for source in sorted((root / "source/src/so101_demo_py/src").rglob("*.py")):
        relative = source.relative_to(root / "source/src/so101_demo_py/src")
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        artifacts.append(dict(path=f"lib/python3.12/site-packages/so101_demo/{relative}", sha256=sha256_file(target)))
    provenance = root / "install/so101_demo_py/share/so101_demo_py/debug-provenance-manifest.json"
    provenance.parent.mkdir(parents=True)
    provenance.write_text(json.dumps(dict(schema_version=1, artifacts=artifacts), separators=(",", ":")))
    (root / "install/setup.sh").write_text(f"COLCON_CURRENT_PREFIX={root}/install\n")
    library = root / "install/lib/libshard.so"
    library.parent.mkdir()
    library.write_bytes(elf_object(str(root), hashlib.sha1(commit.encode()).digest()))
    for tree in ("install", "source"):
        (root / tree / "BUILD-COMMIT").write_text(commit + "\n")
    return root


def make_inputs(tmp_path, name, root: Path, commit, *, host_code="", base_image="sha256:" + "b" * 64):
    """The sealed inputs root of a run: `mount-inputs/MOUNT-INPUTS.json` and `tree-manifest.jsonl` of the tree at `root`."""
    inputs = tmp_path / f"inputs-{name}"
    directory = inputs / "mount-inputs"
    directory.mkdir(parents=True)
    entries = [file_entry(root, path) for path in sorted(root.rglob("*")) if path.is_file() or path.is_symlink()]
    (directory / "tree-manifest.jsonl").write_text("".join(json.dumps(entry) + "\n" for entry in entries))
    (directory / "MOUNT-INPUTS.json").write_text(json.dumps(dict(
        kind="MOUNT_INPUTS", commit=commit, mount_root=str(root), build_commit_sha256=dict(install=derived(commit), source=derived(commit)),
        base_image=base_image, tree_manifest_sha256=sha256_file(directory / "tree-manifest.jsonl"), host_code=host_code)))
    seal(inputs)
    return inputs


def identity(root: Path, commit, *, digest="sha256:" + "b" * 64, **edits):
    h = derived(commit)
    document = dict(IDENTITY, mount_build=dict(commit=commit, root=str(root)),
                    image_source_install={role: dict(digest=digest, install_sha256=h, package_source_sha256=h) for role in ("shard", "inference")})
    document.update(edits)
    return document


def preflight(commit, image):
    return dict(schema_version=1, kind="MOUNT_PREFLIGHT", result="PASS", commit=commit, base_image_id=image["digest"],
                base_manifest_sha256="c" * 64, install_record_sha256=image["install_sha256"], must_failures=0, warnings=0, exceptions={},
                host="ai-station")


def sealed_source(tmp_path, name, scenes, ident, commit, *, gpu):
    """A sealed run root of that identity holding the mount preflight of its commit, as the merge reads it."""
    source = make_source(tmp_path, name, scenes, report_edit=dict(identity=ident, gpu=gpu), seal_it=False)
    root = source.index.parent
    (root / "host/mount-preflight.json").write_text(json.dumps(preflight(commit, ident["image_source_install"]["shard"])))
    seal(root)
    return source


class World:
    pass


def make_world(tmp_path, *, edits=None, base=None, host_code="", digest_b=None, with_inputs=True, second="b"):
    world = World()
    world.repo, world.a, world.b, world.c = make_repo(tmp_path, edits=edits, base=base)
    world.commits = dict(a=world.a, b=world.b, c=world.c)
    second_commit = world.commits[second]
    world.root_a = build_mount_tree(tmp_path, world.repo, world.a)
    world.root_b = build_mount_tree(tmp_path, world.repo, second_commit)
    world.inputs_a = make_inputs(tmp_path, "a", world.root_a, world.a, host_code=host_code)
    world.inputs_b = make_inputs(tmp_path, "b", world.root_b, second_commit)
    ids = [f"s{n:02d}" for n in range(6)]
    world.formal = scene_list(tmp_path / "formal.scenes.json", ids, {"s04": "validation", "s05": "offline_test"})
    ident_a = identity(world.root_a, world.a)
    ident_b = identity(world.root_b, second_commit, digest=digest_b or "sha256:" + "b" * 64)
    a = sealed_source(tmp_path, "a", ids[:3], ident_a, world.a, gpu="GPU-a")
    b = sealed_source(tmp_path, "b", ids[3:], ident_b, second_commit, gpu="GPU-b")
    if with_inputs:
        a = MergeSource(index=a.index, qualification_report=a.qualification_report, host=a.host, mount_inputs=world.inputs_a)
        b = MergeSource(index=b.index, qualification_report=b.qualification_report, host=b.host, mount_inputs=world.inputs_b)
    world.sources = [a, b]
    world.tmp = tmp_path
    return world


def write_proof(world, tmp_path, mount=("b",), host=(), name="proof.json"):
    document = ie.build_proof(world.repo, world.a, [world.commits[m] for m in mount], [world.commits[h] for h in host])
    path = tmp_path / name
    path.write_text(json.dumps(document, indent=1))
    return path


def merge(world, proof, **kwargs):
    return merge_collections(world.sources, world.formal, "20261027T010203Z", identity_equivalence=proof, repo=world.repo, **kwargs)


def refused(code, world, proof, **kwargs):
    with pytest.raises(MergeRefused, match=code):
        merge(world, proof, **kwargs)


# ---- the happy path and the record ----------------------------------------------------------------------------------------------

def test_builds_that_differ_only_in_host_orchestration_files_merge_and_the_manifest_records_the_proof(tmp_path):
    world = make_world(tmp_path)
    proof = write_proof(world, tmp_path)
    index, manifest = merge(world, proof)
    record = manifest["identity_equivalence"]
    assert len(index["committed_episodes"]) == 6
    assert record["proof_sha256"] == sha256_file(proof) and record["allow_list_version"] == ie.ALLOW_LIST_VERSION
    assert record["reference_commit"] == world.a
    (comparison,) = record["comparisons"]
    assert comparison["commit"] == world.b and comparison["role"] == "mount_build"
    assert comparison["changed_files"] == sorted(HEAD_EDITS)
    assert comparison["changed_files_sha256"] == ie.list_sha256(sorted(HEAD_EDITS))
    (tree,) = record["trees"]
    assert tree["differences"]["source"]["paths"] == sorted("source/" + name for name in HEAD_EDITS)
    assert tree["differences"]["python"]["count"] == 2
    assert tree["differences"]["provenance"]["count"] == 1 and tree["differences"]["elf"]["count"] == 1
    assert tree["differences"]["text"]["count"] == 1                       # setup.sh: equal after the mount-root substitution
    container = tree["container_side"]["changed_modules_imported_at_start_and_identical"]
    assert list(container) == ["src/so101_demo_py/src/runtime/container_campaign/service_owner.py"]
    assert container["src/so101_demo_py/src/runtime/container_campaign/service_owner.py"]["imported_names"] == ["_write"]
    provenance = index["provenance"]
    assert provenance["identity_equivalence"] == dict(proof_sha256=sha256_file(proof), allow_list_version=ie.ALLOW_LIST_VERSION)
    assert [source["controlled_identity_sha256"] for source in provenance["sources"]][0] != \
        [source["controlled_identity_sha256"] for source in provenance["sources"]][1]


def test_the_host_code_commit_of_a_stage_is_covered_when_a_source_names_it(tmp_path):
    world = make_world(tmp_path)
    world.inputs_a = make_inputs(tmp_path, "a2", world.root_a, world.a, host_code=f"retry and finalize ran host code at {world.c}")
    world.sources[0] = MergeSource(index=world.sources[0].index, qualification_report=world.sources[0].qualification_report,
                                   host="a", mount_inputs=world.inputs_a)
    proof = write_proof(world, tmp_path, host=("c",))
    _, manifest = merge(world, proof)
    assert manifest["identity_equivalence"]["host_code_commits"] == [dict(commit=world.c, named_by=["source 0 (%s)" % world.sources[0].index])]
    assert {entry["role"] for entry in manifest["identity_equivalence"]["comparisons"]} == {"mount_build", "host_code"}


def test_a_host_code_commit_that_no_source_names_is_refused(tmp_path):
    world = make_world(tmp_path)
    refused("MERGE_IDENTITY_EQUIVALENCE_COMMIT_MISMATCH", world, write_proof(world, tmp_path, host=("c",)))


def test_identical_identities_still_merge_without_a_proof(tmp_path):
    world = make_world(tmp_path)
    same = identity(world.root_a, world.a)
    sources = [sealed_source(tmp_path, "x", ["s00", "s01", "s02"], same, world.a, gpu="GPU-a"),
               sealed_source(tmp_path, "y", ["s03", "s04", "s05"], same, world.a, gpu="GPU-b")]
    index, manifest = merge_collections(sources, world.formal, "20261027T010203Z")
    assert len(index["committed_episodes"]) == 6 and "identity_equivalence" not in manifest
    assert "identity_equivalence" not in index["provenance"]


# ---- what is refused ----------------------------------------------------------------------------------------------------------

def test_a_difference_outside_the_two_fields_is_refused_even_with_a_valid_proof(tmp_path):
    world = make_world(tmp_path)
    proof = write_proof(world, tmp_path)
    report = world.sources[1].qualification_report
    document = json.loads(report.read_text())
    document["controlled_identity"]["contact_policy_fingerprint"] = "9" * 64
    report.write_text(json.dumps(document))
    refused(r"MERGE_IDENTITY_MISMATCH: source 1 differs from source 0 in \[.*'contact_policy_fingerprint'", world, proof)


def test_a_different_base_image_is_refused(tmp_path):
    world = make_world(tmp_path, digest_b="sha256:" + "d" * 64)
    refused("MERGE_IDENTITY_EQUIVALENCE_TREE_MISMATCH.*base image", world, write_proof(world, tmp_path))


def test_a_missing_proof_is_refused(tmp_path):
    world = make_world(tmp_path)
    refused(r"MERGE_IDENTITY_MISMATCH: source 1 differs from source 0 in \['image_source_install', 'mount_build'\]; "
            "MERGE_IDENTITY_EQUIVALENCE_MISSING", world, None)
    with pytest.raises(MergeRefused, match="MERGE_IDENTITY_EQUIVALENCE_MISSING"):
        ie.verify_equivalence(None, world.repo, [], workers=1)
    with pytest.raises(MergeRefused, match="MERGE_IDENTITY_EQUIVALENCE_PROOF_INVALID"):
        merge(world, tmp_path / "no-such-proof.json")


def test_a_changed_file_outside_the_allow_list_is_refused_by_the_builder_and_by_the_merge(tmp_path):
    world = make_world(tmp_path, edits=dict(HEAD_EDITS, **{"src/so101_demo_py/src/runtime/container_campaign/other.py": "VALUE = 2\n"}))
    with pytest.raises(MergeRefused, match="MERGE_IDENTITY_EQUIVALENCE_FILE_NOT_ALLOWED"):
        ie.build_proof(world.repo, world.a, [world.b])
    # a proof written by hand with the exact recomputed list is refused by the merge all the same
    files = ie.changed_files(world.repo, world.a, world.b)
    proof = tmp_path / "forged.json"
    proof.write_text(json.dumps(dict(
        kind=ie.PROOF_KIND, schema_version=1, allow_list_version=ie.ALLOW_LIST_VERSION, git_command=ie.GIT_COMMAND, reference_commit=world.a,
        comparisons=[dict(role="mount_build", commit=world.b, changed_files=files, changed_files_sha256=ie.list_sha256(files))])))
    refused("MERGE_IDENTITY_EQUIVALENCE_FILE_NOT_ALLOWED.*other.py", world, proof)


@pytest.mark.parametrize("name,ok", [
    ("src/so101_demo_py/src/runtime/container_campaign/owner.py", True),
    ("src/so101_teleop/so101_teleop/unified/admission.py", True),
    ("src/so101_demo_py/test/runtime/test_x.py", True),
    ("src/so101_teleop/test/unified/test_y.py", True),
    ("docs/experiments/x.md", True),
    ("src/so101_demo_py/src/runtime/container_campaign/launch.py", False),
    ("src/so101_demo_py/src/runtime/container_campaign/owner.py.bak", False),
    ("src/so101_demo_py/config/act/collection.json", False),
    ("src/so101_demo_py/test/data/model.bin", False),
    ("scripts/images/build_mount_tree.zsh", False),
    ("third_party/x.cpp", False),
    ("src/so101_demo_py/src/cli/campaign_shard.py", False),
])
def test_the_allow_list(name, ok):
    assert ie.allowed_file(name) is ok


def test_a_proof_for_other_commits_than_the_sources_is_refused(tmp_path):
    world = make_world(tmp_path)
    refused("MERGE_IDENTITY_EQUIVALENCE_COMMIT_MISMATCH", world, write_proof(world, tmp_path, mount=("c",)))
    other = ie.build_proof(world.repo, world.b, [world.c])                   # reference is no source's commit
    path = tmp_path / "other.json"
    path.write_text(json.dumps(other))
    refused("MERGE_IDENTITY_EQUIVALENCE_COMMIT_MISMATCH", world, path)


def test_a_proof_for_a_source_commit_it_does_not_cover_is_refused(tmp_path):
    world = make_world(tmp_path)
    document = json.loads(write_proof(world, tmp_path).read_text())
    document["comparisons"][0]["commit"] = "0" * 40
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps(document))
    with pytest.raises(MergeRefused, match="MERGE_IDENTITY_EQUIVALENCE_(GIT_FAILED|COMMIT_MISMATCH)"):
        merge(world, path)


@pytest.mark.parametrize("tamper", ["drop_file", "add_file", "sha", "list_of_another_pair"])
def test_a_tampered_proof_whose_list_does_not_match_a_recomputation_is_refused(tmp_path, tamper):
    world = make_world(tmp_path)
    document = json.loads(write_proof(world, tmp_path).read_text())
    entry = document["comparisons"][0]
    if tamper == "drop_file":
        entry["changed_files"].remove("docs/note.md")
        entry["changed_files_sha256"] = ie.list_sha256(entry["changed_files"])       # consistent hash, wrong list
    elif tamper == "add_file":
        entry["changed_files"].append("src/so101_demo_py/src/cli/act_collect_parallel.py")
        entry["changed_files"].sort()
        entry["changed_files_sha256"] = ie.list_sha256(entry["changed_files"])
    elif tamper == "sha":
        entry["changed_files_sha256"] = "0" * 64
    else:
        entry["changed_files"] = ie.changed_files(world.repo, world.b, world.c)       # a real list, of another pair
        entry["changed_files_sha256"] = ie.list_sha256(entry["changed_files"])
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(document))
    with pytest.raises(MergeRefused, match="MERGE_IDENTITY_EQUIVALENCE_(PROOF_TAMPERED|COMMIT_MISMATCH)"):
        merge(world, path)


def test_a_proof_of_another_allow_list_version_or_shape_is_refused(tmp_path):
    world = make_world(tmp_path)
    good = json.loads(write_proof(world, tmp_path).read_text())
    for number, edit in enumerate([dict(allow_list_version="host-orchestration-0"), dict(kind="other"), dict(extra=1), dict(comparisons=[]),
                                   dict(reference_commit=world.a[:12])]):
        path = tmp_path / f"bad{number}.json"
        path.write_text(json.dumps(dict(good, **edit)))
        refused("MERGE_IDENTITY_EQUIVALENCE_PROOF_INVALID", world, path)


def test_the_sealed_inputs_of_every_source_are_required(tmp_path):
    world = make_world(tmp_path, with_inputs=False)
    refused("MERGE_IDENTITY_EQUIVALENCE_INPUTS_MISSING", world, write_proof(world, tmp_path))


def test_a_mount_record_that_does_not_agree_with_the_identity_is_refused(tmp_path):
    world = make_world(tmp_path)
    document_path = world.inputs_b / "mount-inputs/MOUNT-INPUTS.json"
    # an inputs root of another commit
    wrong = make_inputs(tmp_path, "wrong", world.root_a, world.a)
    world.sources[1] = MergeSource(index=world.sources[1].index, qualification_report=world.sources[1].qualification_report, host="b",
                                   mount_inputs=wrong)
    assert document_path.exists()
    refused("MERGE_IDENTITY_EQUIVALENCE_TREE_MISMATCH.*MOUNT-INPUTS.json", world, write_proof(world, tmp_path))


def test_an_unsealed_or_damaged_inputs_root_is_refused(tmp_path):
    world = make_world(tmp_path)
    proof = write_proof(world, tmp_path)
    manifest = world.inputs_b / "mount-inputs/tree-manifest.jsonl"
    os.chmod(manifest, 0o644)
    manifest.write_text(manifest.read_text() + "\n")
    with pytest.raises(MergeRefused, match="MERGE_(IDENTITY_EQUIVALENCE_TREE_MISMATCH|SOURCE_UNSEALED)"):
        merge(world, proof)


def test_an_identity_whose_image_record_is_not_the_hash_of_its_commit_is_refused(tmp_path):
    world = make_world(tmp_path)
    proof = write_proof(world, tmp_path)
    report = world.sources[1].qualification_report
    document = json.loads(report.read_text())
    document["controlled_identity"]["image_source_install"]["shard"]["install_sha256"] = "5" * 64
    report.write_text(json.dumps(document))
    refused("MERGE_IDENTITY_EQUIVALENCE_TREE_MISMATCH.*image record", world, proof)


def test_only_one_of_the_two_fields_differing_is_refused(tmp_path):
    world = make_world(tmp_path)
    proof = write_proof(world, tmp_path)
    report = world.sources[1].qualification_report
    document = json.loads(report.read_text())
    document["controlled_identity"]["mount_build"] = dict(document["controlled_identity"]["mount_build"], commit=world.a)
    report.write_text(json.dumps(document))
    refused("MERGE_IDENTITY_EQUIVALENCE_TREE_MISMATCH", world, proof)


# ---- the mounted trees ----------------------------------------------------------------------------------------------------------

def retarget(tmp_path, world, path_in_tree, data: bytes):
    """Change one file of the second mounted tree on disk and write the sealed inputs again, so only the tree comparison can object."""
    target = world.root_b / path_in_tree
    os.chmod(target.parent, 0o755)
    target.write_bytes(data)
    shutil.rmtree(world.inputs_b)
    world.inputs_b = make_inputs(tmp_path, "b", world.root_b, world.b)
    world.sources[1] = MergeSource(index=world.sources[1].index, qualification_report=world.sources[1].qualification_report, host="b",
                                   mount_inputs=world.inputs_b)


def test_an_installed_module_that_differs_without_its_source_differing_is_refused(tmp_path):
    world = make_world(tmp_path)
    retarget(tmp_path, world, "install/so101_demo_py/lib/python3.12/site-packages/so101_demo/cli/campaign_inference.py", b"X = 99\n")
    refused("MERGE_IDENTITY_EQUIVALENCE_TREE_MISMATCH.*differs between the two builds|not in the git difference", world, write_proof(world, tmp_path))


def test_an_installed_module_that_is_not_its_snapshot_is_refused(tmp_path):
    world = make_world(tmp_path)
    retarget(tmp_path, world, "install/so101_demo_py/lib/python3.12/site-packages/so101_demo/runtime/container_campaign/owner.py",
             b"def stage_retry():\n    return 99\n")
    refused("MERGE_IDENTITY_EQUIVALENCE_TREE_MISMATCH.*not the file of its source snapshot", world, write_proof(world, tmp_path))


def test_a_compiled_object_that_differs_beyond_its_build_id_is_refused(tmp_path):
    world = make_world(tmp_path)
    data = bytearray((world.root_b / "install/lib/libshard.so").read_bytes())
    data[70] ^= 0xFF                                        # a byte of the body, not of the build-id note
    retarget(tmp_path, world, "install/lib/libshard.so", bytes(data))
    refused("MERGE_IDENTITY_EQUIVALENCE_TREE_MISMATCH.*libshard.so.*build-id", world, write_proof(world, tmp_path))


def test_a_build_script_that_differs_beyond_the_mount_root_is_refused(tmp_path):
    world = make_world(tmp_path)
    retarget(tmp_path, world, "install/setup.sh", f"COLCON_CURRENT_PREFIX={world.root_b}/install\nexport EVIL=1\n".encode())
    refused("MERGE_IDENTITY_EQUIVALENCE_TREE_MISMATCH.*setup.sh", world, write_proof(world, tmp_path))


def test_a_tree_file_that_is_not_what_its_manifest_lists_is_refused(tmp_path):
    world = make_world(tmp_path)
    (world.root_b / "install/setup.sh").write_text("changed after the manifest\n")
    refused("MERGE_IDENTITY_EQUIVALENCE_TREE_MISMATCH.*sealed tree manifest", world, write_proof(world, tmp_path))


def test_a_file_the_snapshots_differ_in_but_git_does_not_name_is_refused(tmp_path):
    world = make_world(tmp_path)
    retarget(tmp_path, world, "source/src/so101_demo_py/src/runtime/container_campaign/other.py", b"VALUE = 77\n")
    refused("MERGE_IDENTITY_EQUIVALENCE_TREE_MISMATCH", world, write_proof(world, tmp_path))
    # and the other way: the snapshot of the second build lacks the edit git names
    (tmp_path / "other").mkdir()
    world = make_world(tmp_path / "other")
    retarget(tmp_path / "other", world, "source/docs/note.md", (world.root_a / "source/docs/note.md").read_bytes())
    refused("MERGE_IDENTITY_EQUIVALENCE_TREE_MISMATCH.*identically", world, write_proof(world, tmp_path))


# ---- what a container can reach ---------------------------------------------------------------------------------------------------

def test_a_symbol_a_container_imports_that_changed_is_refused(tmp_path):
    world = make_world(tmp_path, edits=dict(HEAD_EDITS, **{"src/so101_demo_py/src/runtime/container_campaign/service_owner.py":
                                                           SERVICE_OWNER_WRITE_CHANGED}))
    refused("MERGE_IDENTITY_EQUIVALENCE_CONTAINER_REACH.*service_owner.py", world, write_proof(world, tmp_path))


def test_import_time_code_of_a_module_a_container_reaches_that_changed_is_refused(tmp_path):
    world = make_world(tmp_path, edits=dict(HEAD_EDITS, **{"src/so101_demo_py/src/runtime/container_campaign/service_owner.py":
                                                           SERVICE_OWNER_IMPORT_TIME_CHANGED}))
    refused("MERGE_IDENTITY_EQUIVALENCE_CONTAINER_REACH.*import-time", world, write_proof(world, tmp_path))


@pytest.mark.parametrize("shard", [SHARD_WHOLE, SHARD_STRING])
def test_a_container_that_uses_a_changed_module_as_a_whole_is_refused(tmp_path, shard):
    world = make_world(tmp_path, base={"src/so101_demo_py/src/cli/campaign_shard.py": shard})
    refused("MERGE_IDENTITY_EQUIVALENCE_CONTAINER_REACH.*as a whole", world, write_proof(world, tmp_path))


def test_a_changed_module_reached_only_inside_a_function_is_not_proven_absent_and_is_reported_as_relied_on(tmp_path):
    lazy = ("def main():\n    from so101_demo.runtime.container_campaign.service_owner import ContainerServiceOwner\n"
            "    return ContainerServiceOwner\n")
    world = make_world(tmp_path, base={"src/so101_demo_py/src/cli/campaign_shard.py": lazy})
    _, manifest = merge(world, write_proof(world, tmp_path))
    side = manifest["identity_equivalence"]["trees"][0]["container_side"]
    service_owner = "src/so101_demo_py/src/runtime/container_campaign/service_owner.py"
    assert side["changed_modules_imported_at_start_and_identical"] == {}
    reliance = side["relied_on_allow_list"][service_owner]
    assert reliance["imported_names"] == ["ContainerServiceOwner"] and reliance["imported_slice_identical"] is False
    assert list(reliance["chains"].values())[0] == ["so101_demo.cli.campaign_shard",
                                                    "so101_demo.runtime.container_campaign.service_owner"]


def test_a_changed_host_module_no_container_reaches_is_accepted_and_reported(tmp_path):
    world = make_world(tmp_path, base={"src/so101_demo_py/src/cli/campaign_shard.py": "X = 5\n"})
    _, manifest = merge(world, write_proof(world, tmp_path))
    side = manifest["identity_equivalence"]["trees"][0]["container_side"]
    assert side["changed_modules_imported_at_start_and_identical"] == {} and side["relied_on_allow_list"] == {}


# ---- the commands -----------------------------------------------------------------------------------------------------------------

def test_the_proof_command_writes_the_proof_once_and_refuses_what_the_allow_list_forbids(tmp_path, capsys):
    world = make_world(tmp_path)
    out = tmp_path / "cmd-proof.json"
    argv = ["--repo", str(world.repo), "--reference", world.a, "--mount-commit", world.b, "--out", str(out)]
    assert proof_cli.main(argv) == 0
    assert json.loads(out.read_text()) == ie.build_proof(world.repo, world.a, [world.b])
    assert proof_cli.main(argv) == 2                                                     # exists
    (tmp_path / "f").mkdir()
    forbidden = make_world(tmp_path / "f", edits={"src/so101_demo_py/src/runtime/container_campaign/other.py": "VALUE = 5\n"})
    refused_out = tmp_path / "refused.json"
    assert proof_cli.main(["--repo", str(forbidden.repo), "--reference", forbidden.a, "--mount-commit", forbidden.b, "--out", str(refused_out)]) == 2
    assert not refused_out.exists() and "FILE_NOT_ALLOWED" in capsys.readouterr().err


def test_the_merge_command_takes_the_proof_the_repository_and_the_inputs_of_each_source(tmp_path, capsys):
    world = make_world(tmp_path)
    proof = write_proof(world, tmp_path)
    out = tmp_path / "merged"
    argv = ["--out-dir", str(out), "--formal-list", str(world.formal), "--stamp", "20261027T010203Z", "--identity-equivalence", str(proof),
            "--repo", str(world.repo)]
    for source in world.sources:
        argv += ["--index", str(source.index), "--qualification-report", str(source.qualification_report), "--host", source.host,
                 "--mount-inputs", str(source.mount_inputs)]
    assert merge_cli.main(argv) == 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["identity_equivalence"]["proof_sha256"] == sha256_file(proof)
    assert len(manifest["episodes"]) == 6
    shutil.rmtree(out)
    assert merge_cli.main([part for part in argv if part not in ("--identity-equivalence", str(proof))]) == 2
    assert "MERGE_IDENTITY_EQUIVALENCE_MISSING" in capsys.readouterr().err
    assert not out.exists()
