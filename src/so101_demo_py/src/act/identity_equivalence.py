"""The identity-equivalence rule of `act_merge_collections`: two formal runs whose controlled identity differs only in `mount_build` and
`image_source_install` (the commit of the mounted build and the hashes derived from it) may be merged when it is shown, not assumed, that the
two builds differ only in host-orchestration code.

Human decision of 2026-10-27: allow the merge only if every commit difference between the sources falls in a controlled list of host-orchestration
files, the container-side code of both sides is the same, and the differences are written into the merge manifest. This module is that rule.

The proof (`ACT_IDENTITY_EQUIVALENCE`, made by `act_identity_equivalence`) records the reference commit, the compared commits (mounted builds
and host-code commits) and, for each, the exact `git diff --name-only --no-renames <reference> <commit>` over the whole tree with its sha256.
The merge never trusts the document. `verify_proof` recomputes every list from the git repository and refuses (`PROOF_TAMPERED`) on any
difference; every path must be in `ALLOWED_FILES`, a test file under `TEST_PREFIXES` or a documentation file under `DOC_PREFIXES`. There is no
wildcard over `src` outside the test directories.

`verify_trees` then compares the two mounted builds through the sealed `mount-inputs` of the runs (`MOUNT-INPUTS.json`, `tree-manifest.jsonl`,
the trees on disk as the inputs root names them). Every difference between the two manifests is classified; none may be left over:

  source     the `source/` snapshot differs in exactly the files of the git list (set equality with the recomputed list)
  python     an installed module differs only where its source does; the installed bytes equal the snapshot bytes (manifest hashes)
  provenance `debug-provenance-manifest.json` differs only in the entries of those modules, with the same hashes
  elf        a compiled object equal after the mount-root substitution except for the 20 bytes of the GNU build-id note
  text       any other file equal byte for byte after the substitution of the mount root and the commit (setup scripts, prefix paths, egg-info)
  generated  an installed generated type-support `.c` under an `include/.../detail/` directory (two rosidl generators write the same
             file name in a parallel build, so the content is not reproducible). Never compiled or executed in a container; reported by count
             and NOT verified (the one class the rule accepts by path alone).

Container reach: the container entry modules (`campaign_shard`, `campaign_inference`, `campaign_processor`, `image_bootstrap`) are followed
through every `import` (also inside functions) and every string constant that names a module, in both source snapshots. A changed allow-listed
module that this closure reaches is accepted only when it is reached through `from <module> import <names>`; then the module-level code that
is not a definition, and the definitions named (with the module-level names they use, transitively), must be the same syntax tree in both
snapshots. A whole-module use (`import module`) of a changed module is refused. The analysis is static: an import built at run time from a
string that is not a literal module name is not seen.

Everything fails closed with `MergeRefused` messages that start with `MERGE_IDENTITY_EQUIVALENCE_*`.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

from so101_demo.act.collection_merge import MergeRefused, read_seal, sha256_file, verify_seal

PROOF_KIND = "ACT_IDENTITY_EQUIVALENCE"
PROOF_SCHEMA_VERSION = 1
#: version of the reviewed lists below; the proof names it and the merge refuses any other
ALLOW_LIST_VERSION = "host-orchestration-2026-10-27.1"
#: reviewed host-orchestration modules: they run in the host process (campaign owner, stage records, qualification recompute, admission);
#: none of them is the entry of a container. Whatever a container imports from one of them is compared symbol by symbol (see above).
ALLOWED_FILES = frozenset({
    "src/so101_demo_py/src/act/collection_qualification_recompute.py",
    "src/so101_demo_py/src/cli/act_collect_parallel.py",
    "src/so101_demo_py/src/cli/act_process_parallel.py",
    "src/so101_demo_py/src/runtime/act_fixed_collection_composition.py",
    "src/so101_demo_py/src/runtime/container_campaign/owner.py",
    "src/so101_demo_py/src/runtime/container_campaign/service_owner.py",
    "src/so101_demo_py/src/runtime/container_campaign/stage_records.py",
    "src/so101_teleop/so101_teleop/unified/admission.py",
})
TEST_PREFIXES = ("src/so101_demo_py/test/", "src/so101_teleop/test/")
DOC_PREFIXES = ("docs/",)
ROLES = ("mount_build", "host_code")
GIT_COMMAND = "git diff --name-only --no-renames -z <reference> <commit>"
#: the programs a container is started with, as modules (launch.py: campaign_processor, campaign_shard, campaign_inference; the bootstrap)
CONTAINER_ENTRIES = ("so101_demo.cli.campaign_shard", "so101_demo.cli.campaign_inference", "so101_demo.cli.campaign_processor",
                     "so101_demo.runtime.container_campaign.image_bootstrap")
PYTHON_ROOTS = {"so101_demo": "src/so101_demo_py/src", "so101_teleop": "src/so101_teleop/so101_teleop"}
_HEX40 = re.compile(r"[0-9a-f]{40}")
_INSTALL_TOP = {"so101_demo_py": "so101_demo", "so101_teleop": "so101_teleop"}
_INSTALL_PY = re.compile(r"install/(so101_demo_py|so101_teleop)/lib/python3\.\d+/site-packages/(so101_demo|so101_teleop)/(.+\.py)")
_PROVENANCE = "install/so101_demo_py/share/so101_demo_py/debug-provenance-manifest.json"
_GENERATED_C = re.compile(r"install/[^/]+/include/.+/detail/[^/]+__type_support\.c")
_BUILD_COMMIT = ("install/BUILD-COMMIT", "source/BUILD-COMMIT")
_CODE = "MERGE_IDENTITY_EQUIVALENCE_"


def refuse(code, message):
    raise MergeRefused(f"{_CODE}{code}: {message}")


def allowed_file(path: str) -> bool:
    return path in ALLOWED_FILES or (path.startswith(TEST_PREFIXES) and path.endswith(".py")) or path.startswith(DOC_PREFIXES)


def derived_hash(commit: str) -> str:
    """The sha256 of the `BUILD-COMMIT` record of a tree (`<commit>\\n`): what the image records of the identity hold."""
    return hashlib.sha256(f"{commit}\n".encode()).hexdigest()


def list_sha256(files) -> str:
    return hashlib.sha256("".join(f"{name}\n" for name in files).encode()).hexdigest()


# ---- git ---------------------------------------------------------------------------------------------------------------------

def _git(repo, *args) -> bytes:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", b"")
        refuse("GIT_FAILED", f"git {' '.join(args[:3])}: {error} {detail.decode(errors='replace').strip()[:200] if detail else ''}")


def _commit(value, what) -> str:
    if not isinstance(value, str) or _HEX40.fullmatch(value) is None:
        refuse("PROOF_INVALID", f"{what} is not a full 40-hex commit: {value!r}")
    return value


def changed_files(repo, reference: str, commit: str) -> list:
    """`git diff --name-only --no-renames` of the whole tree between the two commits, sorted. Both must exist in `repo`."""
    for value in (reference, commit):
        if _git(repo, "rev-parse", "--verify", "-q", f"{value}^{{commit}}").decode().strip() != value:
            refuse("GIT_FAILED", f"{value} is not a commit of {repo}")
    names = _git(repo, "diff", "--name-only", "--no-renames", "-z", reference, commit).decode("utf-8", "surrogateescape")
    return sorted(name for name in names.split("\0") if name)


def build_proof(repo, reference: str, mount_commits=(), host_commits=()) -> dict:
    """The proof document. Refuses at once when a changed file is outside the allow-list (no proof of a forbidden difference exists)."""
    comparisons = []
    for role, commits in (("mount_build", mount_commits), ("host_code", host_commits)):
        for commit in commits:
            files = changed_files(repo, _commit(reference, "reference"), _commit(commit, role))
            outside = [name for name in files if not allowed_file(name)]
            if outside:
                refuse("FILE_NOT_ALLOWED", f"{commit} differs from {reference} in {len(outside)} file(s) outside the allow-list, first: {outside[:5]}")
            comparisons.append(dict(role=role, commit=commit, changed_files=files, changed_files_sha256=list_sha256(files)))
    if not comparisons:
        refuse("PROOF_INVALID", "no commit to compare")
    return dict(kind=PROOF_KIND, schema_version=PROOF_SCHEMA_VERSION, allow_list_version=ALLOW_LIST_VERSION, git_command=GIT_COMMAND,
                reference_commit=reference, comparisons=comparisons)


def verify_proof(path, repo) -> tuple:
    """`(document, sha256 of the file)` when the proof is intact: shape, allow-list version, every list recomputed from `repo` and equal, every
    path allowed. Anything else is a refusal."""
    try:
        payload = Path(path).read_bytes()
        document = json.loads(payload)
    except (OSError, ValueError) as error:
        refuse("PROOF_INVALID", f"{path} cannot be read: {error}")
    keys = {"kind", "schema_version", "allow_list_version", "git_command", "reference_commit", "comparisons"}
    if (not isinstance(document, dict) or set(document) != keys or document["kind"] != PROOF_KIND
            or document["schema_version"] != PROOF_SCHEMA_VERSION or not isinstance(document["comparisons"], list)
            or not document["comparisons"]):
        refuse("PROOF_INVALID", f"{path} is not an {PROOF_KIND} document")
    if document["allow_list_version"] != ALLOW_LIST_VERSION:
        refuse("PROOF_INVALID", f"{path}: allow-list version {document['allow_list_version']!r}, this tool holds {ALLOW_LIST_VERSION!r}")
    reference = _commit(document["reference_commit"], "reference_commit")
    seen = set()
    for number, entry in enumerate(document["comparisons"]):
        if (not isinstance(entry, dict) or set(entry) != {"role", "commit", "changed_files", "changed_files_sha256"}
                or entry["role"] not in ROLES or not isinstance(entry["changed_files"], list)
                or not all(isinstance(name, str) for name in entry["changed_files"])):
            refuse("PROOF_INVALID", f"comparison {number} of {path} has a wrong shape")
        commit = _commit(entry["commit"], f"comparison {number}")
        if (entry["role"], commit) in seen or commit == reference:
            refuse("PROOF_INVALID", f"comparison {number}: {commit} is named twice or is the reference")
        seen.add((entry["role"], commit))
        recomputed = changed_files(repo, reference, commit)
        if entry["changed_files"] != recomputed or entry["changed_files_sha256"] != list_sha256(recomputed):
            refuse("PROOF_TAMPERED", f"comparison {number} ({commit}): the recorded file list or its sha256 is not what {GIT_COMMAND} "
                                     f"recomputes in {repo} ({len(entry['changed_files'])} recorded, {len(recomputed)} recomputed)")
        outside = [name for name in recomputed if not allowed_file(name)]
        if outside:
            refuse("FILE_NOT_ALLOWED", f"{commit} differs from {reference} in {len(outside)} file(s) outside the allow-list "
                                       f"{ALLOW_LIST_VERSION}, first: {outside[:5]}")
    return document, hashlib.sha256(payload).hexdigest()


# ---- the identities ----------------------------------------------------------------------------------------------------------

def source_commit(identity: dict, name: str) -> str:
    """The mounted commit of one source identity, with its image records checked against it: every record's install and package hash is the
    hash of that commit's `BUILD-COMMIT` record. Returns the commit."""
    mount = identity.get("mount_build")
    if not isinstance(mount, dict) or set(mount) != {"commit", "root"} or not isinstance(mount["root"], str):
        refuse("TREE_MISMATCH", f"{name}: the identity has no mount_build {{commit, root}}")
    commit = _commit(mount["commit"], f"{name} mount_build.commit")
    images = identity.get("image_source_install")
    if not isinstance(images, dict) or not images:
        refuse("TREE_MISMATCH", f"{name}: the identity has no image records")
    for role, record in images.items():
        if (not isinstance(record, dict) or set(record) != {"digest", "install_sha256", "package_source_sha256"}
                or record["install_sha256"] != derived_hash(commit) or record["package_source_sha256"] != derived_hash(commit)):
            refuse("TREE_MISMATCH", f"{name}: image record {role!r} is not the base image plus the build record of {commit}")
    return commit


def base_images(identity: dict) -> dict:
    return {role: record["digest"] for role, record in identity["image_source_install"].items()}


# ---- the mount inputs ---------------------------------------------------------------------------------------------------------

def _read_manifest(path) -> dict:
    entries = {}
    try:
        for line in Path(path).read_text().splitlines():
            if line.strip():
                entry = json.loads(line)
                entries[entry["path"]] = entry
    except (OSError, ValueError, KeyError, TypeError) as error:
        refuse("TREE_MISMATCH", f"{path} is not a tree manifest: {error}")
    return entries


def load_mount_inputs(inputs_root, identity: dict, commit: str, name: str, *, workers: int = 4) -> dict:
    """The sealed inputs root of a run, read back, with its `mount-inputs/` record checked against the identity of the source."""
    inputs_root = Path(inputs_root)
    record, entries = read_seal(inputs_root)
    problems = verify_seal(inputs_root, entries, workers=workers)
    if problems:
        refuse("TREE_MISMATCH", f"{name}: the inputs root {inputs_root} fails its seal readback: {problems[:3]}")
    directory = inputs_root / "mount-inputs"
    try:
        document = json.loads((directory / "MOUNT-INPUTS.json").read_bytes())
    except (OSError, ValueError) as error:
        refuse("TREE_MISMATCH", f"{name}: {directory}/MOUNT-INPUTS.json: {error}")
    tree_manifest = directory / "tree-manifest.jsonl"
    expected_hash = derived_hash(commit)
    if (not isinstance(document, dict) or document.get("kind") != "MOUNT_INPUTS" or document.get("commit") != commit
            or document.get("mount_root") != identity["mount_build"]["root"]
            or document.get("build_commit_sha256") != dict(install=expected_hash, source=expected_hash)
            or document.get("tree_manifest_sha256") != sha256_file(tree_manifest)
            or document.get("base_image") not in set(base_images(identity).values())):
        refuse("TREE_MISMATCH", f"{name}: MOUNT-INPUTS.json does not agree with the identity (commit, mount root, record hashes, manifest hash)")
    manifest = _read_manifest(tree_manifest)
    for tree in ("install", "source"):
        entry = manifest.get(f"{tree}/BUILD-COMMIT")
        if entry is None or entry.get("sha256") != expected_hash:
            refuse("TREE_MISMATCH", f"{name}: the tree manifest holds no {tree}/BUILD-COMMIT of {commit}")
    return dict(name=name, commit=commit, root=Path(document["mount_root"]), manifest=manifest, document=document,
                inputs_root=str(inputs_root), tree_manifest_sha256=document["tree_manifest_sha256"],
                mount_inputs_sha256=sha256_file(directory / "MOUNT-INPUTS.json"))


def installed_module(path: str):
    """The repo path of the source of an installed python module, or None."""
    found = _INSTALL_PY.fullmatch(path)
    if found is None:
        return None
    package, top, relative = found.groups()
    if _INSTALL_TOP.get(package) != top:
        return None
    return f"{PYTHON_ROOTS[top]}/{relative}"


def _read_checked(side, path):
    """The bytes of a file of a mounted tree, equal to its manifest hash; a missing or changed file is a refusal."""
    entry = side["manifest"].get(path)
    try:
        data = (side["root"] / path).read_bytes()
    except OSError as error:
        refuse("TREE_MISMATCH", f"{side['name']}: {side['root'] / path} cannot be read: {error}")
    if entry is None or hashlib.sha256(data).hexdigest() != entry.get("sha256"):
        refuse("TREE_MISMATCH", f"{side['name']}: {side['root'] / path} is not the file the sealed tree manifest lists")
    return data


def _substitute(data: bytes, a, b) -> bytes:
    """`a`'s mount root, full commit and 12-hex id replaced by `b`'s (all the same length, so offsets stay)."""
    return (data.replace(str(a["root"]).encode(), str(b["root"]).encode()).replace(a["commit"].encode(), b["commit"].encode())
            .replace(a["commit"][:12].encode(), b["commit"][:12].encode()))


def _build_id_range(data: bytes):
    """`(start, end)` of the descriptor of the GNU build-id note of a little-endian ELF64 object, or None."""
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        return None
    shoff, = struct.unpack_from("<Q", data, 0x28)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 0x3A)
    if not shoff or shentsize < 64 or shoff + shnum * shentsize > len(data) or shstrndx >= shnum:
        return None

    def section(index):
        return struct.unpack_from("<IIQQQQIIQQ", data, shoff + index * shentsize)

    names = section(shstrndx)
    for index in range(shnum):
        header = section(index)
        label = data[names[4] + header[0]:data.index(b"\0", names[4] + header[0])]
        if label == b".note.gnu.build-id":
            offset, size = header[4], header[5]
            namesz, descsz, kind = struct.unpack_from("<III", data, offset)
            if kind != 3 or data[offset + 12:offset + 12 + namesz] != b"GNU\0" or size < 12 + ((namesz + 3) & ~3) + descsz:
                return None
            start = offset + 12 + ((namesz + 3) & ~3)
            return start, start + descsz
    return None


def _elf_equal(a_data: bytes, b_data: bytes) -> bool:
    if len(a_data) != len(b_data):
        return False
    span = _build_id_range(a_data)
    if span is None or span != _build_id_range(b_data):
        return False
    start, end = span
    return a_data[:start] == b_data[:start] and a_data[end:] == b_data[end:]


def _provenance_problem(a, b, differing: set):
    """None when the two debug provenance manifests differ only in the entries of installed files that differ between the trees (each of
    them is classified on its own), with the hashes the tree manifests hold."""
    try:
        da = json.loads(_substitute(_read_checked(a, _PROVENANCE), a, b))
        db = json.loads(_read_checked(b, _PROVENANCE))
        ea = {item["path"]: item["sha256"] for item in da["artifacts"]}
        eb = {item["path"]: item["sha256"] for item in db["artifacts"]}
    except (ValueError, KeyError, TypeError) as error:
        return f"unreadable: {error}"
    if len(ea) != len(da["artifacts"]) or len(eb) != len(db["artifacts"]) or set(ea) != set(eb):
        return "the entry sets differ"
    if {key: value for key, value in da.items() if key != "artifacts"} != {key: value for key, value in db.items() if key != "artifacts"}:
        return "a field other than the artifacts differs"
    for path in sorted(p for p in ea if ea[p] != eb[p]):
        full = f"install/so101_demo_py/{path}"
        if full not in differing:
            return f"{path} differs but is not an installed file that differs between the trees"
        if a["manifest"].get(full, {}).get("sha256") != ea[path] or b["manifest"].get(full, {}).get("sha256") != eb[path]:
            return f"{path}: the provenance hash is not the hash of the installed file"
    return None


def compare_trees(a: dict, b: dict, git_files: list) -> dict:
    """Classify every difference between the two tree manifests (see the module doc); returns the counts and lists for the merge manifest."""
    changed = set(git_files)
    differing = sorted(p for p in set(a["manifest"]) | set(b["manifest"]) if a["manifest"].get(p) != b["manifest"].get(p))
    report = dict(source=[], python=[], provenance=[], elf=[], text=[], generated=[])
    modules = {p for p in differing if installed_module(p) is not None}
    for path in differing:
        if path in _BUILD_COMMIT:
            continue
        if path.startswith("source/"):
            if path[len("source/"):] not in changed:
                refuse("TREE_MISMATCH", f"the source snapshots differ in {path}, which is not in the git difference of the proof")
            report["source"].append(path)
        elif path in modules:
            repo_path = installed_module(path)
            if repo_path not in changed:
                refuse("TREE_MISMATCH", f"the installed module {path} differs but {repo_path} is not in the git difference of the proof")
            for side in (a, b):
                installed, snapshot = side["manifest"].get(path), side["manifest"].get(f"source/{repo_path}")
                if (installed is None) != (snapshot is None) or (installed and installed.get("sha256") != snapshot.get("sha256")):
                    refuse("TREE_MISMATCH", f"{side['name']}: {path} is not the file of its source snapshot")
            report["python"].append(path)
        elif path == _PROVENANCE:
            problem = _provenance_problem(a, b, set(differing))
            if problem:
                refuse("TREE_MISMATCH", f"{path}: {problem}")
            report["provenance"].append(path)
        elif _GENERATED_C.fullmatch(path):
            report["generated"].append(path)
        else:
            if path not in a["manifest"] or path not in b["manifest"] or "sha256" not in a["manifest"][path] or "sha256" not in b["manifest"][path]:
                refuse("TREE_MISMATCH", f"{path} exists in only one tree or is not a regular file, and is no allow-listed module")
            da, db = _substitute(_read_checked(a, path), a, b), _read_checked(b, path)
            if da == db:
                report["text"].append(path)
            elif _elf_equal(da, db):
                report["elf"].append(path)
            else:
                refuse("TREE_MISMATCH", f"{path} differs between the two builds and is neither equal after the mount-root substitution "
                                        "nor equal outside the GNU build-id")
    missing = sorted(f"source/{name}" for name in changed - {p[len("source/"):] for p in report["source"]}
                     if f"source/{name}" in a["manifest"] or f"source/{name}" in b["manifest"])
    if missing:
        refuse("TREE_MISMATCH", f"the git difference names {len(missing)} file(s) the source snapshots hold identically, first: {missing[:3]}")
    return {kind: dict(count=len(paths), **(dict(paths=paths) if kind in ("source", "python", "provenance") else {}))
            for kind, paths in report.items()}


# ---- the container reach ------------------------------------------------------------------------------------------------------

def _module_path(source_root: Path, module: str):
    top, _, rest = module.partition(".")
    base = PYTHON_ROOTS.get(top)
    if base is None:
        return None
    path = source_root / base
    path = path.joinpath(*rest.split(".")) if rest else path
    if path.with_suffix(".py").is_file():
        return path.with_suffix(".py")
    if (path / "__init__.py").is_file():
        return path / "__init__.py"
    return None


def _module_name(source_root: Path, path: Path):
    for top, base in PYTHON_ROOTS.items():
        try:
            relative = path.relative_to(source_root / base)
        except ValueError:
            continue
        parts = list(relative.with_suffix("").parts)
        package = parts[-1] == "__init__"
        if package:
            parts.pop()
        return ".".join([top, *parts]), package
    raise ValueError(path)


def _slice(tree: ast.Module, names: set):
    """`(statements, definitions)` a container can run of a module that it imports with `from module import names`: every module-level
    statement that is not a definition, and the definitions in `names` plus, transitively, the module-level definitions they refer to."""
    definitions = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    wanted, todo = set(), [name for name in names if name in definitions]
    while todo:
        name = todo.pop()
        if name in wanted:
            continue
        wanted.add(name)
        for node in ast.walk(definitions[name]):
            if isinstance(node, ast.Name) and node.id in definitions:
                todo.append(node.id)
    statements = [node for node in tree.body if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    return statements, {name: definitions[name] for name in sorted(wanted)}


def _definition_slice(tree: ast.Module, names: set):
    statements, definitions = _slice(tree, names)
    return [ast.dump(node) for node in statements], {name: ast.dump(node) for name, node in definitions.items()}


def _import_targets(source_root: Path, module: str, package: bool, node):
    """`(module, name or None)` pairs one syntax node refers to: `import m`, `from m import n` (a submodule is a whole use of it) and a string
    constant that is a module name."""
    targets = []
    if isinstance(node, ast.Import):
        targets.extend((item.name, None) for item in node.names)
    elif isinstance(node, ast.ImportFrom):
        base = module.split(".")
        if node.level:
            base = base if package else base[:-1]
            base = base[:len(base) - (node.level - 1)]
            target = ".".join(base + ([node.module] if node.module else []))
        else:
            target = node.module or ""
        for item in node.names:
            child = f"{target}.{item.name}"
            targets.append((child, None) if _module_path(source_root, child) is not None else (target, item.name))
    elif isinstance(node, ast.Constant) and isinstance(node.value, str) and re.fullmatch(r"so101_(demo|teleop)(\.\w+)+", node.value):
        if _module_path(source_root, node.value) is not None:
            targets.append((node.value, None))
    return targets


def _walk(node, eager_only: bool):
    """The syntax nodes of `node`; with `eager_only`, not the bodies of functions (their imports run only when they are called; their
    decorators and default values, which run when the function is defined, are kept)."""
    yield node
    if eager_only and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        arguments = node.args
        children = [*getattr(node, "decorator_list", ()), *arguments.defaults, *(d for d in arguments.kw_defaults if d is not None)]
    else:
        children = list(ast.iter_child_nodes(node))
    for child in children:
        yield from _walk(child, eager_only)


def container_reach(source_root: Path, sliced=frozenset(), *, eager_only: bool = False) -> dict:
    """`module -> {path, whole, names, by}` for every module the container entries reach: every import statement (inside functions too) and
    every string constant that is a module name, followed to a fixpoint. `names` are the names imported from a module by
    `from module import name`; `whole` is True when something imports the module itself; `by` the importers. A module in `sliced` (a changed
    host-orchestration module) that is only imported by name is followed only through what those names can run (`_slice`), not through the
    imports of its host-side code. With `eager_only` only the imports that run when a module is imported are followed (not those inside the
    bodies of functions): the modules a container certainly loads."""
    named = {module: dict(whole=True, names=set(), by=set()) for module in CONTAINER_ENTRIES}
    processed = {}
    while True:
        progress = False
        for module in sorted(named):
            path = _module_path(source_root, module)
            if path is None:
                continue
            entry = named[module]
            key = (entry["whole"], frozenset(entry["names"])) if module in sliced else None
            if processed.get(module, "unseen") == key:
                continue
            processed[module] = key
            progress = True
            parts = module.split(".")
            for cut in range(1, len(parts)):
                named.setdefault(".".join(parts[:cut]), dict(whole=True, names=set(), by=set()))["by"].add(module)
            _, package = _module_name(source_root, path)
            tree = ast.parse(path.read_bytes())
            if module in sliced and not entry["whole"]:
                statements, definitions = _slice(tree, entry["names"])
                nodes = [item for root in (*statements, *definitions.values()) for item in _walk(root, eager_only)]
            else:
                nodes = list(_walk(tree, eager_only))
            for node in nodes:
                for target, name in _import_targets(source_root, module, package, node):
                    seen = named.setdefault(target, dict(whole=False, names=set(), by=set()))
                    seen["by"].add(module)
                    if name is None:
                        seen["whole"] = True
                    else:
                        seen["names"].add(name)
        if not progress:
            break
    return {module: dict(path=_module_path(source_root, module), **entry) for module, entry in named.items()
            if _module_path(source_root, module) is not None}


def _repo_module(repo_path: str):
    for top, base in PYTHON_ROOTS.items():
        if repo_path.startswith(base + "/") and repo_path.endswith(".py"):
            parts = repo_path[len(base) + 1:-3].split("/")
            return ".".join([top, *(parts[:-1] if parts[-1] == "__init__" else parts)])
    return None


def _chain(reach: dict, goal: str) -> list:
    """The shortest import chain from a container entry to `goal` in a reach map."""
    from collections import deque

    parent, queue = {goal: None}, deque([goal])
    while queue:
        current = queue.popleft()
        if current in CONTAINER_ENTRIES:
            chain = []
            while current is not None:
                chain.append(current)
                current = parent[current]
            return chain
        for importer in sorted(reach[current]["by"]):
            if importer not in parent and importer in reach:
                parent[importer] = current
                queue.append(importer)
    return []


def verify_container_side(a: dict, b: dict, git_files: list) -> dict:
    """The container-side code of the two snapshots is the same, to the extent a static analysis shows it.

    Imported when a container program starts (`eager`): a changed module there is accepted only when it is imported by name and what is
    imported (the module-level code that is not a definition, and the named definitions with what they use) is the same syntax tree in
    both snapshots; any other case is refused.

    Imported only inside function bodies (`lazy`): whether such an import runs depends on the code path, which this analysis does not
    follow. A changed module that is reached only that way is NOT proven absent from the containers; it is accepted because it is in the
    reviewed allow-list of host-orchestration modules, and it is listed with its import chain in the record (`relied_on_allow_list`)."""
    roots = {side["name"]: side["root"] / "source" for side in (a, b)}
    sliced = {module for module in map(_repo_module, git_files) if module}
    eager = {name: container_reach(root, sliced, eager_only=True) for name, root in roots.items()}
    full = {name: container_reach(root, sliced) for name, root in roots.items()}
    identical, relied = {}, {}
    for repo_path in git_files:
        module = _repo_module(repo_path)
        if module is None:
            continue
        in_eager = [reach[module] for reach in eager.values() if module in reach]
        in_full = [reach[module] for reach in full.values() if module in reach]
        if not in_full:
            continue
        if repo_path not in ALLOWED_FILES:
            refuse("CONTAINER_REACH", f"{repo_path} is changed and reached by a container but is not an allow-listed module")
        if in_eager and any(entry["whole"] for entry in in_eager):
            refuse("CONTAINER_REACH", f"{repo_path} is changed and a container imports the module as a whole when it starts")
        names = set().union(*(entry["names"] for entry in (in_eager or in_full)))
        slices = []
        for side in (a, b):
            try:
                slices.append(_definition_slice(ast.parse((side["root"] / "source" / repo_path).read_bytes()), names))
            except (OSError, SyntaxError) as error:
                refuse("CONTAINER_REACH", f"{repo_path} cannot be compared in {side['name']}: {error}")
        if not in_eager:
            relied[repo_path] = dict(imported_names=sorted(names), imported_slice_identical=slices[0] == slices[1],
                                     whole_module_use=any(entry["whole"] for entry in in_full),
                                     chains={name: _chain(reach, module) for name, reach in full.items() if module in reach})
            continue
        if slices[0] != slices[1]:
            refuse("CONTAINER_REACH", f"{repo_path}: what a container imports from it when it starts ({sorted(names)}) or its import-time code "
                                      "differs between the two snapshots")
        identical[repo_path] = dict(imported_names=sorted(names), identical_definitions=sorted(slices[0][1]))
    return dict(entries=list(CONTAINER_ENTRIES), eager_modules={name: len(reach) for name, reach in eager.items()},
                reachable_modules={name: len(reach) for name, reach in full.items()},
                changed_modules_imported_at_start_and_identical=identical, relied_on_allow_list=relied,
                analysis="static: import statements and literal module-name strings; eager = outside function bodies, lazy = inside; "
                         "a lazy-only reach is not proven absent and rests on the reviewed allow-list")


# ---- the whole rule -------------------------------------------------------------------------------------------------------------

def verify_equivalence(proof_path, repo, parsed: list, *, workers: int = 4) -> dict:
    """Everything the merge needs to accept differing `mount_build`/`image_source_install`; `parsed` holds per source `name`, `identity`
    and `mount_inputs` (an inputs root or None). Returns the record for the merge manifest."""
    if proof_path is None:
        refuse("MISSING", "the identities differ in mount_build/image_source_install and no --identity-equivalence proof was given")
    if repo is None:
        refuse("PROOF_INVALID", "no git repository to recompute the proof in")
    document, proof_sha = verify_proof(proof_path, repo)
    commits = {}
    for item in parsed:
        commits[item["name"]] = source_commit(item["identity"], item["name"])
    if len(set(commits.values())) != len(parsed):
        refuse("TREE_MISMATCH", "two sources hold the same mounted commit although their identities differ")
    images = [base_images(item["identity"]) for item in parsed]
    if any(image != images[0] for image in images[1:]):
        refuse("TREE_MISMATCH", "the base image digests of the sources differ")
    reference = document["reference_commit"]
    if reference not in commits.values():
        refuse("COMMIT_MISMATCH", f"the proof's reference commit {reference} is the commit of no source ({sorted(commits.values())})")
    proof_mounts = {entry["commit"] for entry in document["comparisons"] if entry["role"] == "mount_build"}
    if proof_mounts != set(commits.values()) - {reference}:
        refuse("COMMIT_MISMATCH", f"the mounted commits of the proof ({sorted(proof_mounts | {reference})}) are not those of the sources "
                                  f"({sorted(commits.values())})")
    sides = {}
    for item in parsed:
        if item.get("mount_inputs") is None:
            refuse("INPUTS_MISSING", f"{item['name']} has no --mount-inputs (the sealed inputs root of its run)")
        sides[commits[item["name"]]] = load_mount_inputs(item["mount_inputs"], item["identity"], commits[item["name"]], item["name"],
                                                         workers=workers)
    by_commit = {entry["commit"]: entry for entry in document["comparisons"]}
    host_checked = []
    for entry in document["comparisons"]:
        if entry["role"] == "host_code":
            owners = [side for side in sides.values() if entry["commit"] in side["document"].get("host_code", "")]
            if not owners:
                refuse("COMMIT_MISMATCH", f"the host-code commit {entry['commit']} of the proof is named by no source's MOUNT-INPUTS host_code record")
            host_checked.append(dict(commit=entry["commit"], named_by=[side["name"] for side in owners]))
    trees = []
    for commit, side in sorted(sides.items()):
        if commit == reference:
            continue
        files = by_commit[commit]["changed_files"]
        base = sides[reference]
        trees.append(dict(source=side["name"], against=base["name"], commit=commit, differences=compare_trees(base, side, files),
                          container_side=verify_container_side(base, side, files)))
    return dict(allow_list_version=ALLOW_LIST_VERSION, proof_path=str(Path(proof_path).resolve()), proof_sha256=proof_sha,
                reference_commit=reference, git_command=GIT_COMMAND,
                comparisons=[dict(role=e["role"], commit=e["commit"], changed_files=e["changed_files"],
                                  changed_files_sha256=e["changed_files_sha256"]) for e in document["comparisons"]],
                sources={side["name"]: dict(commit=commit, inputs_root=side["inputs_root"], tree_manifest_sha256=side["tree_manifest_sha256"],
                                            mount_inputs_sha256=side["mount_inputs_sha256"]) for commit, side in sides.items()},
                host_code_commits=host_checked, trees=trees,
                unverified=dict(note="the generated type-support .c files under include/ are accepted by path only (never compiled or run in a container)",
                                count=sum(tree["differences"]["generated"]["count"] for tree in trees)))
