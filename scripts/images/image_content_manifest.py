#!/usr/bin/env python3
"""Content manifest of a container image: the merged root filesystem, computed outside the container.

The image is read from a `docker save` tar (a file or stdin), never from a running container. The layers are merged in order
by the OCI rules and every path of the final root filesystem gets one entry (type, mode, uid, gid, and size plus sha256 for a
file, the target for a symlink, major and minor for a device). Mtimes, atimes and ctimes are not recorded, so two builds of the
same content have the same `content_sha256` even when their timestamps differ.

    image_content_manifest.py manifest <tar|-> --exclusions FILE --output FILE
    image_content_manifest.py diff A.json B.json
    image_content_manifest.py check-no-pyc MANIFEST [--base BASE_MANIFEST]
    image_content_manifest.py check-no-project-code MANIFEST
    image_content_manifest.py tree DIR --output FILE

`tree` applies the same rule to a directory (the install and source trees that are mounted into a container): the same entry fields
without owners, and a `.pyc` file or `__pycache__` directory is a refusal, not something skipped.

Standard library only. See scripts/images/README.md.
"""
from __future__ import annotations

import argparse
import copy
import csv
import datetime
import fnmatch
import hashlib
import io
import json
import os
import posixpath
import re
import stat
import sys
import tarfile

SCHEMA = "so101-image-content-manifest/1"
CONFIG_FIELDS = ("Entrypoint", "Cmd", "Env", "WorkingDir", "User", "ExposedPorts", "Volumes", "Labels", "Shell")
# No exclusion rule may match inside, or at, one of these trees.
PROTECTED_TREES = ("/act", "/opt/ros", "/usr/lib", "/usr/bin", "/act/venv")
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_TEXT_BYTES = 16 * 1024 * 1024
CHUNK = 1024 * 1024
WHITEOUT_PREFIX = ".wh."
OPAQUE_NAME = ".wh..wh..opq"
DPKG_LIST = re.compile(r"^/var/lib/dpkg/info/[^/]+\.list$")
PIP_RECORD = re.compile(r"^(/.*)/([^/]+)\.dist-info/RECORD$")
FILE_TYPES = ("file", "hardlink")


class ImageManifestError(Exception):
    """Base of every refusal of this tool; the message names the cause."""


class ArchiveFormatError(ImageManifestError):
    """The tar is not a recognizable docker-archive or OCI image layout."""


class AmbiguousImageError(ImageManifestError):
    """The archive holds no single image (zero or several platform manifests)."""


class MissingBlobError(ImageManifestError):
    """The manifest names a config or layer that is not in the archive."""


class LayerParseError(ImageManifestError):
    """A layer could not be read (unsupported compression or a damaged tar)."""


class DanglingHardlinkError(ImageManifestError):
    """A hard link names a target that exists in no layer."""


class ExclusionError(ImageManifestError):
    """The exclusion file is malformed, or a rule could match inside a protected tree."""


class ManifestIntegrityError(ImageManifestError):
    """A manifest file is unreadable or its content does not match its content_sha256."""


# --- canonical JSON ---------------------------------------------------------------------------------------------------

def _reject_floats(value, where="$"):
    if isinstance(value, float):
        raise ImageManifestError(f"float at {where}: the manifest holds integers and strings only")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_floats(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_floats(item, f"{where}[{index}]")


def canonical_bytes(value) -> bytes:
    """Sorted keys, no whitespace, ASCII-escaped (valid UTF-8, and safe for names that are not valid UTF-8)."""
    _reject_floats(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- reading the archive ----------------------------------------------------------------------------------------------

def normalize_path(name: str) -> str:
    parts = [part for part in name.split("/") if part not in ("", ".")]
    return "/" + "/".join(parts)


def archive_name(name: str) -> str:
    return "/".join(part for part in name.split("/") if part not in ("", "."))


class _Prefixed(io.RawIOBase):
    """A readable that returns `prefix` first and then the rest of `raw` (a peeked stream, put back)."""

    def __init__(self, prefix: bytes, raw):
        self._prefix = prefix
        self._raw = raw

    def readable(self):
        return True

    def readinto(self, buffer):
        if self._prefix:
            count = min(len(buffer), len(self._prefix))
            buffer[:count] = self._prefix[:count]
            self._prefix = self._prefix[count:]
            return count
        data = self._raw.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)


class _Layer:
    """What one layer tar contributes, before merging."""

    def __init__(self):
        self.entries = {}
        self.whiteouts = []
        self.opaque = []


def _member_entry(member, pax):
    entry = {"mode": "%04o" % (member.mode & 0o7777), "uid": member.uid, "gid": member.gid}
    if member.isdir():
        entry["type"] = "dir"
    elif member.issym():
        entry["type"] = "symlink"
        entry["link"] = member.linkname
    elif member.islnk():
        entry["type"] = "hardlink"
        entry["target"] = normalize_path(member.linkname)
    elif member.ischr() or member.isblk():
        entry["type"] = "char" if member.ischr() else "block"
        entry["major"] = member.devmajor
        entry["minor"] = member.devminor
    elif member.isfifo():
        entry["type"] = "fifo"
    elif member.isreg():
        entry["type"] = "file"
    else:
        raise LayerParseError(f"unsupported tar member type {member.type!r} at {member.name}")
    xattrs = {key[len("SCHILY.xattr."):]: sha256_hex(value.encode("utf-8", "surrogateescape"))
              for key, value in pax.items() if key.startswith("SCHILY.xattr.")}
    if xattrs:
        entry["xattrs"] = xattrs
    return entry


def read_layer(fileobj, label: str) -> _Layer:
    layer = _Layer()
    try:
        archive = tarfile.open(fileobj=fileobj, mode="r|*")
        for member in archive:
            path = normalize_path(member.name)
            base = posixpath.basename(path)
            parent = posixpath.dirname(path)
            if base == OPAQUE_NAME:
                layer.opaque.append(parent)
                continue
            if base.startswith(".wh..wh."):
                continue                                       # other reserved names (.wh..wh.plnk, .wh..wh.aufs): ignored
            if base.startswith(WHITEOUT_PREFIX):
                layer.whiteouts.append(posixpath.join(parent, base[len(WHITEOUT_PREFIX):]))
                continue
            entry = _member_entry(member, member.pax_headers)
            if entry["type"] == "file":
                digest = hashlib.sha256()
                keep = bool(DPKG_LIST.match(path) or PIP_RECORD.match(path)) and member.size <= MAX_TEXT_BYTES
                text = bytearray()
                stream = archive.extractfile(member)
                size = 0
                while True:
                    chunk = stream.read(CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    digest.update(chunk)
                    if keep:
                        text += chunk
                entry["size"] = size
                entry["sha256"] = digest.hexdigest()
                if keep:
                    entry["_text"] = bytes(text)
            layer.entries[path] = entry
    except ImageManifestError:
        raise
    except (tarfile.TarError, EOFError, OSError, ValueError, UnicodeError) as error:
        raise LayerParseError(f"layer {label} could not be read: {error}") from error
    return layer


def read_archive(fileobj):
    """One pass over the outer tar. Returns (json members by name, layers by name, unreadable layers by name)."""
    documents, layers, failures = {}, {}, {}
    try:
        outer = tarfile.open(fileobj=fileobj, mode="r|*")
        for member in outer:
            if not member.isreg():
                continue
            name = archive_name(member.name)
            stream = outer.extractfile(member)
            head = stream.read(512)
            if head.lstrip()[:1] in (b"{", b"["):
                if member.size > MAX_JSON_BYTES:
                    raise ArchiveFormatError(f"JSON member {name} is larger than {MAX_JSON_BYTES} bytes")
                documents[name] = head + stream.read()
                continue
            if member.size == 0:
                layers[name] = _Layer()
                continue
            if len(head) < 512 and not head.startswith(b"\x1f\x8b"):
                continue                                       # too small to be a layer (VERSION files and the like)
            try:
                layers[name] = read_layer(_Prefixed(head, stream), name)
            except LayerParseError as error:
                failures[name] = str(error)
    except ImageManifestError:
        raise
    except (tarfile.TarError, EOFError, OSError, ValueError) as error:
        raise ArchiveFormatError(f"the input is not a readable tar archive: {error}") from error
    return documents, layers, failures


def _json(documents, name, what):
    if name not in documents:
        raise MissingBlobError(f"{what} {name} is not in the archive")
    try:
        return json.loads(documents[name])
    except ValueError as error:
        raise ArchiveFormatError(f"{what} {name} is not valid JSON: {error}") from error


def _blob_name(digest: str) -> str:
    algorithm, _, hexdigest = digest.partition(":")
    return f"blobs/{algorithm}/{hexdigest}"


def _oci_candidates(documents, descriptor, seen):
    """Image manifests reachable from an index descriptor, as (config blob name, [layer blob names])."""
    platform = descriptor.get("platform") or {}
    if platform.get("os") == "unknown" or platform.get("architecture") == "unknown":
        return []                                               # attestation manifests
    name = _blob_name(descriptor.get("digest", ""))
    if name in seen or name not in documents:
        return []
    seen.add(name)
    document = _json(documents, name, "manifest")
    media_type = document.get("mediaType", descriptor.get("mediaType", ""))
    if "manifests" in document and ("index" in media_type or "list" in media_type or "config" not in document):
        found = []
        for child in document["manifests"]:
            found += _oci_candidates(documents, child, seen)
        return found
    if "config" not in document or "layers" not in document:
        raise ArchiveFormatError(f"manifest {name} has no config and layers")
    return [(_blob_name(document["config"]["digest"]), [_blob_name(layer["digest"]) for layer in document["layers"]])]


def select_image(documents):
    """Return (config blob name, layer blob names) for the single image in the archive."""
    if "manifest.json" in documents:
        listing = _json(documents, "manifest.json", "docker-archive manifest")
        if not isinstance(listing, list) or len(listing) != 1:
            raise AmbiguousImageError(f"manifest.json lists {len(listing) if isinstance(listing, list) else 'no'} images; save exactly one")
        item = listing[0]
        if "Config" not in item or "Layers" not in item:
            raise ArchiveFormatError("manifest.json entry has no Config and Layers")
        return archive_name(item["Config"]), [archive_name(layer) for layer in item["Layers"]]
    if "index.json" in documents:
        index = _json(documents, "index.json", "OCI index")
        found, seen = [], set()
        for descriptor in index.get("manifests", []):
            found += _oci_candidates(documents, descriptor, seen)
        if len(found) != 1:
            raise AmbiguousImageError(f"index.json resolves to {len(found)} image manifests in this archive; save exactly one platform")
        return found[0]
    raise ArchiveFormatError("the archive has neither manifest.json (docker-archive) nor index.json (OCI layout)")


# --- merging the layers -----------------------------------------------------------------------------------------------

def _ancestors(path):
    while True:
        path = posixpath.dirname(path)
        if path in ("", "/"):
            return
        yield path


def _resolve_hardlink(path, entry, layer, state):
    target, seen = entry["target"], {path}
    while True:
        if target in seen:
            raise DanglingHardlinkError(f"hard link {path} loops through {target}")
        seen.add(target)
        candidate = layer.entries.get(target)
        if candidate is None:
            candidate = state.get(target)
        if candidate is None:
            raise DanglingHardlinkError(f"hard link {path} names {entry['target']}, which is in no layer")
        if candidate["type"] == "hardlink" and target in layer.entries:
            target = candidate["target"]
            continue
        break
    resolved = {key: copy.deepcopy(value) for key, value in candidate.items() if key not in ("type", "target")}
    resolved["type"] = "hardlink"
    resolved["target"] = entry["target"]
    return resolved


def merge_layers(layers):
    state = {}
    for layer in layers:
        resolved = {}
        for path, entry in layer.entries.items():
            resolved[path] = _resolve_hardlink(path, entry, layer, state) if entry["type"] == "hardlink" else entry
        whole = set(layer.whiteouts)                            # the path and its subtree
        below = set(layer.opaque)                               # the subtree only
        for path, entry in resolved.items():
            old = state.get(path)
            if old is not None and old["type"] == "dir" and entry["type"] != "dir":
                below.add(path)                                 # a type change drops the old children
        if whole or below:
            for path in [key for key in state
                         if key in whole or any(parent in whole or parent in below for parent in _ancestors(key))]:
                del state[path]
        state.update(resolved)
    return state


# --- exclusions -------------------------------------------------------------------------------------------------------

def glob_regex(glob: str):
    out, index = [], 0
    while index < len(glob):
        char = glob[index]
        if glob.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif glob.startswith("**", index):
            out.append(".*")
            index += 2
        elif char == "*":
            out.append("[^/]*")
            index += 1
        elif char == "?":
            out.append("[^/]")
            index += 1
        elif char == "[":
            end = glob.find("]", index + 2)
            if end < 0:
                out.append(re.escape(char))
                index += 1
            else:
                body = glob[index + 1:end]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                index = end + 1
        else:
            out.append(re.escape(char))
            index += 1
    return re.compile("^" + "".join(out) + "$")


def could_match_inside(glob: str, tree: str) -> bool:
    """True when `glob` can match `tree` itself or a path inside it (conservative)."""
    patterns = [part for part in glob.split("/") if part]
    names = [part for part in tree.split("/") if part]

    def walk(gi, ni):
        if ni == len(names):
            return True
        if gi == len(patterns):
            return False
        if "**" in patterns[gi]:
            return walk(gi + 1, ni) or walk(gi, ni + 1)
        return fnmatch.fnmatchcase(names[ni], patterns[gi]) and walk(gi + 1, ni + 1)

    return walk(0, 0)


def load_exclusions(path):
    """Parse `<glob> | <reason> | <date added>` lines; refuse a rule that could reach a protected tree."""
    rules, seen = [], set()
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError as error:
        raise ExclusionError(f"cannot read the exclusion file {path}: {error}") from error
    for number, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = [field.strip() for field in line.split("|")]
        if len(fields) != 3 or not all(fields):
            raise ExclusionError(f"{path}:{number}: expected '<glob> | <reason> | <date added>'")
        glob, reason, added = fields
        if not glob.startswith("/"):
            raise ExclusionError(f"{path}:{number}: the glob {glob!r} must start with /")
        try:
            datetime.date.fromisoformat(added)
        except ValueError as error:
            raise ExclusionError(f"{path}:{number}: the date {added!r} is not YYYY-MM-DD") from error
        if glob in seen:
            raise ExclusionError(f"{path}:{number}: the glob {glob!r} is listed twice")
        seen.add(glob)
        for tree in PROTECTED_TREES:
            if could_match_inside(glob, tree):
                raise ExclusionError(f"{path}:{number}: the glob {glob!r} could match inside the protected tree {tree}")
        rules.append({"glob": glob, "reason": reason, "added": added, "regex": glob_regex(glob)})
    return rules


# --- building the manifest --------------------------------------------------------------------------------------------

def _config_subset(config):
    section = config.get("config") or {}
    return {field: section.get(field) for field in CONFIG_FIELDS}


def _attribution(entries):
    dpkg, pip = {}, {}
    for path, entry in entries.items():
        text = entry.get("_text")
        if text is None:
            continue
        if DPKG_LIST.match(path):
            package = posixpath.basename(path)[:-len(".list")]
            dpkg[package] = sorted({line.strip() for line in text.decode("utf-8", "replace").splitlines()
                                    if line.strip() not in ("", "/.")})
            continue
        match = PIP_RECORD.match(path)
        if match:
            site, dist = match.group(1), match.group(2)
            rows = csv.reader(io.StringIO(text.decode("utf-8", "replace")))
            names = {posixpath.normpath(posixpath.join(site, row[0])) for row in rows if row and row[0]}
            pip[f"{site}/{dist}.dist-info"] = sorted(names)
    return {"dpkg": dpkg, "pip": pip}


def build_manifest(documents, layers, failures, rules):
    config_name, layer_names = select_image(documents)
    config = _json(documents, config_name, "image config")
    ordered = []
    for name in layer_names:
        if name in failures:
            raise LayerParseError(failures[name])
        if name not in layers:
            raise MissingBlobError(f"layer {name} is not in the archive")
        ordered.append(layers[name])
    merged = merge_layers(ordered)
    attribution = _attribution(merged)
    entries, excluded, counts = {}, {}, {}
    for path, entry in merged.items():
        entry = {key: value for key, value in entry.items() if key != "_text"}
        rule = next((rule for rule in rules if rule["regex"].match(path)), None)
        if rule is None:
            entries[path] = entry
        else:
            excluded[path] = {"rule": rule["glob"], "entry_sha256": sha256_hex(canonical_bytes(entry))}
            counts[rule["glob"]] = counts.get(rule["glob"], 0) + 1
    content = {"schema": SCHEMA, "config": _config_subset(config), "entries": entries,
               "exclusion_globs": sorted(rule["glob"] for rule in rules)}
    return {"tool": "image_content_manifest.py", "content": content, "content_sha256": sha256_hex(canonical_bytes(content)),
            "excluded": {"counts_by_rule": counts, "entries": excluded}, "attribution": attribution}


def load_manifest(path):
    try:
        with open(path, "rb") as handle:
            document = json.loads(handle.read())
        content = document["content"]
        claimed = document["content_sha256"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ManifestIntegrityError(f"{path} is not an image content manifest: {error!r}") from error
    if sha256_hex(canonical_bytes(content)) != claimed:
        raise ManifestIntegrityError(f"{path}: the content does not match its content_sha256 {claimed}")
    return document


# --- commands ---------------------------------------------------------------------------------------------------------

def cmd_manifest(args):
    rules = load_exclusions(args.exclusions)
    source = sys.stdin.buffer if args.archive == "-" else open(args.archive, "rb")
    try:
        documents, layers, failures = read_archive(source)
    finally:
        if source is not sys.stdin.buffer:
            source.close()
    manifest = build_manifest(documents, layers, failures, rules)
    temporary = args.output + ".partial"
    with open(temporary, "wb") as handle:
        handle.write(canonical_bytes(manifest))
    os.replace(temporary, args.output)
    counts = manifest["excluded"]["counts_by_rule"]
    print(f"entries={len(manifest['content']['entries'])} excluded={sum(counts.values())} "
          f"excluded_by_rule={json.dumps(counts, sort_keys=True)}", file=sys.stderr)
    print(manifest["content_sha256"])
    return 0


def _packages(attribution):
    owners = {}
    for kind in ("dpkg", "pip"):
        for package, paths in attribution.get(kind, {}).items():
            label = f"{kind}:{package}" if kind == "dpkg" else f"pip:{posixpath.basename(package)[:-len('.dist-info')]}"
            for path in paths:
                owners.setdefault(path, set()).add(label)
    return owners


def _owner_text(path, owners):
    names = sorted(set().union(*(side.get(path, set()) for side in owners)))
    if not names:
        return ""
    shown = ",".join(names[:3]) + (f"+{len(names) - 3}" if len(names) > 3 else "")
    return f"  [{shown}]"


def cmd_diff(args):
    first, second = load_manifest(args.a), load_manifest(args.b)
    a, b = first["content"], second["content"]
    owners = (_packages(first.get("attribution", {})), _packages(second.get("attribution", {})))
    lines, differing = [], 0
    config_keys = sorted(k for k in set(a["config"]) | set(b["config"]) if a["config"].get(k) != b["config"].get(k))
    if config_keys:
        lines.append("== image config ==")
        for key in config_keys:
            lines += [f"M {key}", f"  A: {canonical_bytes(a['config'].get(key)).decode()}", f"  B: {canonical_bytes(b['config'].get(key)).decode()}"]
        differing += len(config_keys)
    if a.get("exclusion_globs") != b.get("exclusion_globs"):
        lines.append("== exclusion globs differ ==")
        lines += [f"  A: {a.get('exclusion_globs')}", f"  B: {b.get('exclusion_globs')}"]
        differing += 1
    paths = sorted(p for p in set(a["entries"]) | set(b["entries"]) if a["entries"].get(p) != b["entries"].get(p))
    groups = {}
    for path in paths:
        groups.setdefault("/" + path.split("/")[1] if path != "/" else "/", []).append(path)
    packages = {}
    for top in sorted(groups):
        lines.append(f"== {top} ({len(groups[top])} differing) ==")
        for path in groups[top]:
            left, right = a["entries"].get(path), b["entries"].get(path)
            mark = "M" if left is not None and right is not None else ("+" if left is None else "-")
            owner = _owner_text(path, owners)
            lines.append(f"{mark} {path}{owner}")
            lines.append("  A: " + (canonical_bytes(left).decode() if left is not None else "(absent)"))
            lines.append("  B: " + (canonical_bytes(right).decode() if right is not None else "(absent)"))
            key = owner.strip()[1:-1] if owner else "(unattributed)"
            packages[key] = packages.get(key, 0) + 1
    differing += len(paths)
    if packages:
        lines.append("== by package ==")
        lines += [f"{count:6d}  {name}" for name, count in sorted(packages.items(), key=lambda item: (-item[1], item[0]))]
    lines.append(f"differing={differing} content_sha256_a={first['content_sha256']} content_sha256_b={second['content_sha256']}")
    print("\n".join(lines))
    return 0 if differing == 0 else 1


def _pyc_paths(content):
    return sorted(p for p, e in content["entries"].items() if p.endswith(".pyc") and e["type"] in FILE_TYPES)


def cmd_check_no_pyc(args):
    pyc = _pyc_paths(load_manifest(args.manifest)["content"])
    under_act = [p for p in pyc if p.startswith("/act/")]
    under_venv = [p for p in under_act if p.startswith("/act/venv/")]
    base = set(_pyc_paths(load_manifest(args.base)["content"])) if args.base else None
    site = [p for p in pyc if "/site-packages/" in p and not p.startswith("/act/") and (base is None or p not in base)]
    violations = under_act + site
    print(f"pyc_under_act={len(under_act)} pyc_under_act_venv={len(under_venv)} "
          f"pyc_site_packages_added={len(site)} base={'given' if base is not None else 'not given (every site-packages pyc counts)'}")
    for path in violations[:args.limit]:
        print(f"pyc: {path}")
    if len(violations) > args.limit:
        print(f"... {len(violations) - args.limit} more")
    return 1 if violations else 0


PROJECT_CODE_ROOTS = ("/act/", "/opt/", "/usr/lib/", "/usr/local/", "/root/", "/home/")


def project_code_paths(content):
    """Files under the runtime trees that have a path component starting with `so101` (a package, a dist-info, a source copy)."""
    return sorted(path for path, entry in content["entries"].items()
                  if entry["type"] in FILE_TYPES and path.startswith(PROJECT_CODE_ROOTS)
                  and any(part.lower().startswith("so101") for part in path.split("/")))


def cmd_check_no_project_code(args):
    found = project_code_paths(load_manifest(args.manifest)["content"])
    print(f"project_paths={len(found)}")
    for path in found[:args.limit]:
        print(f"project: {path}")
    if len(found) > args.limit:
        print(f"... {len(found) - args.limit} more")
    return 1 if found else 0


TREE_SCHEMA = "so101-tree-content-manifest/1"


def tree_entries(root):
    """Entries of a directory tree, keyed by the path relative to it: type, mode, and size plus sha256 or the symlink target.
    Raises ImageManifestError for anything but files, directories and symlinks. Returns (entries, bytecode paths)."""
    entries, bytecode = {}, []
    root = os.path.abspath(root)
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        relative_directory = os.path.relpath(directory, root)
        for name in sorted(dirnames + filenames):
            full = os.path.join(directory, name)
            relative = name if relative_directory == "." else posixpath.join(relative_directory.replace(os.sep, "/"), name)
            info = os.lstat(full)
            mode = format(stat.S_IMODE(info.st_mode), "04o")
            if name == "__pycache__" or name.endswith(".pyc"):
                bytecode.append(relative)
            if stat.S_ISLNK(info.st_mode):
                entries[relative] = {"type": "symlink", "target": os.readlink(full)}
            elif stat.S_ISDIR(info.st_mode):
                entries[relative] = {"type": "dir", "mode": mode}
            elif stat.S_ISREG(info.st_mode):
                digest = hashlib.sha256()
                with open(full, "rb") as stream:
                    for chunk in iter(lambda: stream.read(CHUNK), b""):
                        digest.update(chunk)
                entries[relative] = {"type": "file", "mode": mode, "size": info.st_size, "sha256": digest.hexdigest()}
            else:
                raise ImageManifestError(f"{relative}: not a file, directory or symlink")
    return entries, sorted(bytecode)


def cmd_tree(args):
    entries, bytecode = tree_entries(args.directory)
    if bytecode:
        print(f"bytecode in the tree: {len(bytecode)} path(s)")
        for path in bytecode[:args.limit]:
            print(f"pyc: {path}")
        return 1
    document = {"schema": TREE_SCHEMA, "entries": entries, "tree_sha256": sha256_hex(canonical_bytes({"entries": entries}))}
    with open(args.output, "w") as stream:
        stream.write(json.dumps(document, sort_keys=True, indent=1) + "\n")
    print(f"tree_sha256 {document['tree_sha256']} ({len(entries)} entries)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    manifest = commands.add_parser("manifest", help="write the content manifest of a docker save tar; prints content_sha256")
    manifest.add_argument("archive", help="docker save tar (plain or gzip), or - for stdin")
    manifest.add_argument("--exclusions", required=True, help="exclusion file (see image-content-exclusions.txt)")
    manifest.add_argument("--output", required=True, help="manifest JSON to write")
    manifest.set_defaults(handler=cmd_manifest)
    diff = commands.add_parser("diff", help="list the paths that differ between two manifests (exit 1 when any)")
    diff.add_argument("a")
    diff.add_argument("b")
    diff.set_defaults(handler=cmd_diff)
    pyc = commands.add_parser("check-no-pyc", help="fail when a .pyc exists under /act or is added in a site-packages directory")
    pyc.add_argument("manifest")
    pyc.add_argument("--base", help="base image manifest: site-packages .pyc files present there are not flagged")
    pyc.add_argument("--limit", type=int, default=50, help="paths to list (default 50)")
    pyc.set_defaults(handler=cmd_check_no_pyc)
    project = commands.add_parser("check-no-project-code", help="fail when a dependency base holds so101_* code (packages, dist-info, source copies)")
    project.add_argument("manifest")
    project.add_argument("--limit", type=int, default=50)
    project.set_defaults(handler=cmd_check_no_project_code)
    tree = commands.add_parser("tree", help="write the content manifest of a directory tree; prints tree_sha256 (exit 1 when it holds bytecode)")
    tree.add_argument("directory")
    tree.add_argument("--output", required=True)
    tree.add_argument("--limit", type=int, default=50)
    tree.set_defaults(handler=cmd_tree)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ImageManifestError as error:
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
