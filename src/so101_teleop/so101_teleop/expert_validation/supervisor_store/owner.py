"""Execution owner intent, process, tree, cleanup, recovery fence and operator recovery."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
import uuid

from so101_teleop.expert_validation.coordinator import CoordinatorBinding, CoordinatorStartRequest
from so101_teleop.expert_validation.models import (
    ExecutionOwnerIntent,
    OwnedExecutionRecord,
)
from so101_teleop.expert_validation.owner_tree import (
    ConfirmedOwnerProcess,
    OwnerIntent,
    OwnerRecord,
)
from so101_teleop.expert_validation.supervisor_store.schema import (
    StoreConflict,
    _json,
    _owner_intent_from_row,
    _sha,
)
from so101_teleop.process_identity import (
    IDENTITY_EXITED,
    command_fingerprint,
    group_has_live_descendants,
    identity_state,
)


class StoreOwner:
    def reconcile_exited_execution_owner(self, batch_id: str) -> bool:
        """Retire one ``RUNNING`` owner whose recorded process is proven gone; never assume it.

        The only evidence that retires an owner is a proven-absent identity: the platform reports no
        process at the recorded pid, or the pid now carries a different start marker, and the
        recorded process group holds no live process other than that leader. Everything else - a
        live process, an identity this caller may not read, a row without a recorded identity, a
        group that cannot be read or still has members - leaves the row ``RUNNING`` and returns
        ``False``, because an unknown owner must keep blocking.

        The transition is idempotent and moves exactly the row the proof was read from: the update
        is guarded on the batch, the spawn token and the whole recorded identity, so an unrelated
        owner row can never be overwritten and a second call changes nothing. ``True`` means the
        post-condition holds - this batch has no standing ``RUNNING`` owner any more.
        """

        row = self._connection.execute(
            "SELECT * FROM owned_execution WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if row is None or row["state"] != "RUNNING":
            return True
        if not self._owner_identity_proven_gone(row):
            return False
        cursor = self._connection.execute(
            "UPDATE owned_execution SET state = ? "
            "WHERE batch_id = ? AND state = 'RUNNING' AND spawn_token = ? "
            "AND pid IS ? AND pgid IS ? AND started_ticks IS ?",
            (
                self.OWNER_STATE_EXITED,
                batch_id,
                row["spawn_token"],
                row["pid"],
                row["pgid"],
                row["started_ticks"],
            ),
        )
        if cursor.rowcount != 1:
            # The row moved under the proof. Nothing may be retired without knowing which row was.
            raise StoreConflict("EXECUTION_OWNER_RECONCILE_MISMATCH")
        return True

    def _owner_identity_proven_gone(self, row) -> bool:
        """Whether the identity of one ``RUNNING`` owner row is proven not to be running.

        The identity read and the group read are the same machinery the supervisor's own
        unresolved-owner question uses, so the store and the supervisor cannot disagree about one
        process. A row that never recorded an identity (a spawn intent that was never acknowledged)
        is not this method's business: it stays ``INTENT`` and keeps blocking as unknowable.
        """

        # A group id this reader cannot even ask about would answer "no members", so the recorded
        # coordinates are required to be a real identity before either read is consulted.
        if type(row["pid"]) is not int or row["pid"] <= 0:
            return False
        if type(row["pgid"]) is not int or row["pgid"] <= 0:
            return False
        if type(row["started_ticks"]) is not int or row["started_ticks"] < 0:
            return False
        if (
            identity_state(row["pid"], row["started_ticks"], row["argv_sha256"])
            != IDENTITY_EXITED
        ):
            return False
        return not group_has_live_descendants(row["pgid"], row["pid"])

    def _check_no_owner_or_fence(
        self, campaign_id: str | None, *, fence: str, active: str, unknown: str
    ) -> None:
        """Refuse when an owner is live or unknowable, or when a recovery fence stands.

        ``campaign_id=None`` asks the host-wide question a *new* run has to answer: this host runs
        one live execution, so an unresolved owner anywhere blocks a new authorization. A named
        campaign asks the narrower question a retry of that campaign asks.

        A ``RUNNING`` row is not live by itself: the state is written once, when the owner is
        acknowledged, and nothing in this store ever writes it back. So the row is reconciled
        against the recorded process first, and only a proven-dead owner stops blocking - a live
        one, an unreadable one and a row in any state this build does not know all still refuse.
        """

        if campaign_id is None:
            fenced = self.has_recovery_fence()
        else:
            fenced = self.recovery_fence(campaign_id) is not None
        if fenced:
            raise StoreConflict(fence)
        if campaign_id is None:
            rows = self._connection.execute(
                "SELECT o.state, o.batch_id FROM owned_execution o "
                "JOIN campaign_batches b USING (batch_id)"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT o.state, o.batch_id FROM owned_execution o "
                "JOIN campaign_batches b USING (batch_id) WHERE b.campaign_id = ?",
                (campaign_id,),
            ).fetchall()
        for row in rows:
            if row["state"] == "RUNNING":
                if not self.reconcile_exited_execution_owner(row["batch_id"]):
                    raise StoreConflict(active)
                continue
            if row["state"] == "INTENT":
                raise StoreConflict(unknown)
            if row["state"] != self.OWNER_STATE_EXITED:
                # A state this build cannot reason about is not a retired owner.
                raise StoreConflict(active)
        statement = (
            "SELECT i.spawn_token FROM owner_intents i "
            "LEFT JOIN owner_processes p ON p.spawn_token = i.spawn_token "
            "JOIN campaign_batches b ON b.batch_id = i.batch_id "
            "WHERE p.spawn_token IS NULL AND b.cleanup_receipt_sha256 IS NULL"
        )
        parameters: tuple = ()
        if campaign_id is not None:
            statement += " AND i.campaign_id = ?"
            parameters = (campaign_id,)
        unconfirmed = self._connection.execute(
            statement + " LIMIT 1", parameters
        ).fetchone()
        if unconfirmed is not None:
            raise StoreConflict(unknown)

    def record_execution_owner_intent(self, intent) -> str:
        binding = intent.control_binding if isinstance(intent, CoordinatorStartRequest) else None
        if not isinstance(intent, ExecutionOwnerIntent):
            request = intent
            owner_kind = (
                "ADAPTIVE_WRAPPER" if hasattr(request, "runtime_root") else "COORDINATOR"
            )
            executable = request.argv[0]
            runtime_digest = hashlib.sha256(executable.encode("utf-8")).hexdigest()
            intent = ExecutionOwnerIntent(
                batch_id=request.batch_id,
                owner_kind=owner_kind,
                spawn_token="spawn-" + uuid.uuid4().hex,
                expected_executable=executable,
                # The durable fingerprint is the requested command line without its launcher: the
                # kernel may rewrite argv[0] when an interpreter re-execs itself.
                argv_sha256=command_fingerprint(request.argv),
                environment_sha256=_sha(dict(request.environment)),
                source_commit="UNKNOWN",
                install_prefix=Path(executable).parent,
                runtime_sha256=runtime_digest,
                control_socket=getattr(request, "control_socket", None),
            )
        with self._transaction():
            if binding is not None:
                self._validate_fixed_binding(binding)
            try:
                self._connection.execute(
                    "INSERT INTO owned_execution "
                    "(batch_id, owner_kind, state, spawn_token, expected_executable, argv_sha256, "
                    "environment_sha256, source_commit, install_prefix, runtime_sha256, control_socket) "
                    "VALUES (?, ?, 'INTENT', ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        intent.batch_id,
                        intent.owner_kind,
                        intent.spawn_token,
                        intent.expected_executable,
                        intent.argv_sha256,
                        intent.environment_sha256,
                        # Debug metadata column: a no-Git deployment records UNKNOWN
                        # rather than a fabricated commit, and never refuses.
                        intent.source_commit or "UNKNOWN",
                        str(intent.install_prefix),
                        intent.runtime_sha256,
                        str(intent.control_socket) if intent.control_socket else None,
                    ),
                )
                if binding is not None:
                    self._connection.execute(
                        "INSERT INTO fixed_control_bindings VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (binding.batch_id, binding.campaign_id, str(binding.batch_root),
                         str(binding.control_socket), binding.coordinator_epoch,
                         binding.control_token, binding.control_token_sha256),
                    )
            except sqlite3.IntegrityError as error:
                raise StoreConflict("EXECUTION_OWNER_INTENT_CONFLICT") from error
        return intent.spawn_token

    def record_owner_intent(self, intent: OwnerIntent) -> OwnerIntent:
        """Persist one spawn intent before its real spawn.

        The intent table is the only thing a recovery may trust about a spawn that never
        confirmed: it must therefore exist *before* ``Popen``, and a duplicate token may never be
        overwritten by a different intent.
        """
        if not isinstance(intent, OwnerIntent):
            raise StoreConflict("OWNER_INTENT_INVALID")
        with self._transaction():
            try:
                self._connection.execute(
                    "INSERT INTO owner_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        intent.spawn_token,
                        intent.campaign_id,
                        intent.batch_id,
                        intent.role,
                        intent.generation,
                        intent.parent_spawn_token,
                        intent.expected_executable,
                        intent.argv_sha256,
                        1 if intent.own_session else 0,
                        intent.created_at_ns,
                    ),
                )
            except sqlite3.IntegrityError as error:
                try:
                    existing = self.owner_intent(intent.spawn_token)
                except Exception:
                    existing = None
                if existing != intent:
                    raise StoreConflict("OWNER_INTENT_CONFLICT") from error
        return intent

    def owner_intent(self, spawn_token: str) -> OwnerIntent | None:
        row = self._connection.execute(
            "SELECT * FROM owner_intents WHERE spawn_token=?", (spawn_token,)
        ).fetchone()
        return None if row is None else _owner_intent_from_row(row)

    def confirm_owner_process(self, confirmed: ConfirmedOwnerProcess) -> ConfirmedOwnerProcess:
        """Persist the readback identity of a spawned process.

        Confirmation is only accepted for an intent that is already durable: an unconfirmed spawn
        is exactly the case recovery must refuse to guess about.
        """
        if not isinstance(confirmed, ConfirmedOwnerProcess):
            raise StoreConflict("OWNER_CONFIRMATION_INVALID")
        with self._transaction():
            if self.owner_intent(confirmed.spawn_token) is None:
                raise StoreConflict("OWNER_INTENT_MISSING")
            try:
                self._connection.execute(
                    "INSERT INTO owner_processes VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        confirmed.spawn_token,
                        confirmed.pid,
                        confirmed.pgid,
                        confirmed.started_ticks,
                        confirmed.command_sha256,
                        confirmed.confirmed_at_ns,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise StoreConflict("OWNER_CONFIRMATION_CONFLICT") from error
        return confirmed

    def owner_tree(
        self, campaign_id: str, batch_id: str, generation: int | None = None
    ) -> tuple[OwnerRecord, ...]:
        """Every durable intent of one campaign/batch, oldest first, with its confirmation."""
        query = (
            "SELECT i.*, p.pid AS confirmed_pid, p.pgid AS confirmed_pgid, "
            "p.started_ticks AS confirmed_started_ticks, "
            "p.command_sha256 AS confirmed_command_sha256, "
            "p.confirmed_at_ns AS confirmed_at_ns "
            "FROM owner_intents i LEFT JOIN owner_processes p "
            "ON p.spawn_token = i.spawn_token "
            "WHERE i.campaign_id=? AND i.batch_id=?"
        )
        parameters: list[object] = [campaign_id, batch_id]
        if generation is not None:
            query += " AND i.generation=?"
            parameters.append(generation)
        query += " ORDER BY i.created_at_ns, i.spawn_token"
        records = []
        for row in self._connection.execute(query, tuple(parameters)):
            intent = _owner_intent_from_row(row)
            if row["confirmed_pid"] is None:
                records.append(OwnerRecord(intent=intent, confirmed=None))
                continue
            records.append(
                OwnerRecord(
                    intent=intent,
                    confirmed=ConfirmedOwnerProcess(
                        spawn_token=intent.spawn_token,
                        pid=row["confirmed_pid"],
                        pgid=row["confirmed_pgid"],
                        started_ticks=row["confirmed_started_ticks"],
                        command_sha256=row["confirmed_command_sha256"],
                        confirmed_at_ns=row["confirmed_at_ns"],
                    ),
                )
            )
        return tuple(records)

    def owner_cleanup_receipt(
        self, campaign_id: str, batch_id: str, generation: int
    ) -> dict | None:
        row = self._connection.execute(
            "SELECT receipt_json, receipt_sha256 FROM owner_cleanup_receipts "
            "WHERE campaign_id=? AND batch_id=? AND generation=?",
            (campaign_id, batch_id, generation),
        ).fetchone()
        return None if row is None else dict(json.loads(row["receipt_json"]))

    def record_owner_cleanup_receipt(self, receipt) -> None:
        """Index a fsynced leaf-first cleanup receipt. A generation is committed once."""
        document = receipt.as_document()
        with self._transaction():
            try:
                self._connection.execute(
                    "INSERT INTO owner_cleanup_receipts VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        receipt.campaign_id,
                        receipt.batch_id,
                        receipt.generation,
                        receipt.receipt_sha256,
                        json.dumps(document, sort_keys=True, separators=(",", ":")),
                        time.time_ns(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise StoreConflict("OWNER_RECEIPT_CONFLICT") from error

    def _validate_fixed_binding(self, binding: CoordinatorBinding) -> None:
        batch = self.batch(binding.batch_id)
        if (
            batch is None or batch.campaign_id != binding.campaign_id
            or batch.journal_root != binding.batch_root
            or batch.coordinator_epoch != binding.coordinator_epoch
        ):
            raise StoreConflict("FIXED_CONTROL_BATCH_BINDING_MISMATCH")

    def fixed_control_binding(self, batch_id: str) -> CoordinatorBinding | None:
        row = self._connection.execute(
            "SELECT * FROM fixed_control_bindings WHERE batch_id=?", (batch_id,)
        ).fetchone()
        if row is None:
            return None
        binding = CoordinatorBinding(
            row["campaign_id"], row["batch_id"], Path(row["batch_root"]),
            Path(row["control_socket"]), row["coordinator_epoch"],
            row["control_token"], row["control_token_sha256"],
        )
        self._validate_fixed_binding(binding)
        return binding

    def record_recovery_fence(
        self,
        campaign_id: str,
        batch_id: str,
        *,
        reason: str,
        command_id: str,
        generation: int | None = None,
    ) -> None:
        """Record one campaign-scoped fence, optionally for an exact owner-tree generation.

        The row is campaign-scoped and its reason already names the generation the reaper
        concluded, so ``generation`` is validated for interface parity with the directory sink and
        deliberately not stored; every caller that predates it is unchanged.
        """
        if generation is not None and (
            type(generation) is not int or isinstance(generation, bool) or generation < 1
        ):
            raise StoreConflict("RECOVERY_FENCE_GENERATION_INVALID")
        with self._transaction():
            batch = self.batch(batch_id)
            if batch is None or batch.campaign_id != campaign_id:
                raise StoreConflict("RECOVERY_FENCE_BATCH_MISMATCH")
            self._connection.execute(
                "INSERT OR IGNORE INTO recovery_fences VALUES (?, ?, ?, ?, ?)",
                (campaign_id, batch_id, reason, command_id, time.time_ns()),
            )

    def recovery_fence(self, campaign_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM recovery_fences WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def has_recovery_fence(self) -> bool:
        for row in self._connection.execute("SELECT campaign_id FROM recovery_fences"):
            try:
                if self.operator_recovery(row["campaign_id"]) is None:
                    return True
            except StoreConflict:
                return True
        return False

    def operator_recovery_context(self, campaign_id: str) -> dict:
        """Return historical binding facts, never control credentials or success claims."""
        campaign = self._connection.execute(
            "SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        fence = self.recovery_fence(campaign_id)
        if campaign is None or fence is None:
            raise StoreConflict("RECOVERY_FENCE_NOT_FOUND")
        batches = [dict(row) for row in self._connection.execute(
            "SELECT * FROM campaign_batches WHERE campaign_id=? ORDER BY batch_id", (campaign_id,)
        )]
        owners = [dict(row) for row in self._connection.execute(
            "SELECT o.* FROM owned_execution o JOIN campaign_batches b USING(batch_id) "
            "WHERE b.campaign_id=? ORDER BY o.batch_id", (campaign_id,)
        )]
        receipt = self._connection.execute(
            "SELECT receipt_json,receipt_sha256 FROM preflight_receipts WHERE receipt_id=?",
            (campaign["preflight_receipt_id"],),
        ).fetchone()
        if receipt is None:
            raise StoreConflict("RECOVERY_PREFLIGHT_NOT_FOUND")
        document = json.loads(receipt["receipt_json"])
        if _sha(document) != receipt["receipt_sha256"]:
            raise StoreConflict("RECOVERY_PREFLIGHT_INVALID")
        binding = {"campaign": dict(campaign), "batches": batches, "owners": owners,
                   "preflight_receipt_sha256": receipt["receipt_sha256"]}
        return {**binding, "fence": fence, "fence_sha256": _sha(fence),
                "binding_sha256": _sha(binding), "preflight": document}

    def _check_operator_receipt(self, campaign_id: str, receipt: dict) -> None:
        context = self.operator_recovery_context(campaign_id)
        if (
            receipt.get("campaign_id") != campaign_id
            or receipt.get("fence_sha256") != context["fence_sha256"]
            or receipt.get("binding_sha256") != context["binding_sha256"]
            or receipt.get("status") != "OPERATOR_RECOVERED_ABORTED"
            or receipt.get("execution_success") is not False
            or receipt.get("upstream_cleanup_claimed") is not False
        ):
            raise StoreConflict("RECOVERY_RECEIPT_INVALID")
        for prefix in ("report", "backup", "config"):
            path = Path(receipt[f"{prefix}_path"])
            if (
                not path.is_absolute() or path != path.resolve(strict=True)
                or not path.is_relative_to(self.root / "operator-recovery")
            ):
                raise StoreConflict("RECOVERY_EVIDENCE_INVALID")
            metadata = path.stat(follow_symlinks=False)
            if (
                not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) != 0o600
                or hashlib.sha256(path.read_bytes()).hexdigest() != receipt[f"{prefix}_sha256"]
            ):
                raise StoreConflict("RECOVERY_EVIDENCE_INVALID")
        report = json.loads(Path(receipt["report_path"]).read_bytes())
        for key in ("campaign_id", "command_id", "fence_sha256", "binding_sha256"):
            if report.get(key) != receipt.get(key):
                raise StoreConflict("RECOVERY_REPORT_INVALID")
        if receipt["config_sha256"] != context["preflight"].get("parallel_config_sha256"):
            raise StoreConflict("RECOVERY_CONFIG_MISMATCH")

    def operator_recovery(self, campaign_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM operator_recoveries WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            receipt = json.loads(row["receipt_json"])
            if _sha(receipt) != row["receipt_sha256"] or receipt.get("command_id") != row["command_id"]:
                raise StoreConflict("RECOVERY_RECEIPT_INVALID")
            self._check_operator_receipt(campaign_id, receipt)
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise StoreConflict("RECOVERY_RECEIPT_INVALID") from error
        return receipt

    def record_operator_recovery(self, receipt: dict) -> dict:
        """Commit only an audited abort resolution; original fence/history stays intact."""
        campaign_id = receipt["campaign_id"]
        request = {key: receipt[key] for key in (
            "campaign_id", "command_id", "fence_sha256", "binding_sha256", "config_sha256",
        )}
        digest = _sha(request)
        with self._transaction():
            self._check_operator_receipt(campaign_id, receipt)
            if self._connection.execute(
                "SELECT 1 FROM commands WHERE command_id=?", (receipt["command_id"],)
            ).fetchone() is not None:
                raise StoreConflict("COMMAND_ID_REUSED")
            if self.operator_recovery(campaign_id) is not None:
                raise StoreConflict("RECOVERY_ALREADY_RESOLVED")
            self._connection.execute("INSERT INTO operator_recoveries VALUES (?, ?, ?, ?)",
                                     (campaign_id, receipt["command_id"], _json(receipt), _sha(receipt)))
            self._connection.execute("INSERT INTO commands VALUES (?, ?, ?, ?, ?)",
                                     (receipt["command_id"], digest, "OPERATOR_RECOVERY", "COMPLETE", _json(receipt)))
        return receipt

    def acknowledge_execution_owner(self, owned=None, **values) -> None:
        if owned is not None:
            values = {
                "batch_id": owned.batch_id,
                "pid": owned.pid,
                "pgid": owned.pgid,
                "started_ticks": owned.started_ticks,
                "coordinator_epoch": getattr(owned, "coordinator_epoch", None),
                "runner_pid": getattr(owned, "runner_pid", None),
                "runner_journal_root": getattr(owned, "runner_journal_root", None),
                "argv_sha256": owned.argv_sha256,
                "environment_sha256": owned.environment_sha256,
            }
        batch_id = values["batch_id"]
        with self._transaction():
            row = self._connection.execute(
                "SELECT * FROM owned_execution WHERE batch_id = ?", (batch_id,)
            ).fetchone()
            if row is None or row["state"] != "INTENT":
                raise StoreConflict("EXECUTION_OWNER_INTENT_MISSING")
            binding = self.fixed_control_binding(batch_id)
            if binding is not None and (
                values.get("coordinator_epoch") != binding.coordinator_epoch
                or type(values.get("coordinator_epoch")) is not int
            ):
                raise StoreConflict("FIXED_CONTROL_OWNER_ACK_MISMATCH")
            for name in ("argv_sha256", "environment_sha256"):
                if values.get(name) is not None and values[name] != row[name]:
                    raise StoreConflict("EXECUTION_OWNER_FINGERPRINT_MISMATCH")
            self._connection.execute(
                "UPDATE owned_execution SET state='RUNNING', pid=?, pgid=?, started_ticks=?, "
                "coordinator_epoch=?, runner_pid=?, runner_journal_root=?, acknowledged_at_ns=? "
                "WHERE batch_id=?",
                (
                    values["pid"],
                    values["pgid"],
                    values["started_ticks"],
                    values.get("coordinator_epoch"),
                    values.get("runner_pid"),
                    str(values.get("runner_journal_root"))
                    if values.get("runner_journal_root") is not None
                    else None,
                    time.time_ns(),
                    batch_id,
                ),
            )

    def owned_execution(self, batch_id: str) -> OwnedExecutionRecord | None:
        row = self._connection.execute(
            "SELECT * FROM owned_execution WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if row is None:
            return None
        return OwnedExecutionRecord(
            batch_id=row["batch_id"],
            owner_kind=row["owner_kind"],
            state=row["state"],
            spawn_token=row["spawn_token"],
            expected_executable=row["expected_executable"],
            argv_sha256=row["argv_sha256"],
            environment_sha256=row["environment_sha256"],
            source_commit=row["source_commit"],
            install_prefix=Path(row["install_prefix"]),
            runtime_sha256=row["runtime_sha256"],
            pid=row["pid"],
            pgid=row["pgid"],
            started_ticks=row["started_ticks"],
            control_socket=Path(row["control_socket"]) if row["control_socket"] else None,
            coordinator_epoch=row["coordinator_epoch"],
            runner_pid=row["runner_pid"],
            runner_journal_root=Path(row["runner_journal_root"])
            if row["runner_journal_root"]
            else None,
            acknowledged_at_ns=row["acknowledged_at_ns"],
        )


    owned_coordinator = owned_execution
    def owned_executions(self, states: tuple[str, ...]) -> tuple[OwnedExecutionRecord, ...]:
        marks = ",".join("?" for _ in states)
        return tuple(
            self.owned_execution(row["batch_id"])
            for row in self._connection.execute(
                f"SELECT batch_id FROM owned_execution WHERE state IN ({marks}) ORDER BY batch_id",
                states,
            )
        )
