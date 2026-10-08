"""A content-bound memo of the independent fresh-process QC (CP-3456).

`episode_qc.recompute_native_qc` is a pure function of files: the sealed episode, the run scope, the frozen inputs and the Teacher
manifest. For a 100 s episode it takes about five minutes (the seal, the physical audit and the native QC). The offline processor runs
it in a fresh interpreter right after it sealed the episode. The run's result gates (the Worker's ResultStore and the Coordinator's
`ActCollectionResultVerifier`) would otherwise repeat it three or four times, the Coordinator's twice under its state lock, against a
ten second result acknowledgement.

The memo records that this exact recomputation succeeded on this exact content. It is a SHA-256 fingerprint of every file of the
episode (path, size, digest), of the scope, the frozen inputs and the Teacher manifest, bound to the QC rule version and to the
canonical report. A gate that is configured to trust it accepts it only when all of that matches what is on disk now; any other case
recomputes in full. Nothing that reads back a finished run (`verify_coordinator_commit`, `act_first_episode qc`, `verify-commit`)
trusts it.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

MEMO_NAME = "qc-verification-memo.json"
MEMO_KIND = "ACT_QC_VERIFICATION_MEMO"
MEMO_SCHEMA = 2
#: The modules whose source decides a QC verdict: the QC itself, the audit and seal readers, the physical-audit and native-endpoint
#: rules, the scene-association rules and the frozen-input verification. A memo written by other source than the reader's own is
#: not trusted (CP-3457), whatever `QC_RULE_VERSION` says.
CODE_MODULES = ("episode_qc", "episode_audit", "recorder", "native_endpoints", "raw_physics_chunks", "scene_association",
                "execution_snapshot", "collection_boundaries", "first_episode_inputs", "qc_memo")
COVERS = ("episode_seal", "physical_audit", "native_qc")
_TEACHER_RELATIVE = Path("dynamic") / "dynamic-execute-manifest.json"
_CHUNK = 1 << 20
#: (resolved argument paths) -> (stat signature of every file, fingerprint); valid only while every signature is unchanged
_CACHE: dict = {}


def _file_digest(path) -> str:
    digest = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        while True:
            block = os.read(descriptor, _CHUNK)
            if not block:
                break
            digest.update(block)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _regular_files(root: Path) -> list:
    """Every file under `root`, sorted by relative path; a symbolic link or any non-regular entry is refused."""
    found = []
    for directory, names, files in os.walk(root, followlinks=False):
        for name in sorted(names):
            if os.path.islink(os.path.join(directory, name)):
                raise ValueError("QC_MEMO_SYMLINK_IN_EPISODE")
        for name in sorted(files):
            path = Path(directory, name)
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("QC_MEMO_NON_REGULAR_FILE")
            found.append((path.relative_to(root).as_posix(), path, info))
    found.sort(key=lambda item: item[0])
    return found


def _teacher_path(episode_root: Path, teacher_manifest):
    return Path(teacher_manifest) if teacher_manifest is not None else Path(episode_root).parent / _TEACHER_RELATIVE


def _signature(items) -> tuple:
    return tuple((name, info.st_size, info.st_mtime_ns, info.st_ino) for name, _path, info in items)


def fingerprint(*, episode_root, scope, inputs_manifest, teacher_manifest=None) -> str:
    """SHA-256 over the content of the episode tree, the scope, the frozen inputs and the Teacher manifest (absent is a value)."""
    root = Path(os.path.realpath(episode_root))
    episode_items = _regular_files(root)
    external = []
    for label, path in (("scope", Path(scope)), ("inputs", Path(inputs_manifest)),
                        ("teacher", _teacher_path(root, teacher_manifest))):
        try:
            info = path.lstat()
        except FileNotFoundError:
            external.append((label, path, None))
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("QC_MEMO_NON_REGULAR_FILE")
        external.append((label, path, info))
    signature = (_signature(episode_items),
                 tuple((label, None if info is None else (info.st_size, info.st_mtime_ns, info.st_ino))
                       for label, _path, info in external))
    key = (str(root), *(str(path) for _label, path, _info in external))
    cached = _CACHE.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]
    digest = hashlib.sha256()
    digest.update(b"ACT_QC_MEMO_FINGERPRINT_V1\n")
    for name, path, _info in episode_items:
        digest.update(f"episode\0{name}\0{_info.st_size}\0{_file_digest(path)}\n".encode())
    for label, path, info in external:
        digest.update(f"{label}\0{'ABSENT' if info is None else _file_digest(path)}\n".encode())
    result = digest.hexdigest()
    _CACHE[key] = (signature, result)
    return result


_CODE_DIGEST: list = []


def code_digest() -> str:
    """SHA-256 over the source files of `CODE_MODULES` (name and bytes), computed once per process."""
    if not _CODE_DIGEST:
        digest = hashlib.sha256(b"ACT_QC_CODE_DIGEST_V1\n")
        package = Path(__file__).resolve().parent
        for name in CODE_MODULES:
            digest.update(f"{name}\0".encode())
            digest.update((package / f"{name}.py").read_bytes())
            digest.update(b"\n")
        _CODE_DIGEST.append(digest.hexdigest())
    return _CODE_DIGEST[0]


def _canonical_report_sha256(report) -> str:
    from .episode_qc import _report_canonical

    return hashlib.sha256(_report_canonical(report)).hexdigest()


def memo_path(report_path) -> Path:
    return Path(report_path).with_name(MEMO_NAME)


def write_memo(report_path, report, *, episode_root, scope, inputs_manifest, teacher_manifest=None) -> Path:
    """Write the memo beside `report_path` for a PASS report; the fresh-process QC calls this after it published the report."""
    if report.get("status") != "PASS":
        raise ValueError("QC_MEMO_REQUIRES_PASS")
    document = {"kind": MEMO_KIND, "schema_version": MEMO_SCHEMA, "rule_version": report["rule_version"], "covers": list(COVERS),
                "code_digest": code_digest(), "report_sha256": _canonical_report_sha256(report),
                "fingerprint": fingerprint(episode_root=episode_root, scope=scope, inputs_manifest=inputs_manifest,
                                           teacher_manifest=teacher_manifest)}
    target = memo_path(report_path)
    staging = target.with_name(f".{target.name}.{os.getpid()}.pending")
    with open(staging, "wb") as stream:
        stream.write((json.dumps(document, sort_keys=True, indent=1) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staging, target)
    return target


def memo_matches(report_path, report, *, episode_root, scope, inputs_manifest, teacher_manifest=None) -> bool:
    """True only if a memo beside `report_path` records this report, this QC rule version and the content on disk now."""
    from .episode_qc import QC_RULE_VERSION

    try:
        if report.get("status") != "PASS" or report.get("rule_version") != QC_RULE_VERSION:
            return False
        descriptor = os.open(memo_path(report_path), os.O_RDONLY | os.O_NOFOLLOW)
        try:
            document = json.loads(os.read(descriptor, 1 << 16))
        finally:
            os.close(descriptor)
        return (type(document) is dict
                and document.get("kind") == MEMO_KIND and document.get("schema_version") == MEMO_SCHEMA
                and document.get("rule_version") == QC_RULE_VERSION and document.get("covers") == list(COVERS)
                and document.get("code_digest") == code_digest()
                and document.get("report_sha256") == _canonical_report_sha256(report)
                and document.get("fingerprint") == fingerprint(episode_root=episode_root, scope=scope,
                                                                inputs_manifest=inputs_manifest,
                                                                teacher_manifest=teacher_manifest))
    except (OSError, ValueError, TypeError, KeyError):
        return False
