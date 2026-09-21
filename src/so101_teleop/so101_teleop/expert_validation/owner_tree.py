"""The persistent macOS owner tree: intent before every spawn, leaf-first recovery after a crash.

Every real spawn in the service hangs off one tree - ``adapter -> campaign -> worker -> station``,
with the broker as the campaign's second child. A spawn is durable in two steps:

1. :class:`OwnerIntent` is written *before* ``Popen``. A crash between the write and the spawn
   therefore leaves an intent with no process, never a process with no intent.
2. :class:`ConfirmedOwnerProcess` is written *after* the kernel readback of PID, PGID and birth
   marker. Recovery only signals a process whose live identity still matches that readback.

Recovery itself is leaf-first (:data:`RECLAIM_ORDER`): the station goes before the worker, the
worker before the campaign, and the adapter last, so no parent is stopped while a child it owns can
still fork or hold the journal. A station in its own session is reclaimed through its own recorded
PGID, never through the worker's group.

An identity that cannot be proven is never signalled and never guessed at: the record becomes
``unresolved``, the fence stays, and the caller keeps reporting operator recovery. Foreign
processes are not part of any tree, so they are never touched.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Callable, Mapping, Sequence

from ..owned_group import terminate_group
from ..process_identity import ProcessIdentityError, command_fingerprint, read_identity


class OwnerTreeError(RuntimeError):
    """A durable owner record cannot be trusted, or a recovery may not proceed."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


#: The only roles an intent may declare.
ROLES = ("ADAPTER", "CAMPAIGN", "BROKER", "WORKER", "STATION")

#: Leaf-first reclamation order. A role is stopped only after every role to its left is gone.
RECLAIM_ORDER = ("STATION", "WORKER", "BROKER", "CAMPAIGN", "ADAPTER")

#: The frozen durable document schemas every spawn boundary writes into the shared tree root.
INTENT_SCHEMA = "so101.owner-intent/1"
CONFIRMATION_SCHEMA = "so101.owner-confirmation/1"
UNRESOLVED_TREE_SCHEMA = "so101.unresolved-owner-tree/1"

INTENT_SUFFIX = ".intent.json"
CONFIRMED_SUFFIX = ".confirmed.json"
ABANDONED_SUFFIX = ".abandoned.json"
RECEIPT_SUFFIX = ".owner-cleanup-receipt.json"
UNRESOLVED_SUFFIX = ".unresolved-owner-tree.json"


def _canonical_hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_id(name: str, value) -> str:
    if not isinstance(value, str) or not value:
        raise OwnerTreeError("OWNER_FIELD_INVALID", name)
    return value


def _require_sha256(name: str, value) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise OwnerTreeError("OWNER_FIELD_INVALID", name)
    return value


def _safe_record_name(name: str, value) -> str:
    """One path-safe coordinate. A record may never be read from outside its own tree."""
    if (
        not isinstance(value, str)
        or not value
        or value in (".", "..")
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{name}={value!r}")
    return value


def _receipt_document(receipt, recorded_at_ns: int) -> dict[str, object]:
    """The one durable receipt shape, shared by the receipt file and the directory source.

    ``receipt_sha256`` covers every other field, so a reader can tell a truncated or rewritten
    receipt from the one the reaper committed.
    """
    document: dict[str, object] = {
        "campaign_id": receipt.campaign_id,
        "batch_id": receipt.batch_id,
        "generation": receipt.generation,
        "reclaimed": [dict(entry) for entry in receipt.reclaimed],
        "already_exited": [dict(entry) for entry in receipt.already_exited],
        "unresolved": [dict(entry) for entry in receipt.unresolved],
        "recorded_at_ns": recorded_at_ns,
    }
    document["receipt_sha256"] = _canonical_hash(document)
    return document


def _write_document_exclusive(path: Path, document: Mapping[str, object]) -> None:
    """Create one durable document exactly once, fsynced with its directory."""
    payload = json.dumps(dict(document), sort_keys=True, separators=(",", ":")).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _read_document(path: Path, *, required: bool) -> dict | None:
    """Read one durable document without ever following a symlink.

    A malformed, unreadable or non-object document is a hard error: skipping it would hide an owner
    process from the reaper, which is the one thing this module exists to prevent.
    """
    if path.is_symlink():
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: symlinked owner record")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        if required:
            raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: missing") from None
        return None
    except OSError as error:
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: {error}") from error
    try:
        chunks = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
    except OSError as error:
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: {error}") from error
    finally:
        os.close(descriptor)
    try:
        document = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: {error}") from error
    if not isinstance(document, dict):
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: not a JSON object")
    return document


def _directory_names(directory: Path) -> list[str]:
    """List one record directory through a no-follow descriptor, or nothing if it is absent."""
    if directory.is_symlink():
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{directory}: symlinked owner directory")
    try:
        descriptor = os.open(directory, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return []
    except OSError as error:
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{directory}: {error}") from error
    try:
        return sorted(os.listdir(descriptor))
    except OSError as error:
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{directory}: {error}") from error
    finally:
        os.close(descriptor)


def _intent_from_directory(
    path: Path,
    document: Mapping[str, object],
    *,
    campaign_id: str,
    batch_id: str,
    spawn_token: str,
) -> OwnerIntent:
    """Validate one frozen intent document against the coordinates its file name claims."""
    if document.get("schema") != INTENT_SCHEMA:
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: schema")
    for name in (
        "campaign_id",
        "batch_id",
        "role",
        "spawn_token",
        "expected_executable",
        "argv_sha256",
    ):
        if not isinstance(document.get(name), str):
            raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: {name}")
    if (
        type(document.get("generation")) is not int
        or type(document.get("created_at_ns")) is not int
    ):
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: timestamp")
    if type(document.get("own_session")) is not bool:
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: own_session")
    parent = document.get("parent_spawn_token")
    if parent is not None and not isinstance(parent, str):
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: parent_spawn_token")
    if (
        document["campaign_id"] != campaign_id
        or document["batch_id"] != batch_id
        or document["spawn_token"] != spawn_token
    ):
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: coordinates")
    try:
        return OwnerIntent.from_document(document)
    except OwnerTreeError as error:
        # A file that cannot even describe a legal intent is a corrupt record, not a field error.
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: {error}") from error


def _confirmation_from_directory(
    path: Path, document: Mapping[str, object], *, spawn_token: str
) -> ConfirmedOwnerProcess:
    """Validate one frozen readback document against the spawn token it claims."""
    if document.get("schema") != CONFIRMATION_SCHEMA:
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: schema")
    if not isinstance(document.get("spawn_token"), str):
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: spawn_token")
    if document["spawn_token"] != spawn_token:
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: coordinates")
    for name in ("pid", "pgid", "started_ticks", "confirmed_at_ns"):
        if type(document.get(name)) is not int:
            raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: {name}")
    if not isinstance(document.get("command_sha256"), str):
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: command_sha256")
    try:
        return ConfirmedOwnerProcess.from_document(document)
    except OwnerTreeError as error:
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: {error}") from error


def _receipt_from_directory(path: Path, document: Mapping[str, object]) -> dict:
    """Validate the shape ``OwnerTreeRecovery._write_receipt`` produces before trusting it."""
    if not isinstance(document.get("receipt_sha256"), str):
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: receipt_sha256")
    for name in ("campaign_id", "batch_id"):
        if not isinstance(document.get(name), str):
            raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: {name}")
    if type(document.get("generation")) is not int:
        raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: generation")
    for name in ("reclaimed", "already_exited", "unresolved"):
        if not isinstance(document.get(name), list):
            raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: {name}")
    return dict(document)


@dataclass(frozen=True, slots=True)
class OwnerIntent:
    """One durable spawn intent: written before the process exists."""

    campaign_id: str
    batch_id: str
    role: str
    generation: int
    spawn_token: str
    parent_spawn_token: str | None
    expected_executable: str
    argv_sha256: str
    own_session: bool
    created_at_ns: int

    def __post_init__(self) -> None:
        _require_id("campaign_id", self.campaign_id)
        _require_id("batch_id", self.batch_id)
        if self.role not in ROLES:
            raise OwnerTreeError("OWNER_ROLE_INVALID", str(self.role))
        if type(self.generation) is not int or self.generation < 1:
            raise OwnerTreeError("OWNER_FIELD_INVALID", "generation")
        _require_id("spawn_token", self.spawn_token)
        _require_id("expected_executable", self.expected_executable)
        _require_sha256("argv_sha256", self.argv_sha256)
        if self.parent_spawn_token is not None:
            _require_id("parent_spawn_token", self.parent_spawn_token)
        if type(self.created_at_ns) is not int or self.created_at_ns < 1:
            raise OwnerTreeError("OWNER_FIELD_INVALID", "created_at_ns")

    @classmethod
    def for_argv(
        cls,
        *,
        campaign_id: str,
        batch_id: str,
        role: str,
        generation: int,
        spawn_token: str,
        argv: Sequence[str],
        parent_spawn_token: str | None = None,
        own_session: bool = True,
        created_at_ns: int | None = None,
    ) -> "OwnerIntent":
        if not argv:
            raise OwnerTreeError("OWNER_ARGV_EMPTY")
        return cls(
            campaign_id=campaign_id,
            batch_id=batch_id,
            role=role,
            generation=generation,
            spawn_token=spawn_token,
            parent_spawn_token=parent_spawn_token,
            expected_executable=str(argv[0]),
            # argv[0] is excluded on purpose: a launcher or interpreter may legitimately rewrite
            # it, and every durable fingerprint in this service is taken the same way.
            argv_sha256=command_fingerprint(argv),
            own_session=own_session,
            created_at_ns=created_at_ns if created_at_ns is not None else time.time_ns(),
        )

    def as_document(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "batch_id": self.batch_id,
            "role": self.role,
            "generation": self.generation,
            "spawn_token": self.spawn_token,
            "parent_spawn_token": self.parent_spawn_token,
            "expected_executable": self.expected_executable,
            "argv_sha256": self.argv_sha256,
            "own_session": self.own_session,
            "created_at_ns": self.created_at_ns,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "OwnerIntent":
        return cls(
            campaign_id=str(document["campaign_id"]),
            batch_id=str(document["batch_id"]),
            role=str(document["role"]),
            generation=int(document["generation"]),
            spawn_token=str(document["spawn_token"]),
            parent_spawn_token=(
                None
                if document.get("parent_spawn_token") is None
                else str(document["parent_spawn_token"])
            ),
            expected_executable=str(document["expected_executable"]),
            argv_sha256=str(document["argv_sha256"]),
            own_session=bool(document.get("own_session", True)),
            created_at_ns=int(document["created_at_ns"]),
        )


@dataclass(frozen=True, slots=True)
class ConfirmedOwnerProcess:
    """The kernel readback of a spawned process, written after ``Popen``."""

    spawn_token: str
    pid: int
    pgid: int
    started_ticks: int
    command_sha256: str
    confirmed_at_ns: int

    def __post_init__(self) -> None:
        _require_id("spawn_token", self.spawn_token)
        for name in ("pid", "pgid"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise OwnerTreeError("OWNER_FIELD_INVALID", name)
        if type(self.started_ticks) is not int or self.started_ticks < 0:
            raise OwnerTreeError("OWNER_FIELD_INVALID", "started_ticks")
        _require_sha256("command_sha256", self.command_sha256)
        if type(self.confirmed_at_ns) is not int or self.confirmed_at_ns < 1:
            raise OwnerTreeError("OWNER_FIELD_INVALID", "confirmed_at_ns")

    def as_document(self) -> dict[str, object]:
        return {
            "spawn_token": self.spawn_token,
            "pid": self.pid,
            "pgid": self.pgid,
            "started_ticks": self.started_ticks,
            "command_sha256": self.command_sha256,
            "confirmed_at_ns": self.confirmed_at_ns,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "ConfirmedOwnerProcess":
        return cls(
            spawn_token=str(document["spawn_token"]),
            pid=int(document["pid"]),
            pgid=int(document["pgid"]),
            started_ticks=int(document["started_ticks"]),
            command_sha256=str(document["command_sha256"]),
            confirmed_at_ns=int(document["confirmed_at_ns"]),
        )


@dataclass(frozen=True, slots=True)
class OwnerRecord:
    """One durable tree entry: always an intent, optionally a confirmation."""

    intent: OwnerIntent
    confirmed: ConfirmedOwnerProcess | None


@dataclass(frozen=True, slots=True)
class OwnerParentBinding:
    """Who is allowed to reclaim this tree, and for which generation."""

    campaign_id: str
    batch_id: str
    generation: int
    recovery_owner: str
    parent_pid: int | None = None
    parent_started_ticks: int | None = None


@dataclass(frozen=True, slots=True)
class OwnerCleanupReceipt:
    """The fsynced result of one leaf-first recovery."""

    campaign_id: str
    batch_id: str
    generation: int
    reclaimed: tuple[dict[str, object], ...]
    already_exited: tuple[dict[str, object], ...]
    unresolved: tuple[dict[str, object], ...]
    receipt_sha256: str

    @property
    def fence_released(self) -> bool:
        """A fence may only be released when nothing about this tree is left unproven."""
        return not self.unresolved

    def as_document(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "batch_id": self.batch_id,
            "generation": self.generation,
            "reclaimed": [dict(entry) for entry in self.reclaimed],
            "already_exited": [dict(entry) for entry in self.already_exited],
            "unresolved": [dict(entry) for entry in self.unresolved],
            "fence_released": self.fence_released,
            "receipt_sha256": self.receipt_sha256,
        }

    def describe(self) -> str:
        return (
            f"generation {self.generation} reclaimed={len(self.reclaimed)} "
            f"already_exited={len(self.already_exited)} unresolved={len(self.unresolved)} "
            f"fence_released={self.fence_released} receipt={self.receipt_sha256[:12]}"
        )


@dataclass(frozen=True, slots=True)
class DirectoryOwnerRecords:
    """The demo-side spawn boundaries' durable records, read from one shared tree root.

    ``<root>/<campaign_id>/<batch_id>/`` holds ``<spawn_token>.intent.json`` before every spawn,
    ``<spawn_token>.confirmed.json`` after the kernel readback, the committed cleanup receipt and
    the unresolved-tree fence. An ``.abandoned.json`` marker records that the boundary gave up a
    prepared spawn; the intent itself stays in the tree as unconfirmed, because the crash window it
    covers is exactly the window in which a process may exist without a readback.

    Reading is deliberately hostile. A symlinked root, directory or record file, a record whose
    file name and document disagree, and any malformed or unreadable document are all
    ``OWNER_RECORD_INVALID``: a record is never silently skipped, because a skipped record is an
    owner process no reaper would ever see.
    """

    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root))

    def owner_tree(
        self, campaign_id: str, batch_id: str, generation: int | None = None
    ) -> tuple[OwnerRecord, ...]:
        if generation is not None and (type(generation) is not int or generation < 1):
            raise OwnerTreeError("OWNER_RECORD_INVALID", f"generation={generation!r}")
        directory = self._batch_directory(campaign_id, batch_id, create=False)
        if directory is None:
            return ()
        names = _directory_names(directory)
        records: list[tuple[OwnerIntent, ConfirmedOwnerProcess | None]] = []
        for name in names:
            if not name.endswith(INTENT_SUFFIX):
                continue
            spawn_token = name[: -len(INTENT_SUFFIX)]
            if not spawn_token:
                raise OwnerTreeError("OWNER_RECORD_INVALID", f"{directory / name}: spawn_token")
            path = directory / name
            document = _read_document(path, required=True)
            intent = _intent_from_directory(
                path, document, campaign_id=campaign_id, batch_id=batch_id, spawn_token=spawn_token
            )
            confirmation_path = directory / f"{spawn_token}{CONFIRMED_SUFFIX}"
            confirmation_document = _read_document(confirmation_path, required=False)
            confirmed = (
                None
                if confirmation_document is None
                else _confirmation_from_directory(
                    confirmation_path, confirmation_document, spawn_token=spawn_token
                )
            )
            records.append((intent, confirmed))
        intents = {intent.spawn_token for intent, _ in records}
        for name in names:
            # A confirmation nothing ever intended is corruption: it names a process this tree
            # cannot attribute to any spawn, so it is refused rather than ignored.
            if name.endswith(CONFIRMED_SUFFIX) and name[: -len(CONFIRMED_SUFFIX)] not in intents:
                raise OwnerTreeError(
                    "OWNER_RECORD_INVALID", f"{directory / name}: confirmation without an intent"
                )
        ordered = sorted(
            (
                OwnerRecord(intent=intent, confirmed=confirmed)
                for intent, confirmed in records
                if generation is None or intent.generation == generation
            ),
            key=lambda record: (record.intent.created_at_ns, record.intent.spawn_token),
        )
        return tuple(ordered)

    def owner_cleanup_receipt(
        self, campaign_id: str, batch_id: str, generation: int
    ) -> dict | None:
        if type(generation) is not int or generation < 1:
            raise OwnerTreeError("OWNER_RECORD_INVALID", f"generation={generation!r}")
        directory = self._batch_directory(campaign_id, batch_id, create=False)
        if directory is None:
            return None
        path = directory / f"generation-{generation}{RECEIPT_SUFFIX}"
        document = _read_document(path, required=False)
        return None if document is None else _receipt_from_directory(path, document)

    # -- the same two-step, written by a spawner that shares this root -------------------------

    def record_owner_intent(self, intent: OwnerIntent) -> OwnerIntent:
        """Write one intent document before its spawn.

        The first durable record of a spawn token wins, exactly like the supervisor store: a second
        identical write is idempotent, and a different intent under the same token is refused.
        """
        if not isinstance(intent, OwnerIntent):
            raise OwnerTreeError("OWNER_RECORD_INVALID", "intent")
        directory = self._batch_directory(intent.campaign_id, intent.batch_id, create=True)
        document = {"schema": INTENT_SCHEMA, **intent.as_document()}
        self._write_record(
            directory / f"{intent.spawn_token}{INTENT_SUFFIX}", document, "OWNER_INTENT_CONFLICT"
        )
        return intent

    def confirm_owner_process(self, confirmed: ConfirmedOwnerProcess) -> ConfirmedOwnerProcess:
        """Write one readback document next to the durable intent it belongs to.

        The token, not a coordinate argument, is what this call has: the intent is located first,
        because a confirmation for a spawn that was never intended must be refused rather than
        invent a directory the reaper would later read as an unconfirmed owner.
        """
        if not isinstance(confirmed, ConfirmedOwnerProcess):
            raise OwnerTreeError("OWNER_RECORD_INVALID", "confirmation")
        for directory in self._record_directories():
            intent_path = directory / f"{confirmed.spawn_token}{INTENT_SUFFIX}"
            if not intent_path.is_file():
                continue
            document = _read_document(intent_path, required=True)
            _intent_from_directory(
                intent_path,
                document,
                campaign_id=directory.parent.name,
                batch_id=directory.name,
                spawn_token=confirmed.spawn_token,
            )
            self._write_record(
                directory / f"{confirmed.spawn_token}{CONFIRMED_SUFFIX}",
                {"schema": CONFIRMATION_SCHEMA, **confirmed.as_document()},
                "OWNER_CONFIRMATION_CONFLICT",
            )
            return confirmed
        raise OwnerTreeError("OWNER_INTENT_MISSING", confirmed.spawn_token)

    def _write_record(
        self, path: Path, document: Mapping[str, object], conflict_code: str
    ) -> None:
        existing = _read_document(path, required=False)
        if existing is not None:
            if dict(existing) != dict(document):
                raise OwnerTreeError(conflict_code, str(path))
            return
        try:
            _write_document_exclusive(path, document)
        except FileExistsError:
            if dict(_read_document(path, required=True)) != dict(document):
                raise OwnerTreeError(conflict_code, str(path)) from None

    def record_owner_cleanup_receipt(self, receipt) -> None:
        """Commit one receipt document, idempotently, for the first reaper that got there."""
        campaign_id = getattr(receipt, "campaign_id", None)
        batch_id = getattr(receipt, "batch_id", None)
        generation = getattr(receipt, "generation", None)
        if type(generation) is not int or generation < 1:
            raise OwnerTreeError("OWNER_RECORD_INVALID", f"generation={generation!r}")
        directory = self._batch_directory(campaign_id, batch_id, create=True)
        path = directory / f"generation-{generation}{RECEIPT_SUFFIX}"
        existing = _read_document(path, required=False)
        if existing is not None:
            committed = _receipt_from_directory(path, existing)
            if _receipt_matches(committed, receipt):
                # The durable file is the answer; a second writer changes nothing.
                return
            raise OwnerTreeError(
                "OWNER_RECEIPT_CONFLICT", f"{path}: {committed['receipt_sha256']}"
            )
        document = _receipt_document(receipt, time.time_ns())
        try:
            _write_document_exclusive(path, document)
        except FileExistsError:
            # A concurrent reaper won the create; its document is the committed one.
            committed = _receipt_from_directory(path, _read_document(path, required=True))
            if not _receipt_matches(committed, receipt):
                raise OwnerTreeError(
                    "OWNER_RECEIPT_CONFLICT", f"{path}: {committed['receipt_sha256']}"
                ) from None

    def record_recovery_fence(
        self,
        campaign_id: str,
        batch_id: str,
        *,
        reason: str,
        command_id: str,
        generation: int | None = None,
    ) -> None:
        """Write the unresolved-tree document that keeps a fence auditable on disk.

        ``generation`` is the exact generation the reaper concluded, and the reaper always passes
        it. A caller that does not is answered by :meth:`_derived_fence_generation`, whose document
        says out loud that the number was derived instead of presenting it as fact.
        """
        directory = self._batch_directory(campaign_id, batch_id, create=True)
        if generation is None:
            generation, source = self._derived_fence_generation(campaign_id, batch_id, command_id)
            derived = True
        else:
            if type(generation) is not int or isinstance(generation, bool) or generation < 1:
                raise OwnerTreeError("OWNER_RECORD_INVALID", f"generation={generation!r}")
            derived, source = False, "caller"
        path = directory / f"generation-{generation}{UNRESOLVED_SUFFIX}"
        existing = _read_document(path, required=False)
        if existing is not None:
            if existing.get("schema") != UNRESOLVED_TREE_SCHEMA:
                raise OwnerTreeError("OWNER_RECORD_INVALID", f"{path}: schema")
            # The first durable reason is the audit trail; a later reaper never rewrites it.
            return
        _write_document_exclusive(
            path,
            {
                "schema": UNRESOLVED_TREE_SCHEMA,
                "campaign_id": campaign_id,
                "batch_id": batch_id,
                "generation": generation,
                "generation_derived": derived,
                "generation_source": source,
                "reason": str(reason),
                "command_id": str(command_id),
                "recorded_at_ns": time.time_ns(),
            },
        )

    # -- internals ---------------------------------------------------------------------------

    def _batch_directory(self, campaign_id: str, batch_id: str, *, create: bool) -> Path | None:
        campaign_id = _safe_record_name("campaign_id", campaign_id)
        batch_id = _safe_record_name("batch_id", batch_id)
        root = self._root_path()
        if root.exists() and not root.is_dir():
            raise OwnerTreeError("OWNER_RECORD_INVALID", f"{root}: not a directory")
        directory = root
        for name in (campaign_id, batch_id):
            directory = directory / name
            if directory.is_symlink():
                raise OwnerTreeError(
                    "OWNER_RECORD_INVALID", f"{directory}: symlinked owner directory"
                )
            if directory.exists() and not directory.is_dir():
                raise OwnerTreeError("OWNER_RECORD_INVALID", f"{directory}: not a directory")
            if not directory.is_dir():
                if not create:
                    return None
                directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        return directory

    def _root_path(self) -> Path:
        root = self.root
        if root.is_symlink():
            raise OwnerTreeError("OWNER_RECORD_INVALID", f"{root}: symlinked owner-tree root")
        return root

    def _record_directories(self) -> list[Path]:
        """Every batch directory under the root, for a lookup with no coordinates of its own."""
        root = self._root_path()
        if not root.is_dir():
            return []
        directories = []
        for campaign_name in sorted(os.listdir(root)):
            campaign = root / campaign_name
            if campaign.is_symlink() or not campaign.is_dir():
                continue
            for batch_name in sorted(os.listdir(campaign)):
                batch = campaign / batch_name
                if batch.is_symlink() or not batch.is_dir():
                    continue
                directories.append(batch)
        return directories

    def _derived_fence_generation(
        self, campaign_id: str, batch_id: str, command_id: str
    ) -> tuple[int, str]:
        """A generation for a fence whose caller did not name one.

        A trailing number in the command id is only trusted when the recorded tree corroborates it:
        ``spawn-<pid>`` also ends in a number, and a pid must never name a generation file.
        """
        recorded = sorted(
            {record.intent.generation for record in self.owner_tree(campaign_id, batch_id)}
        )
        match = re.search(r"-(\d+)$", str(command_id))
        if match is not None and int(match.group(1)) in recorded:
            return int(match.group(1)), "command_id"
        if recorded:
            return recorded[-1], "recorded_intents"
        return 1, "default"


def _receipt_matches(document: Mapping[str, object], receipt) -> bool:
    """Whether a committed receipt document already says exactly what this reaper concluded."""
    if (
        document.get("campaign_id") != receipt.campaign_id
        or document.get("batch_id") != receipt.batch_id
        or document.get("generation") != receipt.generation
    ):
        return False
    for name in ("reclaimed", "already_exited", "unresolved"):
        committed = document.get(name)
        if not isinstance(committed, list):
            return False
        if [dict(entry) for entry in committed] != [
            dict(entry) for entry in getattr(receipt, name, ())
        ]:
            return False
    return True


@dataclass(frozen=True, slots=True, init=False)
class CompositeOwnerRecords:
    """Several durable record sources read as one owner tree, in the order they are given.

    The service keeps its adapter record in its own store while the demo-side adapter writes its
    campaign, broker, worker and station records into the shared tree root, so a recovery reads
    both as one tree. A spawn token that exists in two durable copies is returned once: one spawn
    is one process group, and a reaper must never signal the same group twice.
    """

    sources: tuple

    def __init__(self, *sources) -> None:
        for source in sources:
            if not callable(getattr(source, "owner_tree", None)):
                raise OwnerTreeError("OWNER_RECORD_SOURCE_INVALID", type(source).__name__)
        object.__setattr__(self, "sources", tuple(sources))

    def owner_tree(
        self, campaign_id: str, batch_id: str, generation: int | None = None
    ) -> tuple[OwnerRecord, ...]:
        records: list[OwnerRecord] = []
        seen: set[str] = set()
        for source in self.sources:
            for record in source.owner_tree(campaign_id, batch_id, generation):
                spawn_token = record.intent.spawn_token
                if spawn_token in seen:
                    continue
                seen.add(spawn_token)
                records.append(record)
        return tuple(records)

    def owner_cleanup_receipt(
        self, campaign_id: str, batch_id: str, generation: int
    ) -> dict | None:
        for source in self.sources:
            read = getattr(source, "owner_cleanup_receipt", None)
            if read is None:
                continue
            document = read(campaign_id, batch_id, generation)
            if document is not None:
                return document
        return None

    def record_owner_cleanup_receipt(self, receipt) -> None:
        self._fan_out("record_owner_cleanup_receipt", receipt)

    def record_recovery_fence(
        self,
        campaign_id: str,
        batch_id: str,
        *,
        reason: str,
        command_id: str,
        generation: int | None = None,
    ) -> None:
        self._fan_out(
            "record_recovery_fence",
            campaign_id,
            batch_id,
            reason=reason,
            command_id=command_id,
            generation=generation,
        )

    def _fan_out(self, name: str, *args, **kwargs) -> None:
        """Write to every source that offers the method, then report the first refusal."""
        first_error: Exception | None = None
        for source in self.sources:
            method = getattr(source, name, None)
            if method is None:
                continue
            try:
                method(*args, **kwargs)
            except Exception as error:  # every durable sink still gets its write
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error


class OwnerTreeRecovery:
    """Reclaim one campaign's owner tree leaf-first, or refuse and keep the fence.

    ``store`` is any durable record source with ``owner_tree()``: the supervisor store, a
    :class:`DirectoryOwnerRecords` tree root, or a :class:`CompositeOwnerRecords` over both.
    """

    def __init__(
        self,
        store,
        *,
        receipt_root: Path,
        identity_reader: Callable[[int], object] = read_identity,
        terminator: Callable[..., object] = terminate_group,
        clock: Callable[[], int] = time.time_ns,
        stop_timeout_s: float = 3.0,
    ) -> None:
        if not callable(getattr(store, "owner_tree", None)):
            raise OwnerTreeError("OWNER_RECORD_SOURCE_INVALID", type(store).__name__)
        self._store = store
        self._receipt_root = Path(receipt_root)
        self._identity_reader = identity_reader
        self._terminator = terminator
        self._clock = clock
        self._stop_timeout_s = stop_timeout_s

    def recover_leaf_first(
        self,
        *,
        parent_binding: OwnerParentBinding,
        generation: int | None = None,
    ) -> OwnerCleanupReceipt:
        if not isinstance(parent_binding, OwnerParentBinding):
            raise OwnerTreeError("OWNER_PARENT_BINDING_INVALID")
        if generation is None:
            generation = parent_binding.generation
        if generation != parent_binding.generation:
            raise OwnerTreeError(
                "OWNER_RECOVERY_GENERATION_MISMATCH",
                f"requested {generation} != binding {parent_binding.generation}",
            )
        if parent_binding.generation < 1 or not parent_binding.recovery_owner:
            raise OwnerTreeError("OWNER_PARENT_BINDING_INVALID")

        committed = self._committed_receipt(parent_binding, generation)
        if committed is not None:
            # A second reaper for an already committed generation must not signal anything: the
            # first receipt is the durable answer, and re-deriving it could only repeat signals.
            return self._receipt_from_document(committed)

        records = self._store.owner_tree(
            parent_binding.campaign_id, parent_binding.batch_id, generation
        )
        reclaimed: list[dict[str, object]] = []
        already_exited: list[dict[str, object]] = []
        unresolved: list[dict[str, object]] = []
        for record in self._ordered(records):
            entry = self._base_entry(record)
            confirmed = record.confirmed
            if confirmed is None:
                # The intent is durable but no readback ever confirmed a process. Guessing a pid
                # here is exactly what this module refuses to do.
                unresolved.append({**entry, "reason": "INTENT_UNCONFIRMED"})
                continue
            identity = self._read(confirmed, entry, unresolved)
            if identity is None:
                if entry.get("reason") == "ALREADY_EXITED":
                    already_exited.append(entry)
                continue
            receipt = self._terminator(
                pgid=confirmed.pgid,
                leader_pid=confirmed.pid,
                timeout_s=self._stop_timeout_s,
            )
            if getattr(receipt, "clear", False):
                reclaimed.append({**entry, "outcome": "GROUP_CLEARED"})
            else:
                describe = getattr(receipt, "describe", lambda: "survivors remain")()
                unresolved.append(
                    {**entry, "reason": "OWNER_GROUP_SURVIVORS", "detail": describe}
                )

        if unresolved:
            self._record_fence(parent_binding, generation, unresolved)
            return OwnerCleanupReceipt(
                campaign_id=parent_binding.campaign_id,
                batch_id=parent_binding.batch_id,
                generation=generation,
                reclaimed=tuple(reclaimed),
                already_exited=tuple(already_exited),
                unresolved=tuple(unresolved),
                receipt_sha256="",
            )

        receipt = OwnerCleanupReceipt(
            campaign_id=parent_binding.campaign_id,
            batch_id=parent_binding.batch_id,
            generation=generation,
            reclaimed=tuple(reclaimed),
            already_exited=tuple(already_exited),
            unresolved=(),
            receipt_sha256="",
        )
        receipt = replace(receipt, receipt_sha256=self._write_receipt(receipt))
        self._store.record_owner_cleanup_receipt(receipt)
        return receipt

    # -- internals ---------------------------------------------------------------------------

    def _ordered(self, records: Sequence[OwnerRecord]) -> list[OwnerRecord]:
        return sorted(
            records,
            key=lambda record: (
                RECLAIM_ORDER.index(record.intent.role)
                if record.intent.role in RECLAIM_ORDER
                else len(RECLAIM_ORDER),
                record.intent.created_at_ns,
                record.intent.spawn_token,
            ),
        )

    def _base_entry(self, record: OwnerRecord) -> dict[str, object]:
        entry: dict[str, object] = {
            "spawn_token": record.intent.spawn_token,
            "role": record.intent.role,
            "generation": record.intent.generation,
        }
        if record.confirmed is not None:
            entry["pid"] = record.confirmed.pid
            entry["pgid"] = record.confirmed.pgid
            entry["started_ticks"] = record.confirmed.started_ticks
        return entry

    def _read(
        self,
        confirmed: ConfirmedOwnerProcess,
        entry: dict[str, object],
        unresolved: list[dict[str, object]],
    ):
        """Prove the live process is still the confirmed one, or classify why it is not."""
        try:
            identity = self._identity_reader(confirmed.pid)
        except ProcessIdentityError:
            entry["reason"] = "ALREADY_EXITED"
            entry["outcome"] = "ALREADY_EXITED"
            return None
        observed_pid = getattr(identity, "pid", None)
        observed_ticks = getattr(identity, "start_marker", None)
        observed_command = getattr(identity, "command_sha256", None)
        observed_pgid = getattr(identity, "pgid", None)
        state = getattr(identity, "state", None)
        if state == "Z":
            entry["reason"] = "ALREADY_EXITED"
            entry["outcome"] = "ALREADY_EXITED"
            return None
        if (
            observed_pid != confirmed.pid
            or observed_ticks != confirmed.started_ticks
            or observed_command != confirmed.command_sha256
            or observed_pgid != confirmed.pgid
        ):
            # A recycled pid, a re-birthed process or a different group: the record no longer names
            # a process this tree owns, so it is never signalled.
            unresolved.append(
                {
                    **entry,
                    "reason": "OWNER_IDENTITY_MISMATCH",
                    "observed": {
                        "pid": observed_pid,
                        "pgid": observed_pgid,
                        "started_ticks": observed_ticks,
                        "command_sha256": observed_command,
                    },
                }
            )
            return None
        return identity

    def _committed_receipt(self, parent_binding: OwnerParentBinding, generation: int):
        read = getattr(self._store, "owner_cleanup_receipt", None)
        if read is None:
            return None
        document = read(parent_binding.campaign_id, parent_binding.batch_id, generation)
        if document is None:
            return None
        if (
            document.get("campaign_id") != parent_binding.campaign_id
            or document.get("batch_id") != parent_binding.batch_id
            or document.get("generation") != generation
        ):
            raise OwnerTreeError("OWNER_RECEIPT_GENERATION_MISMATCH", str(generation))
        return document

    def _receipt_from_document(self, document) -> OwnerCleanupReceipt:
        return OwnerCleanupReceipt(
            campaign_id=str(document["campaign_id"]),
            batch_id=str(document["batch_id"]),
            generation=int(document["generation"]),
            reclaimed=tuple(dict(entry) for entry in document.get("reclaimed", ())),
            already_exited=tuple(dict(entry) for entry in document.get("already_exited", ())),
            unresolved=tuple(dict(entry) for entry in document.get("unresolved", ())),
            receipt_sha256=str(document["receipt_sha256"]),
        )

    def _record_fence(
        self, parent_binding: OwnerParentBinding, generation: int, unresolved
    ) -> None:
        record = getattr(self._store, "record_recovery_fence", None)
        if record is None:
            return
        reason = (
            f"OWNER_TREE_UNRESOLVED generation {generation}: "
            + "; ".join(
                f"{entry['role']} {entry.get('reason')}" for entry in unresolved
            )
        )
        record(
            parent_binding.campaign_id,
            parent_binding.batch_id,
            reason=reason,
            command_id=f"{parent_binding.recovery_owner}-{generation}",
            generation=generation,
        )

    def _write_receipt(self, receipt: OwnerCleanupReceipt) -> str:
        document = _receipt_document(receipt, self._clock())
        directory = self._receipt_root / receipt.campaign_id / receipt.batch_id
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / f"generation-{receipt.generation}.owner-cleanup-receipt.json"
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        try:
            descriptor = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
        except FileExistsError:
            # A concurrent reaper won the write. The durable file is the answer, not this call.
            existing = json.loads(path.read_text(encoding="utf-8"))
            return str(existing["receipt_sha256"])
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directory_fd = os.open(directory, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return str(document["receipt_sha256"])
