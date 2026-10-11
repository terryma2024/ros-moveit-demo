"""Lease generations, lease rows and the reconcile and table listing."""

from __future__ import annotations

from so101_teleop.expert_validation.supervisor_store.schema import StoreConflict


class StoreLeases:
    def invalidate_active_leases(self) -> int:
        with self._transaction():
            cursor = self._connection.execute(
                "UPDATE leases SET state='RESTART_INVALIDATED' WHERE state='ACTIVE'"
            )
            return cursor.rowcount

    def next_lease_generation(self) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(generation), 0) + 1 FROM leases"
        ).fetchone()
        return int(row[0])

    def insert_lease(
        self, lease_id: str, service_session_id: str, generation: int, expires_ns: int
    ) -> None:
        with self._transaction():
            active = self._connection.execute(
                "SELECT lease_id FROM leases WHERE state='ACTIVE'"
            ).fetchone()
            if active is not None:
                raise StoreConflict("LEASE_ALREADY_HELD")
            self._connection.execute(
                "INSERT INTO leases VALUES (?, ?, ?, ?, 'ACTIVE')",
                (lease_id, service_session_id, generation, expires_ns),
            )

    def current_lease(self):
        return self._connection.execute(
            "SELECT * FROM leases WHERE state='ACTIVE' ORDER BY generation DESC LIMIT 1"
        ).fetchone()

    def renew_lease(
        self,
        lease_id: str,
        service_session_id: str,
        generation: int,
        new_generation: int,
        expires_ns: int,
    ) -> None:
        with self._transaction():
            cursor = self._connection.execute(
                "UPDATE leases SET generation=?, expires_monotonic_ns=? "
                "WHERE lease_id=? AND service_session_id=? AND generation=? AND state='ACTIVE'",
                (new_generation, expires_ns, lease_id, service_session_id, generation),
            )
            if cursor.rowcount != 1:
                raise StoreConflict("STALE_LEASE_GENERATION")

    def set_lease_state(
        self, lease_id: str, generation: int, state: str
    ) -> None:
        with self._transaction():
            cursor = self._connection.execute(
                "UPDATE leases SET state=? WHERE lease_id=? AND generation=? AND state='ACTIVE'",
                (state, lease_id, generation),
            )
            if cursor.rowcount != 1:
                raise StoreConflict("LEASE_NOT_ACTIVE")

    def reconcile(self) -> dict:
        ambiguous = tuple(
            row[0] for row in self._connection.execute(
                "SELECT command_id FROM commands WHERE state='IN_PROGRESS' ORDER BY command_id"
            )
        )
        intents = tuple(
            row[0] for row in self._connection.execute(
                "SELECT batch_id FROM owned_execution WHERE state='INTENT' ORDER BY batch_id"
            )
        )
        return {"ambiguous_commands": ambiguous, "unacknowledged_owner_intents": intents}

    def table_names(self) -> set[str]:
        return {
            row[0]
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
