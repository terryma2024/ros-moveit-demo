"""Controller runtime attestation validation and the install tree walk."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import os
from pathlib import Path
import stat

from so101_demo.parallel_batch.canonical_json import canonical_sha256
from so101_demo.runtime.runtime_closure.identities import (
    _READ_HOOK,
    CLOSURE_ENVIRONMENT_KEYS,
    CONFIG_SUFFIXES,
    CONTROLLER_RUNTIME_ROLE,
    LIBRARY_MARKERS,
    MUJOCO_DYLIB_ALIAS_LINK_TEXT,
    MUJOCO_DYLIB_ALIAS_RELATIVE_PATH,
    SKIPPED_DIRECTORY_NAMES,
    ControllerRuntimeOwnerBinding,
    DylibAliasIdentity,
    FileDigest,
    RuntimeClosureError,
    RuntimeClosureIdentity,
    RuntimeProcessAttestation,
    _attestation_invalid,
    _closure_prefix_for,
)


def validate_controller_runtime_attestation(
    attestation: RuntimeProcessAttestation,
) -> dict[str, object]:
    """Re-validate one controller attestation without trusting any cached verdict.

    The role, the ancestor chain and the plugin/vendor read-back all have to line up: a
    diagnostic launcher standing in for the controller, a descendant that is not reachable
    from the recorded owner root, a second process claiming the same role, an image outside
    the frozen closure (or the sanctioned farm), a drifted digest and an empty read-back all
    fail closed with ``PROCESS_ATTESTATION_INVALID``.
    """

    binding = attestation.owner_binding
    if attestation.role != CONTROLLER_RUNTIME_ROLE:
        raise _attestation_invalid("role", attestation.role)
    if not str(attestation.executable) or not attestation.executable.is_absolute():
        raise _attestation_invalid("executable", str(attestation.executable))
    if attestation.pid <= 0 or attestation.birth_identity <= 0:
        raise _attestation_invalid(
            "identity", f"{attestation.pid}/{attestation.birth_identity}"
        )
    if binding.spawn_role != CONTROLLER_RUNTIME_ROLE:
        raise _attestation_invalid("spawn_role", binding.spawn_role)

    ancestry = binding.ancestry
    if not ancestry:
        raise _attestation_invalid("owner_ancestry", "empty")
    if (
        ancestry[0].pid != binding.owner_root_pid
        or ancestry[0].birth_identity != binding.owner_root_birth_identity
    ):
        raise _attestation_invalid("owner_ancestry", "root identity drift")
    for index, identity in enumerate(ancestry[1:], start=1):
        if identity.parent_pid != ancestry[index - 1].pid:
            raise _attestation_invalid(
                "owner_ancestry", f"{identity.pid} is not a child of {ancestry[index - 1].pid}"
            )
    candidates = [identity for identity in ancestry if identity.role == CONTROLLER_RUNTIME_ROLE]
    if len(candidates) != 1:
        raise _attestation_invalid(
            "owner_ancestry", f"{len(candidates)} controller candidates"
        )
    descendant = ancestry[-1]
    if descendant.role != CONTROLLER_RUNTIME_ROLE:
        raise _attestation_invalid("role", descendant.role)
    if (
        descendant.pid != attestation.pid
        or descendant.birth_identity != attestation.birth_identity
    ):
        raise _attestation_invalid(
            "identity",
            f"{descendant.pid}/{descendant.birth_identity} != "
            f"{attestation.pid}/{attestation.birth_identity}",
        )

    if not binding.closure_prefixes:
        raise _attestation_invalid("closure_prefixes", "empty")
    if not any(
        Path(binding.dylib_farm_root).is_relative_to(Path(prefix))
        for prefix in binding.closure_prefixes
    ):
        raise _attestation_invalid("dylib_farm_root", binding.dylib_farm_root)
    prefixes = tuple(Path(prefix).resolve() for prefix in binding.closure_prefixes)

    executable = Path(attestation.executable).resolve()
    executable_prefix = _closure_prefix_for(executable, prefixes)
    if executable_prefix is None:
        raise _attestation_invalid("executable_scope", str(executable))
    relative_executable = executable.relative_to(executable_prefix).as_posix()
    if relative_executable != binding.expected_executable_relative_path:
        raise _attestation_invalid("controller_executable", relative_executable)

    images = {image.relative_path: image for image in attestation.loaded_images}
    if not images:
        raise _attestation_invalid("loaded_images", "empty")
    for field, image_path, declared in (
        ("plugin", attestation.plugin_path, attestation.plugin_sha256),
        ("vendor", attestation.vendor_path, attestation.vendor_sha256),
    ):
        if not str(image_path) or not Path(image_path).is_absolute():
            raise _attestation_invalid(f"{field}_scope", str(image_path))
        resolved = Path(image_path).resolve()
        prefix = _closure_prefix_for(resolved, prefixes)
        if prefix is None:
            raise _attestation_invalid(f"{field}_scope", str(resolved))
        relative = resolved.relative_to(prefix).as_posix()
        image = images.get(relative)
        if image is None or image.sha256 != declared:
            raise _attestation_invalid(f"{field}_readback", f"{relative}: {declared}")

    if attestation.owner_binding_sha256 != binding.sha256:
        raise _attestation_invalid(
            "owner_binding_sha256", attestation.owner_binding_sha256
        )
    return attestation.as_document()


def build_runtime_process_attestation(
    *,
    closure: RuntimeClosureIdentity | None,
    install_root: Path,
    role: str,
    pid: int,
    birth_identity_before: int,
    birth_identity_after: int,
    executable: Path,
    loaded_images: Sequence[Path],
    required_relative_paths: Sequence[str],
    owner_binding: ControllerRuntimeOwnerBinding,
    plugin_relative_path: str,
    vendor_relative_path: str,
) -> RuntimeProcessAttestation:
    """Validate a stable real controller child and its required closure images.

    ``closure`` is the copied-install identity when one exists. Under the authorized fixed
    dylib-farm contract the round has no single merged closure, so ``closure=None`` keeps the
    digest read-back and the owner binding while the sanctioned prefixes come from
    ``owner_binding``.
    """

    if role != "controller_runtime":
        raise RuntimeClosureError("PROCESS_ATTESTATION_ROLE", role)
    if birth_identity_before != birth_identity_after:
        raise RuntimeClosureError(
            "PROCESS_ATTESTATION_IDENTITY_DRIFT",
            f"{birth_identity_before} != {birth_identity_after}",
        )
    root = _validated_install_root(install_root)
    if closure is not None and root != closure.install_root:
        raise RuntimeClosureError("CLOSURE_INSTALL_ROOT_MISMATCH", str(root))
    executable_path = Path(executable).resolve(strict=True)
    # Under the fixed dylib-farm contract the controller node legitimately lives in one of the five
    # sanctioned prefixes rather than inside the project install (the fork overlay carries
    # `mujoco_ros2_control`), so the scope check uses the binding's prefixes when there is no single
    # merged closure. The validator below still requires the executable to sit under exactly one of
    # them at the frozen relative path.
    executable_prefixes = (
        (root,)
        if closure is not None
        else tuple(Path(prefix).resolve() for prefix in owner_binding.closure_prefixes)
    )
    if not any(executable_path.is_relative_to(prefix) for prefix in executable_prefixes):
        raise RuntimeClosureError(
            "PROCESS_ATTESTATION_EXECUTABLE", str(executable_path)
        )
    known = closure.inventory if closure is not None else {}
    known_names = {Path(value.relative_path).name for value in known.values()}
    sanctioned = tuple(
        Path(prefix).resolve() for prefix in owner_binding.closure_prefixes
    )
    observed: dict[str, FileDigest] = {}
    for raw_path in loaded_images:
        path = Path(raw_path).resolve(strict=True)
        if closure is not None and not path.is_relative_to(root):
            if path.name in known_names:
                raise RuntimeClosureError("LOADED_IMAGE_OUTSIDE_INSTALL", str(path))
            continue
        relative = None
        for prefix in sanctioned:
            if path.is_relative_to(prefix):
                relative = path.relative_to(prefix).as_posix()
                break
        if relative is None:
            continue
        expected = known.get(relative)
        digest = _digest_regular_file(path, relative_path=relative)
        if expected is not None and (
            digest.sha256 != expected.sha256 or digest.size_bytes != expected.size_bytes
        ):
            raise RuntimeClosureError("LOADED_IMAGE_DIGEST_MISMATCH", relative)
        observed[relative] = digest
    missing = sorted(set(required_relative_paths) - set(observed))
    if missing:
        raise RuntimeClosureError(
            "PROCESS_ATTESTATION_REQUIRED_IMAGE_MISSING", ",".join(missing)
        )
    attestation = RuntimeProcessAttestation(
        role=role,
        pid=int(pid),
        birth_identity=int(birth_identity_before),
        executable=executable_path,
        loaded_images=tuple(observed[key] for key in sorted(observed)),
        plugin_path=(Path(plugin_relative_path) if Path(plugin_relative_path).is_absolute()
                     else _absolute_prefix_file(sanctioned, plugin_relative_path)),
        plugin_sha256=observed[plugin_relative_path].sha256,
        vendor_path=(Path(vendor_relative_path) if Path(vendor_relative_path).is_absolute()
                     else _absolute_prefix_file(sanctioned, vendor_relative_path)),
        vendor_sha256=observed[vendor_relative_path].sha256,
        owner_binding=owner_binding,
        owner_binding_sha256=owner_binding.sha256,
    )
    validate_controller_runtime_attestation(attestation)
    return attestation


def _absolute_prefix_file(prefixes: Sequence[Path], relative_path: str) -> Path:
    """Resolve one relative inventory path against the sanctioned prefixes."""

    for prefix in prefixes:
        candidate = prefix / relative_path
        if candidate.is_file():
            return candidate.resolve()
    return prefixes[0] / relative_path if prefixes else Path(relative_path)


def _digest_regular_file(path: Path, *, relative_path: str) -> FileDigest:
    """Digest one regular file through a single fd, refusing symlinks and replacements."""

    if path.is_symlink():
        raise RuntimeClosureError("CLOSURE_SYMLINK", str(path))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RuntimeClosureError("CLOSURE_UNREADABLE_FILE", f"{path}: {error}") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeClosureError("CLOSURE_NOT_REGULAR_FILE", str(path))
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        if _READ_HOOK is not None:
            _READ_HOOK(path)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or size != after.st_size:
        raise RuntimeClosureError("CLOSURE_FILE_REPLACED", str(path))
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as error:
        raise RuntimeClosureError("CLOSURE_FILE_REPLACED", f"{path}: {error}") from error
    if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != (
        after.st_dev,
        after.st_ino,
    ):
        raise RuntimeClosureError("CLOSURE_FILE_REPLACED", str(path))
    return FileDigest(
        relative_path=relative_path, sha256=digest.hexdigest(), size_bytes=size
    )


def _read_allowed_dylib_alias(
    root: Path, path: Path, *, relative_path: str
) -> tuple[str, os.stat_result]:
    """Read the exact installer alias without following it or trusting a stale target."""

    if relative_path != MUJOCO_DYLIB_ALIAS_RELATIVE_PATH:
        raise RuntimeClosureError("CLOSURE_SYMLINK", relative_path)
    try:
        before = os.lstat(path)
        link_text = os.readlink(path)
    except OSError as error:
        raise RuntimeClosureError("CLOSURE_SYMLINK", f"{path}: {error}") from error
    if not stat.S_ISLNK(before.st_mode) or link_text != MUJOCO_DYLIB_ALIAS_LINK_TEXT:
        raise RuntimeClosureError("CLOSURE_SYMLINK", str(path))
    link = Path(link_text)
    if link.is_absolute() or len(link.parts) != 1 or link_text in {".", ".."}:
        raise RuntimeClosureError("CLOSURE_SYMLINK", link_text)
    target = path.parent / link_text
    try:
        target_relative = target.relative_to(root).as_posix()
        target_stat = os.lstat(target)
    except (OSError, ValueError) as error:
        raise RuntimeClosureError("CLOSURE_SYMLINK", f"{path}: {error}") from error
    if (
        target_relative
        != "opt/mujoco_vendor/lib/libmujoco.3.4.0.dylib"
        or stat.S_ISLNK(target_stat.st_mode)
        or not stat.S_ISREG(target_stat.st_mode)
    ):
        raise RuntimeClosureError("CLOSURE_SYMLINK", str(path))
    return link_text, before


def _walk_install_files(
    root: Path,
) -> tuple[tuple[tuple[FileDigest, int], ...], tuple[DylibAliasIdentity, ...]]:
    collected: list[tuple[FileDigest, int]] = []
    pending_aliases: list[tuple[str, str, os.stat_result]] = []
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        for name in sorted(directory_names):
            candidate = current / name
            if name in SKIPPED_DIRECTORY_NAMES:
                continue
            if candidate.is_symlink():
                raise RuntimeClosureError("CLOSURE_SYMLINK", str(candidate))
        directory_names[:] = sorted(
            name for name in directory_names if name not in SKIPPED_DIRECTORY_NAMES
        )
        for name in sorted(file_names):
            path = current / name
            relative_path = path.relative_to(root).as_posix()
            if path.is_symlink():
                link_text, before = _read_allowed_dylib_alias(
                    root, path, relative_path=relative_path
                )
                pending_aliases.append((relative_path, link_text, before))
                continue
            if relative_path == MUJOCO_DYLIB_ALIAS_RELATIVE_PATH:
                raise RuntimeClosureError("CLOSURE_SYMLINK", str(path))
            digest = _digest_regular_file(path, relative_path=relative_path)
            mode = os.stat(path, follow_symlinks=False).st_mode
            collected.append((digest, mode))
    by_path = {digest.relative_path: digest for digest, _mode in collected}
    aliases: list[DylibAliasIdentity] = []
    for relative_path, link_text, before in pending_aliases:
        path = root / relative_path
        target_relative = (Path(relative_path).parent / link_text).as_posix()
        target = by_path.get(target_relative)
        try:
            after = os.lstat(path)
            after_text = os.readlink(path)
        except OSError as error:
            raise RuntimeClosureError("CLOSURE_SYMLINK", f"{path}: {error}") from error
        if (
            target is None
            or (before.st_dev, before.st_ino, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_mtime_ns)
            or after_text != link_text
        ):
            raise RuntimeClosureError("CLOSURE_SYMLINK", str(path))
        aliases.append(
            DylibAliasIdentity(
                relative_path=relative_path,
                link_text=link_text,
                target_relative_path=target_relative,
                target_sha256=target.sha256,
            )
        )
    return tuple(collected), tuple(aliases)


def _classify(entry: FileDigest, mode: int) -> str:
    name = Path(entry.relative_path).name
    if any(marker in name for marker in LIBRARY_MARKERS):
        return "library"
    if Path(name).suffix in CONFIG_SUFFIXES:
        return "config"
    if mode & 0o111:
        return "executable"
    return "other"


def collect_install_inventory(install_root: Path) -> tuple[FileDigest, ...]:
    """Every regular file under the copied install prefix, as relative-path digests."""

    root = _validated_install_root(install_root)
    collected, _aliases = _walk_install_files(root)
    return tuple(digest for digest, _mode in collected)


def _validated_install_root(
    install_root: Path, forbidden_roots: Sequence[Path] = ()
) -> Path:
    root = Path(install_root)
    if not root.is_absolute():
        raise RuntimeClosureError(
            "CLOSURE_INSTALL_ROOT_INVALID", f"install root must be absolute: {root}"
        )
    if root.is_symlink():
        raise RuntimeClosureError(
            "CLOSURE_INSTALL_ROOT_INVALID", f"install root must not be a symlink: {root}"
        )
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise RuntimeClosureError(
            "CLOSURE_INSTALL_ROOT_INVALID", f"{root}: {error}"
        ) from error
    if not resolved.is_dir():
        raise RuntimeClosureError(
            "CLOSURE_INSTALL_ROOT_INVALID", f"install root is not a directory: {resolved}"
        )
    for forbidden in forbidden_roots:
        candidate = Path(forbidden)
        try:
            resolved_forbidden = candidate.resolve(strict=False)
        except OSError:  # pragma: no cover - resolve(strict=False) rarely fails
            continue
        if resolved == resolved_forbidden or resolved.is_relative_to(resolved_forbidden):
            raise RuntimeClosureError(
                "CLOSURE_PREFIX_CONTAMINATION",
                f"{resolved} lives inside the forbidden root {resolved_forbidden}",
            )
    return resolved


def normalized_environment_sha256(
    environment: Mapping[str, str] | None,
    *,
    keys: Sequence[str] = CLOSURE_ENVIRONMENT_KEYS,
) -> str:
    """Digest the closed set of environment constraints that belong to the identity."""

    values = dict(environment or {})
    document = {
        key: (values[key] if isinstance(values.get(key), str) else None) for key in sorted(keys)
    }
    return canonical_sha256(document)
