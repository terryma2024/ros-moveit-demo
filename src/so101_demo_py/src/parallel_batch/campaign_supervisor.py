"""The CampaignSupervisor: the real parent, spawner and reaper of a W2 campaign.

The approved design (2026-09-19, section 6.1) is explicit that this is not a side helper that
the Coordinator calls after it has already spawned children. The supervisor:

* holds the campaign-exclusive ``MPS:DEFAULT`` flock for the whole campaign;
* writes a durable ownership receipt *before* every spawn, so a crash between ``Popen`` and
  registration can never lose track of a child;
* is the parent of the Broker and both Workers, so it, and only it, can ``waitpid`` them;
* refuses the next campaign while any spawn intent is unresolved, any owned child is unstopped,
  or any cleanup cannot be proven complete;
* signals only processes whose PID *and* birth identity match its own receipt. Anything else is
  reported, never killed.

The receipt is the durable half of the contract: it is replaced atomically (write to a sibling
temporary file, ``fsync``, ``os.replace``), and it is the first thing a successor reads.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .start_guard_probe import ProcessIdentityRecord, read_process_identity

#: Receipt states for one child. Only ACTIVE children may be running.
SPAWNING = "SPAWNING"
ACTIVE = "ACTIVE"
FAILED = "FAILED"
STOPPED = "STOPPED"

#: Failure reasons that end up in the receipt.
ACK_TIMEOUT = "CHILD_ACK_TIMEOUT"
SPAWN_FAILED = "CHILD_SPAWN_FAILED"

#: A child whose birth identity could not be read is not promoted: we could not signal it safely.
IDENTITY_UNAVAILABLE = "CHILD_IDENTITY_UNAVAILABLE"

#: The roles a campaign is allowed to own, and the slots each role may occupy.
OWNED_ROLES: Mapping[str, int] = {"broker": 1, "worker": 2, "coordinator": 1}

#: The single campaign-exclusive resource this supervisor claims.
CLAIM_IDENTITY = "MPS:DEFAULT"

RECEIPT_NAME = "owner-receipt.json"
LOCK_NAME = "campaign-claim.lock"


class CampaignBlocked(RuntimeError):
    """A campaign cannot start, or an owned resource cannot be proven clean."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class RegistrationAck:
    """What a child must report before it is allowed to run."""

    pid: int
    process_group: int
    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("pid", "process_group"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise CampaignBlocked("ACK_INVALID", f"{name}={value!r}")
        if not isinstance(self.argv, tuple) or not self.argv:
            raise CampaignBlocked("ACK_INVALID", "argv missing")

    def to_document(self) -> dict:
        return {"pid": self.pid, "process_group": self.process_group,
                "argv": list(self.argv)}

    @staticmethod
    def from_document(document: object) -> "RegistrationAck":
        if not isinstance(document, Mapping):
            raise CampaignBlocked("ACK_INVALID", "ack is not a mapping")
        try:
            pid = int(document["pid"])
            process_group = int(document["pgid"])
            argv = tuple(str(item) for item in document["argv"])
        except (KeyError, TypeError, ValueError) as error:
            raise CampaignBlocked("ACK_INVALID", str(error)) from error
        return RegistrationAck(pid=pid, process_group=process_group, argv=argv)


@dataclass(frozen=True)
class SpawnIntent:
    """The durable record written before ``Popen``. Its presence forbids the next campaign."""

    role: str
    slot: int
    argv: tuple[str, ...]
    nonce: str
    status: str = SPAWNING
    pid: int | None = None
    process_group: int | None = None
    birth_identity: int | None = None
    ack: RegistrationAck | None = None
    reason: str = ""
    recorded_monotonic_s: float = 0.0

    def to_document(self) -> dict:
        return {
            "role": self.role,
            "slot": self.slot,
            "argv": list(self.argv),
            "nonce": self.nonce,
            "status": self.status,
            "pid": self.pid,
            "process_group": self.process_group,
            "birth_identity": self.birth_identity,
            "ack": None if self.ack is None else self.ack.to_document(),
            "reason": self.reason,
            "recorded_monotonic_s": self.recorded_monotonic_s,
        }

    @staticmethod
    def from_document(document: object) -> "SpawnIntent":
        if not isinstance(document, Mapping):
            raise CampaignBlocked("RECEIPT_CORRUPT", "child entry is not a mapping")
        try:
            ack_document = document.get("ack")
            return SpawnIntent(
                role=str(document["role"]),
                slot=int(document["slot"]),
                argv=tuple(str(item) for item in document["argv"]),
                nonce=str(document["nonce"]),
                status=str(document["status"]),
                pid=None if document.get("pid") is None else int(document["pid"]),
                process_group=(None if document.get("process_group") is None
                               else int(document["process_group"])),
                birth_identity=(None if document.get("birth_identity") is None
                                else int(document["birth_identity"])),
                ack=None if ack_document is None else RegistrationAck.from_document(ack_document),
                reason=str(document.get("reason") or ""),
                recorded_monotonic_s=float(document.get("recorded_monotonic_s") or 0.0),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise CampaignBlocked("RECEIPT_CORRUPT", str(error)) from error

    @property
    def resolved(self) -> bool:
        """A spawn intent is resolved once it is no longer SPAWNING."""

        return self.status != SPAWNING


@dataclass(frozen=True)
class OwnershipReceipt:
    """The durable ownership record for one campaign."""

    campaign_id: str
    owner_pid: int
    owner_birth_identity: int
    claim_identity: str
    children: tuple[SpawnIntent, ...] = ()
    coordinator_pid: int | None = None
    coordinator_heartbeat_monotonic_s: float | None = None
    written_monotonic_s: float = 0.0

    def to_document(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "owner_pid": self.owner_pid,
            "owner_birth_identity": self.owner_birth_identity,
            "claim_identity": self.claim_identity,
            "children": [child.to_document() for child in self.children],
            "coordinator_pid": self.coordinator_pid,
            "coordinator_heartbeat_monotonic_s": self.coordinator_heartbeat_monotonic_s,
            "written_monotonic_s": self.written_monotonic_s,
        }

    @staticmethod
    def from_document(document: object) -> "OwnershipReceipt":
        if not isinstance(document, Mapping):
            raise CampaignBlocked("RECEIPT_CORRUPT", "receipt is not a mapping")
        try:
            return OwnershipReceipt(
                campaign_id=str(document["campaign_id"]),
                owner_pid=int(document["owner_pid"]),
                owner_birth_identity=int(document["owner_birth_identity"]),
                claim_identity=str(document["claim_identity"]),
                children=tuple(
                    SpawnIntent.from_document(item) for item in document.get("children") or ()
                ),
                coordinator_pid=(None if document.get("coordinator_pid") is None
                                 else int(document["coordinator_pid"])),
                coordinator_heartbeat_monotonic_s=(
                    None if document.get("coordinator_heartbeat_monotonic_s") is None
                    else float(document["coordinator_heartbeat_monotonic_s"])),
                written_monotonic_s=float(document.get("written_monotonic_s") or 0.0),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise CampaignBlocked("RECEIPT_CORRUPT", str(error)) from error

    @property
    def unresolved(self) -> tuple[SpawnIntent, ...]:
        return tuple(child for child in self.children if not child.resolved)

    @property
    def live_children(self) -> tuple[SpawnIntent, ...]:
        return tuple(child for child in self.children if child.status == ACTIVE)


@dataclass(frozen=True)
class CleanupReceipt:
    """What a cleanup actually achieved. Reported, never assumed."""

    stopped: tuple[int, ...] = ()
    still_running: tuple[int, ...] = ()
    live_children: tuple[int, ...] = ()
    detail: str = ""

    @property
    def cleanup_complete(self) -> bool:
        return not self.still_running and not self.live_children


@dataclass(frozen=True)
class OrphanReport:
    """Processes found in a receipt that this supervisor must not signal."""

    foreign: tuple[int, ...] = ()
    owned: tuple[int, ...] = ()
    signalled: tuple[int, ...] = ()
    detail: str = ""


class CampaignSupervisor:
    """Owns one campaign: the claim, the durable receipt, and every child process."""

    def __init__(self, campaign_id: str, *, state_root: Path, claim_identity: str = CLAIM_IDENTITY,
                 ack_timeout_s: float = 10.0, identity_timeout_s: float = 2.0,
                 terminate_grace_s: float = 0.5,
                 kill_grace_s: float = 0.5, clock: Callable[[], float] = time.monotonic,
                 popen: Callable[..., object] = subprocess.Popen,
                 identity_reader: Callable[[int], ProcessIdentityRecord | None]
                 = read_process_identity,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if not isinstance(campaign_id, str) or not campaign_id:
            raise CampaignBlocked("CAMPAIGN_ID")
        self.campaign_id = campaign_id
        self.state_root = Path(state_root)
        self.claim_identity = claim_identity
        self.ack_timeout_s = float(ack_timeout_s)
        #: The identity read gets its own short bound instead of reusing the ACK timeout. A live
        #: child reports its identity at once; an exited one never will.
        self.identity_timeout_s = float(identity_timeout_s)
        self.terminate_grace_s = float(terminate_grace_s)
        self.kill_grace_s = float(kill_grace_s)
        self._clock = clock
        self._popen = popen
        self._identity_reader = identity_reader
        self._sleep = sleep
        self._claim_descriptor: int | None = None
        self._receipt: OwnershipReceipt | None = None

    # -- paths ---------------------------------------------------------------------------

    @property
    def lock_path(self) -> Path:
        return self.state_root / LOCK_NAME

    @property
    def receipt_path(self) -> Path:
        return self.state_root / RECEIPT_NAME

    @property
    def holds_claim(self) -> bool:
        return self._claim_descriptor is not None

    # -- claim ---------------------------------------------------------------------------

    def acquire_claim(self) -> None:
        """Take the campaign-exclusive flock, refusing while an old receipt is unresolved."""

        if self.holds_claim:
            raise CampaignBlocked("CAMPAIGN_CLAIM_HELD", "this supervisor already holds it")
        self.state_root.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(descriptor)
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise CampaignBlocked(
                    "CAMPAIGN_CLAIM_HELD", f"{self.claim_identity} is held by another campaign"
                ) from error
            raise CampaignBlocked("CAMPAIGN_CLAIM_FAILED", str(error)) from error
        self._claim_descriptor = descriptor

        existing = self.read_receipt()
        if existing is not None and existing.unresolved:
            self.release_claim()
            raise CampaignBlocked(
                "CAMPAIGN_RECEIPT_UNRESOLVED",
                f"{len(existing.unresolved)} spawn intent(s) were never resolved",
            )
        self._receipt = OwnershipReceipt(
            campaign_id=self.campaign_id,
            owner_pid=os.getpid(),
            owner_birth_identity=self._own_birth_identity(),
            claim_identity=self.claim_identity,
            children=(),
            written_monotonic_s=self._clock(),
        )
        self._write_receipt(self._receipt)

    def _own_birth_identity(self) -> int:
        identity = self._identity_reader(os.getpid())
        return 0 if identity is None else identity.start_time_ticks

    def release_claim(self) -> None:
        """Release the flock. The receipt is cleared only when nothing is unresolved."""

        descriptor = self._claim_descriptor
        if descriptor is None:
            return
        self._claim_descriptor = None
        if self._receipt is not None and not self._receipt.unresolved:
            self._write_receipt(OwnershipReceipt(
                campaign_id=self._receipt.campaign_id,
                owner_pid=self._receipt.owner_pid,
                owner_birth_identity=self._receipt.owner_birth_identity,
                claim_identity=self._receipt.claim_identity,
                children=tuple(child for child in self._receipt.children
                               if child.status != ACTIVE),
                coordinator_pid=self._receipt.coordinator_pid,
                coordinator_heartbeat_monotonic_s=(
                    self._receipt.coordinator_heartbeat_monotonic_s),
                written_monotonic_s=self._clock(),
            ))
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def abandon_claim_for_test(self) -> None:
        """Drop the file descriptor without unlocking or clearing: a simulated crash."""

        descriptor = self._claim_descriptor
        self._claim_descriptor = None
        if descriptor is not None:
            os.close(descriptor)

    # -- receipt -------------------------------------------------------------------------

    def read_receipt(self) -> OwnershipReceipt | None:
        if not self.receipt_path.exists():
            return None
        try:
            document = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise CampaignBlocked("RECEIPT_CORRUPT", str(error)) from error
        return OwnershipReceipt.from_document(document)

    @property
    def receipt(self) -> OwnershipReceipt:
        if self._receipt is None:
            raise CampaignBlocked("CAMPAIGN_RECEIPT_MISSING", "no claim is held")
        return self._receipt

    def _write_receipt(self, receipt: OwnershipReceipt) -> None:
        """Atomically replace the receipt: sibling temp file, fsync, os.replace, fsync dir."""

        self.state_root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(receipt.to_document(), indent=2, sort_keys=True) + "\n"
        temporary = self.receipt_path.with_suffix(".json.part")
        descriptor = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            os.write(descriptor, payload.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, self.receipt_path)
        directory = os.open(self.state_root, os.O_RDONLY)
        try:
            os.fsync(directory)
        except OSError:  # pragma: no cover - not every filesystem allows directory fsync
            pass
        finally:
            os.close(directory)
        self._receipt = receipt

    def _update_child(self, intent: SpawnIntent) -> None:
        current = self.receipt
        children = tuple(intent if child.role == intent.role and child.slot == intent.slot
                         else child for child in current.children)
        self._write_receipt(OwnershipReceipt(
            campaign_id=current.campaign_id,
            owner_pid=current.owner_pid,
            owner_birth_identity=current.owner_birth_identity,
            claim_identity=current.claim_identity,
            children=children,
            coordinator_pid=current.coordinator_pid,
            coordinator_heartbeat_monotonic_s=current.coordinator_heartbeat_monotonic_s,
            written_monotonic_s=self._clock(),
        ))

    # -- spawn ---------------------------------------------------------------------------

    def begin_spawn(self, *, role: str, slot: int, argv: Sequence[str], nonce: str) -> SpawnIntent:
        """Write the durable SPAWNING intent. Nothing may be spawned before this returns."""

        if role not in OWNED_ROLES:
            raise CampaignBlocked("UNOWNED_ROLE", role)
        if type(slot) is not int or slot < 0 or slot >= OWNED_ROLES[role]:
            raise CampaignBlocked("UNOWNED_ROLE", f"{role}[{slot}]")
        if not isinstance(argv, (list, tuple)) or not argv:
            raise CampaignBlocked("SPAWN_ARGV", "argv is required")
        if not isinstance(nonce, str) or not nonce:
            raise CampaignBlocked("SPAWN_NONCE", "nonce is required")
        current = self.receipt
        for child in current.children:
            if child.role == role and child.slot == slot and child.status != STOPPED:
                raise CampaignBlocked("DUPLICATE_ROLE_SLOT", f"{role}[{slot}]")
        intent = SpawnIntent(
            role=role, slot=slot, argv=tuple(str(item) for item in argv), nonce=nonce,
            status=SPAWNING, recorded_monotonic_s=self._clock(),
        )
        self._write_receipt(OwnershipReceipt(
            campaign_id=current.campaign_id,
            owner_pid=current.owner_pid,
            owner_birth_identity=current.owner_birth_identity,
            claim_identity=current.claim_identity,
            children=tuple(child for child in current.children
                           if not (child.role == role and child.slot == slot))
            + (intent,),
            coordinator_pid=current.coordinator_pid,
            coordinator_heartbeat_monotonic_s=current.coordinator_heartbeat_monotonic_s,
            written_monotonic_s=self._clock(),
        ))
        return intent

    def spawn(self, *, role: str, slot: int, argv: Sequence[str], nonce: str,
              ack_path: Path, ack_timeout_s: float | None = None,
              environment: Mapping[str, str] | None = None,
              stderr: object | None = None) -> SpawnIntent:
        """Spawn one owned child and promote it to ACTIVE only after its registered ACK."""

        intent = self.begin_spawn(role=role, slot=slot, argv=argv, nonce=nonce)
        ack_path = Path(ack_path)
        if ack_path.exists():
            ack_path.unlink()
        try:
            child = self._popen(
                list(intent.argv),
                env=None if environment is None else dict(environment),
                start_new_session=True,
                # A child's own diagnostics are evidence: an optional sink keeps a failing child
                # from being silent, which is exactly how the identity race stayed hidden.
                **({} if stderr is None else {"stderr": stderr}),
            )
        except OSError as error:
            self._update_child(replace(intent, status=FAILED, reason=SPAWN_FAILED,
                                       recorded_monotonic_s=self._clock()))
            raise CampaignBlocked(SPAWN_FAILED, str(error)) from error

        pid = int(child.pid)
        timeout = self.ack_timeout_s if ack_timeout_s is None else float(ack_timeout_s)
        # Capture the birth identity *now*, while the child is certainly still alive, and before
        # the ACK wait. Reading it only after the wait is a real race: a short-lived child can
        # finish and exit first, and an exited child is unidentifiable, so it could never be
        # signalled safely. This was measured on macOS, where the read returns None once gone.
        birth = self._read_birth_identity(pid, deadline=self._clock() + self.identity_timeout_s)
        deadline = self._clock() + timeout
        ack: RegistrationAck | None = None
        while self._clock() < deadline:
            if ack_path.exists():
                try:
                    ack = RegistrationAck.from_document(
                        json.loads(ack_path.read_text(encoding="utf-8")))
                except (OSError, ValueError, CampaignBlocked):
                    ack = None
                else:
                    break
            if child.poll() is not None:
                break
            self._sleep(0.02)

        if ack is None or ack.pid != pid:
            self._stop_exact(child, pid)
            failed = replace(intent, status=FAILED, pid=pid, reason=ACK_TIMEOUT,
                             recorded_monotonic_s=self._clock())
            self._update_child(failed)
            return failed

        # The identity captured at spawn is what makes later signalling safe. Re-check it once
        # before promoting: if it changed or vanished, the PID was reused or the child exited, and
        # promoting it would arm a signal against an unknown process.
        identity = self._read_birth_identity(
            pid, deadline=self._clock() + self.identity_timeout_s)
        if birth is None or identity is None or \
                identity.start_time_ticks != birth.start_time_ticks:
            self._stop_exact(child, pid)
            failed = replace(intent, status=FAILED, pid=pid, reason=IDENTITY_UNAVAILABLE,
                             recorded_monotonic_s=self._clock())
            self._update_child(failed)
            return failed

        active = replace(intent, status=ACTIVE, pid=pid, process_group=ack.process_group,
                         birth_identity=identity.start_time_ticks,
                         ack=ack, recorded_monotonic_s=self._clock())
        self._update_child(active)
        return active

    def _read_birth_identity(self, pid: int, *, deadline: float):
        """Retry the identity read until the deadline; return None if it never resolved."""

        while True:
            identity = self._identity_reader(pid)
            if identity is not None and identity.start_time_ticks > 0:
                return identity
            if self._clock() >= deadline:
                return None
            self._sleep(0.02)

    # -- stop, exactly -------------------------------------------------------------------

    def is_gone(self, pid: int) -> bool:
        """True once the process is gone AND reaped (no zombie left for us to collect)."""

        if not self._owns(pid):
            identity = self._identity_reader(pid)
            return identity is None
        try:
            reaped, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return self._identity_reader(pid) is None
        except OSError:
            return False
        return reaped == pid or self._identity_reader(pid) is None

    def _owns(self, pid: int) -> bool:
        if self._receipt is None:
            return False
        return any(child.pid == pid and child.status == ACTIVE for child in self._receipt.children)

    def _matches_receipt(self, pid: int, birth_identity: int | None) -> bool:
        """PID *and* birth identity must match. A reused PID is never signalled."""

        if self._receipt is None:
            return False
        for child in self._receipt.children:
            if child.pid != pid or child.status != ACTIVE:
                continue
            if child.birth_identity is None or birth_identity is None:
                return False
            return child.birth_identity == birth_identity
        return False

    def _stop_exact(self, child, pid: int) -> bool:
        """Stop and reap one child this supervisor spawned in this call. Never a stranger."""

        reaped = False
        for number, grace in ((signal.SIGTERM, self.terminate_grace_s),
                              (signal.SIGKILL, self.kill_grace_s)):
            try:
                os.kill(pid, number)
            except ProcessLookupError:
                pass
            except PermissionError:
                return False
            moment = self._clock()
            while self._clock() - moment < grace:
                if child.poll() is not None:
                    break
                self._sleep(0.02)
            try:
                os.waitpid(pid, os.WNOHANG)
            except (ChildProcessError, OSError):
                pass
            if child.poll() is not None:
                reaped = True
                break
        try:
            child.wait(timeout=self.kill_grace_s)
            reaped = True
        except Exception:  # noqa: BLE001 - the poll below is the real check
            pass
        return reaped and child.poll() is not None

    def terminate_all(self) -> CleanupReceipt:
        """Stop and reap every owned child by exact identity, then clear the receipt."""

        stopped: list[int] = []
        still_running: list[int] = []
        if self._receipt is not None:
            for child in self.receipt.children:
                if child.status != ACTIVE or child.pid is None:
                    continue
                identity = self._identity_reader(child.pid)
                if identity is None:
                    stopped.append(child.pid)
                    continue
                if child.birth_identity is not None and \
                        identity.start_time_ticks != child.birth_identity:
                    # The PID was reused by something we do not own: report, never signal.
                    still_running.append(child.pid)
                    continue
                if self._stop_pid_exact(child.pid):
                    stopped.append(child.pid)
                else:
                    still_running.append(child.pid)
        live = tuple(child.pid for child in (self._receipt.children if self._receipt else ())
                     if child.pid is not None and self._identity_reader(child.pid) is not None)
        receipt = CleanupReceipt(
            stopped=tuple(stopped), still_running=tuple(still_running), live_children=live,
            detail="owned cleanup",
        )
        if receipt.cleanup_complete and self._receipt is not None:
            self._write_receipt(OwnershipReceipt(
                campaign_id=self._receipt.campaign_id,
                owner_pid=self._receipt.owner_pid,
                owner_birth_identity=self._receipt.owner_birth_identity,
                claim_identity=self._receipt.claim_identity,
                children=(),
                coordinator_pid=self._receipt.coordinator_pid,
                coordinator_heartbeat_monotonic_s=(
                    self._receipt.coordinator_heartbeat_monotonic_s),
                written_monotonic_s=self._clock(),
            ))
        return receipt

    def _stop_pid_exact(self, pid: int) -> bool:
        for number, grace in ((signal.SIGTERM, self.terminate_grace_s),
                              (signal.SIGKILL, self.kill_grace_s)):
            try:
                os.kill(pid, number)
            except ProcessLookupError:
                return True
            except PermissionError:
                return False
            moment = self._clock()
            while self._clock() - moment < grace:
                if self._identity_reader(pid) is None:
                    break
                self._sleep(0.02)
            try:
                os.waitpid(pid, os.WNOHANG)
            except (ChildProcessError, OSError):
                pass
            if self._identity_reader(pid) is None:
                return True
        return self._identity_reader(pid) is None

    # -- coordinator liveness -------------------------------------------------------------

    def note_heartbeat(self, *, owner_pid: int, monotonic_s: float | None = None) -> None:
        current = self.receipt
        self._write_receipt(OwnershipReceipt(
            campaign_id=current.campaign_id,
            owner_pid=current.owner_pid,
            owner_birth_identity=current.owner_birth_identity,
            claim_identity=current.claim_identity,
            children=current.children,
            coordinator_pid=int(owner_pid),
            coordinator_heartbeat_monotonic_s=(
                self._clock() if monotonic_s is None else float(monotonic_s)),
            written_monotonic_s=self._clock(),
        ))

    def check_coordinator(self, *, now_monotonic_s: float | None = None, timeout_s: float,
                          owner_alive: Callable[[int], bool] | None = None) -> str:
        """Decide whether the Coordinator is still driving this campaign.

        ``ALIVE`` keeps the campaign. ``OWNER_GONE`` and ``HEARTBEAT_LOST`` both trigger the
        bounded recovery: stop the owned children exactly, keep the claim, and leave the
        receipt in a state a successor can audit.
        """

        current = self.receipt
        pid = current.coordinator_pid
        if pid is None:
            return "NO_COORDINATOR"
        alive = owner_alive or (lambda candidate: self._identity_reader(candidate) is not None)
        if not alive(pid):
            self.terminate_all()
            return "OWNER_GONE"
        last = current.coordinator_heartbeat_monotonic_s
        now = self._clock() if now_monotonic_s is None else float(now_monotonic_s)
        if last is None or (now - last) > float(timeout_s):
            self.terminate_all()
            return "HEARTBEAT_LOST"
        return "ALIVE"

    # -- audit ----------------------------------------------------------------------------

    def inspect_orphans(self) -> OrphanReport:
        """Report receipt entries we cannot claim. Never signals anything during an audit.

        The receipt is read from disk when this supervisor holds no claim, because auditing a
        previous campaign's leftovers is exactly the situation where nobody holds the claim.
        """

        receipt = self._receipt if self._receipt is not None else self.read_receipt()
        foreign: list[int] = []
        owned: list[int] = []
        if receipt is None:
            return OrphanReport(detail="no receipt to audit")
        for child in receipt.children:
            if child.pid is None:
                continue
            identity = self._identity_reader(child.pid)
            if identity is None:
                continue
            if child.status == ACTIVE and child.birth_identity == identity.start_time_ticks:
                owned.append(child.pid)
            else:
                foreign.append(child.pid)
        return OrphanReport(foreign=tuple(foreign), owned=tuple(owned),
                            detail="reported only; no signal was sent")
