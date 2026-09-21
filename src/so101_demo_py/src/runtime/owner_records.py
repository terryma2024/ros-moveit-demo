"""Durable owner-tree records: an intent before every real spawn, a readback after it.

Task 6 of the macOS service campaign closure plan. The service's recovery path reclaims the
process tree ``adapter -> campaign -> worker -> station`` leaf first, and it may only signal a
process whose live kernel identity still matches a durable record. Two files per spawn make that
possible, each written atomically and fsynced before the writer continues:

* ``<spawn_token>.intent.json`` - written *before* ``Popen``. A crash between the write and the
  spawn therefore leaves an intent without a process, never a process without an intent.
* ``<spawn_token>.confirmed.json`` - written *after* the kernel readback of pid, pgid and birth
  ticks. Recovery re-proves the live command against it before signalling anything, so a reused
  PID is never mistaken for the process this record describes.
* ``<spawn_token>.abandoned.json`` - written when a spawn that has an intent fails. The intent is
  evidence and is never deleted; the marker says the process it named never became a live child.

The records live under ``<root>/<campaign_id>/<batch_id>/`` and nothing is ever written outside
that root: every path component is checked, a symlinked record file is refused, and the directory
is resolved before the write so a symlinked batch directory cannot redirect it.

``so101_teleop`` reads these records at recovery time. The dependency runs one way only - teleop
depends on demo - so this module imports the standard library plus the demo's existing process
identity probe and never ``so101_teleop``.

The whole feature is inert without :data:`ROOT_VARIABLE`: no root means
:func:`owner_context_from_environment` returns ``None``, and every caller then spawns exactly as
it did before this module existed - no files, no added environment.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence
from uuid import uuid4

from ..parallel_batch.start_guard_probe import read_process_identity

#: The environment context. Every variable is optional: absent means "this process owns no tree".
ROOT_VARIABLE = "SO101_OWNER_TREE_ROOT"
CAMPAIGN_VARIABLE = "SO101_OWNER_CAMPAIGN_ID"
BATCH_VARIABLE = "SO101_OWNER_BATCH_ID"
GENERATION_VARIABLE = "SO101_OWNER_GENERATION"
PARENT_TOKEN_VARIABLE = "SO101_OWNER_PARENT_TOKEN"
TOKEN_VARIABLE = "SO101_OWNER_TOKEN"

#: The only roles a record may declare, in the vocabulary the recovery side reads.
ROLES = ("ADAPTER", "CAMPAIGN", "BROKER", "WORKER", "STATION")

INTENT_SCHEMA = "so101.owner-intent/1"
CONFIRMATION_SCHEMA = "so101.owner-confirmation/1"

#: Bounded retry between two kernel reads while a child is being confirmed.
CONFIRM_RETRY_S = 0.02

#: Codes a caller may branch on. ``OWNER_CONFIRMATION_UNREADABLE`` is part of the frozen
#: contract the recovery side and the wiring tests rely on.
CONFIRMATION_UNREADABLE = "OWNER_CONFIRMATION_UNREADABLE"
ROLE_INVALID = "OWNER_ROLE_INVALID"
ARGV_INVALID = "OWNER_ARGV_INVALID"
CONTEXT_INVALID = "OWNER_CONTEXT_INVALID"
UNSAFE_PATH = "OWNER_RECORD_UNSAFE_PATH"
UNWRITABLE = "OWNER_RECORD_UNWRITABLE"


class OwnerRecordError(RuntimeError):
    """A durable owner record cannot be trusted, written, or confirmed."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _is_safe_component(value: object) -> bool:
    """One path component that can only ever name a child of the directory it is joined to."""

    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if value in {".", ".."}:
        return False
    return not any(character in value for character in ("/", "\\", "\0"))


@dataclass(frozen=True)
class OwnerContext:
    """Where one campaign's owner records live, and which campaign they belong to."""

    root: Path
    campaign_id: str
    batch_id: str
    generation: int
    parent_spawn_token: str | None = None

    def __post_init__(self) -> None:
        root = Path(self.root)
        if not root.is_absolute():
            raise OwnerRecordError(CONTEXT_INVALID, f"root must be absolute: {root}")
        for name in ("campaign_id", "batch_id"):
            if not _is_safe_component(getattr(self, name)):
                raise OwnerRecordError(CONTEXT_INVALID, name)
        if type(self.generation) is not int or self.generation < 1:
            raise OwnerRecordError(CONTEXT_INVALID, f"generation={self.generation!r}")
        if self.parent_spawn_token is not None and not _is_safe_component(
            self.parent_spawn_token
        ):
            raise OwnerRecordError(CONTEXT_INVALID, "parent_spawn_token")
        object.__setattr__(self, "root", root)


def owner_context_from_environment(environment: Mapping[str, str]) -> OwnerContext | None:
    """The owner context this process was started with, or ``None`` when it owns no tree.

    ``None`` is the inert answer, and it covers both "this process is not part of an owner tree"
    (no root) and "the context is unusable" (a missing, empty or unsafe field). Nothing is
    guessed and no default root is invented: a record written somewhere unexpected is worse than
    no record at all.
    """

    if not isinstance(environment, Mapping):
        return None
    raw_root = environment.get(ROOT_VARIABLE)
    if not isinstance(raw_root, str) or not raw_root.strip():
        return None
    campaign_id = environment.get(CAMPAIGN_VARIABLE)
    batch_id = environment.get(BATCH_VARIABLE)
    generation = environment.get(GENERATION_VARIABLE)
    for value in (campaign_id, batch_id, generation):
        if not isinstance(value, str) or not value.strip():
            return None
    if not generation.strip().isdigit() or int(generation) < 1:
        return None
    parent = environment.get(PARENT_TOKEN_VARIABLE)
    if not isinstance(parent, str) or not parent.strip():
        parent = None
    try:
        return OwnerContext(
            root=Path(raw_root),
            campaign_id=campaign_id,
            batch_id=batch_id,
            generation=int(generation),
            parent_spawn_token=parent,
        )
    except OwnerRecordError:
        return None


def spawner_token_from_environment(environment: Mapping[str, str]) -> str | None:
    """The token ``environment`` gave *this* process, for use as a child's parent token.

    A token that could not name a record component is not propagated: the child then records no
    parent token rather than an unusable one, and the spawn itself is never refused for it.
    """

    if not isinstance(environment, Mapping):
        return None
    token = environment.get(TOKEN_VARIABLE)
    return token if _is_safe_component(token) else None


def command_fingerprint(argv: Sequence[str]) -> str:
    """The durable fingerprint of a command line: everything after ``argv[0]``.

    Byte-identical to :func:`so101_teleop.process_identity.command_fingerprint`, which is what the
    recovery side re-computes from the live process: ``argv[0]`` is excluded because no platform
    promises to preserve it (a venv interpreter reports the resolved binary, a shebang script
    becomes ``[interpreter, script, ...]``), and everything after it is hashed exactly.
    """

    encoded = json.dumps(list(argv[1:]), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_kernel_identity(pid: int) -> tuple[int, int] | None:
    """``(pgid, start_time_ticks)`` as the kernel reports them now, or ``None`` when unreadable."""

    try:
        pgid = int(os.getpgid(int(pid)))
    except (ProcessLookupError, PermissionError, OSError):
        return None
    record = read_process_identity(int(pid))
    if record is None:
        return None
    return pgid, int(record.start_time_ticks)


def _record_directory(context: OwnerContext) -> Path:
    """``<root>/<campaign_id>/<batch_id>``, created and proven to be inside the root."""

    directory = context.root / context.campaign_id / context.batch_id
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise OwnerRecordError(UNWRITABLE, f"{directory}: {error}") from error
    root_real = Path(os.path.realpath(context.root))
    directory_real = Path(os.path.realpath(directory))
    if directory_real != root_real and root_real not in directory_real.parents:
        raise OwnerRecordError(UNSAFE_PATH, f"{directory} resolves outside {context.root}")
    return directory


def _remove_if_present(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:  # pragma: no cover - a leftover temporary we cannot remove is reported later
        pass


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    except OSError:  # pragma: no cover - not every filesystem allows directory fsync
        pass
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, document: Mapping[str, object], *, context: OwnerContext) -> None:
    """Write one document durably: sibling temp file, fsync, ``os.replace``, directory fsync.

    The temporary file is opened with ``O_NOFOLLOW``: a symlink planted at either name is refused
    rather than followed, and the only name ever replaced is the record's own.
    """

    payload = json.dumps(dict(document), indent=2, sort_keys=True) + "\n"
    _record_directory(context)
    if path.is_symlink():
        raise OwnerRecordError(UNSAFE_PATH, f"refusing to write through {path}")
    temporary = path.with_name(path.name + ".part")
    _remove_if_present(temporary)
    descriptor = -1
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        os.write(descriptor, payload.encode("utf-8"))
        os.fsync(descriptor)
    except OSError as error:
        if descriptor >= 0:
            os.close(descriptor)
            descriptor = -1
        _remove_if_present(temporary)
        raise OwnerRecordError(UNWRITABLE, f"{path}: {error}") from error
    else:
        os.close(descriptor)
    try:
        os.replace(temporary, path)
    except OSError as error:
        _remove_if_present(temporary)
        raise OwnerRecordError(UNWRITABLE, f"{path}: {error}") from error
    _fsync_directory(path.parent)


@dataclass(frozen=True)
class OwnerSpawnRecorder:
    """One spawn this process is about to make, and the two durable records that describe it."""

    context: OwnerContext
    role: str
    spawn_token: str
    parent_spawn_token: str | None
    argv_sha256: str
    expected_executable: str
    own_session: bool
    created_at_ns: int

    @classmethod
    def begin(
        cls,
        *,
        context: OwnerContext,
        role: str,
        argv: Sequence[str],
        parent_spawn_token: str | None = None,
        own_session: bool = True,
        spawn_token: str | None = None,
        clock: Callable[[], int] = time.time_ns,
    ) -> "OwnerSpawnRecorder":
        """Write the intent and return only once it is durable, before any ``Popen``.

        ``parent_spawn_token`` is the *spawner's own* token (the value this process received as
        ``SO101_OWNER_TOKEN``), not the child's: the record names the parent of the process about
        to be spawned, and a root spawner passes ``None``.
        """

        if not isinstance(context, OwnerContext):
            raise OwnerRecordError(CONTEXT_INVALID, "an owner context is required")
        if role not in ROLES:
            raise OwnerRecordError(ROLE_INVALID, str(role))
        arguments = [str(item) for item in argv]
        if not arguments:
            raise OwnerRecordError(ARGV_INVALID, "argv is required")
        token = spawn_token if spawn_token is not None else f"{role.lower()}-{uuid4().hex}"
        if not _is_safe_component(token):
            raise OwnerRecordError(UNSAFE_PATH, str(token))
        if parent_spawn_token is not None and not _is_safe_component(parent_spawn_token):
            raise OwnerRecordError(CONTEXT_INVALID, "parent_spawn_token")
        recorder = cls(
            context=context,
            role=role,
            spawn_token=token,
            parent_spawn_token=parent_spawn_token or None,
            argv_sha256=command_fingerprint(arguments),
            expected_executable=arguments[0],
            own_session=bool(own_session),
            created_at_ns=int(clock()),
        )
        _atomic_write(recorder.intent_path, recorder.intent_document(), context=context)
        return recorder

    # -- paths ---------------------------------------------------------------------------

    @property
    def intent_path(self) -> Path:
        return self._directory / f"{self.spawn_token}.intent.json"

    @property
    def confirmation_path(self) -> Path:
        return self._directory / f"{self.spawn_token}.confirmed.json"

    @property
    def abandoned_path(self) -> Path:
        return self._directory / f"{self.spawn_token}.abandoned.json"

    @property
    def _directory(self) -> Path:
        return _record_directory(self.context)

    # -- documents -----------------------------------------------------------------------

    def intent_document(self) -> dict[str, object]:
        return {
            "schema": INTENT_SCHEMA,
            "campaign_id": self.context.campaign_id,
            "batch_id": self.context.batch_id,
            "role": self.role,
            "generation": self.context.generation,
            "spawn_token": self.spawn_token,
            "parent_spawn_token": self.parent_spawn_token,
            "expected_executable": self.expected_executable,
            "argv_sha256": self.argv_sha256,
            "own_session": self.own_session,
            "created_at_ns": self.created_at_ns,
        }

    def child_environment(self, base: Mapping[str, str] | None = None) -> dict[str, str]:
        """The child's environment: its own token, this spawner's token as its parent, and the root.

        ``SO101_OWNER_PARENT_TOKEN`` is set from the spawner rather than inherited: the child's
        parent is *this* process. When this spawner has no token of its own the variable is
        removed, so an inherited grandparent token is never mistaken for the child's parent.
        """

        environment = dict(os.environ if base is None else base)
        environment[ROOT_VARIABLE] = str(self.context.root)
        environment[CAMPAIGN_VARIABLE] = self.context.campaign_id
        environment[BATCH_VARIABLE] = self.context.batch_id
        environment[GENERATION_VARIABLE] = str(self.context.generation)
        environment[TOKEN_VARIABLE] = self.spawn_token
        if self.parent_spawn_token:
            environment[PARENT_TOKEN_VARIABLE] = self.parent_spawn_token
        else:
            environment.pop(PARENT_TOKEN_VARIABLE, None)
        return environment

    # -- the readback --------------------------------------------------------------------

    def confirm(
        self,
        pid: int,
        *,
        identity_reader: Callable[[int], tuple[int, int] | None] = _read_kernel_identity,
        deadline_s: float = 2.0,
        clock: Callable[[], int] = time.time_ns,
    ) -> dict:
        """Read the child's kernel identity back, retrying until ``deadline_s``, then record it.

        ``command_sha256`` is this recorder's requested command fingerprint. The live command is
        deliberately not re-read here: the recovery side re-proves that against the live process,
        which is the only place it can be proven, and a record that claimed to have done so would
        be claiming more than it can.
        """

        if type(pid) is not int or pid <= 0:
            raise OwnerRecordError(CONFIRMATION_UNREADABLE, f"pid={pid!r}")
        deadline_ns = int(clock()) + int(float(deadline_s) * 1_000_000_000)
        while True:
            observed = identity_reader(pid)
            if observed is not None:
                pgid, started_ticks = observed
                break
            if clock() >= deadline_ns:
                raise OwnerRecordError(
                    CONFIRMATION_UNREADABLE, f"pid {pid} was never reported by the kernel"
                )
            time.sleep(CONFIRM_RETRY_S)
        document = {
            "schema": CONFIRMATION_SCHEMA,
            "spawn_token": self.spawn_token,
            "pid": int(pid),
            "pgid": int(pgid),
            "started_ticks": int(started_ticks),
            "command_sha256": self.argv_sha256,
            "confirmed_at_ns": int(clock()),
        }
        _atomic_write(self.confirmation_path, document, context=self.context)
        return document

    def abandon(self, reason: str) -> None:
        """Mark a spawned-but-failed record. The intent stays; nothing is deleted."""

        document = {
            "spawn_token": self.spawn_token,
            "reason": str(reason),
            "recorded_at_ns": int(time.time_ns()),
        }
        _atomic_write(self.abandoned_path, document, context=self.context)
