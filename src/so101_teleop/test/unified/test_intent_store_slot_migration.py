"""The unified store moves from schema 1 to 2 in place, or refuses and changes nothing.

Every store here is a fixture built in a temporary directory; no registered store is ever opened.
"""

import json
import sqlite3

import pytest

from so101_teleop.unified import intent_store
from so101_teleop.unified.contracts import BLOCKED, IDLE, MutationError
from so101_teleop.unified.intent_store import DATABASE_FILE_NAME, IntentStore
from so101_teleop.unified.worker_slots import ActWorkerSlot, ActWorkerSlotRegistry

PER_SLOT_RESOURCE_TABLE = """
CREATE TABLE act_worker_slots (
  campaign_id TEXT NOT NULL,
  worker_id TEXT NOT NULL,
  execution_generation INTEGER NOT NULL,
  ros_domain_id INTEGER NOT NULL,
  namespace TEXT NOT NULL,
  controller_name TEXT NOT NULL,
  slot_json TEXT NOT NULL,
  active INTEGER NOT NULL CHECK (active IN (0,1)),
  PRIMARY KEY (campaign_id, worker_id, execution_generation)
);
CREATE UNIQUE INDEX act_active_slot_domain ON act_worker_slots(ros_domain_id) WHERE active=1;
CREATE UNIQUE INDEX act_active_slot_namespace ON act_worker_slots(namespace) WHERE active=1;
CREATE UNIQUE INDEX act_active_slot_controller ON act_worker_slots(controller_name) WHERE active=1;
"""
PER_SLOT_RESOURCE_ROWS = (
    ("campaign-a", "w00", 3, 181, "/act/campaign_a/w00", "/act/campaign_a/w00/arm_controller", 0),
    ("campaign-a", "w01", 3, 182, "/act/campaign_a/w01", "/act/campaign_a/w01/arm_controller", 0),
)


def slot_json(row):
    campaign, worker, generation, domain, namespace, controller, _active = row
    return json.dumps(dict(campaign_id=campaign, worker_id=worker, execution_generation=generation,
                           ros_domain_id=domain, namespace=namespace, controller_name=controller),
                      sort_keys=True, separators=(",", ":"))


def make_per_slot_resource_store(root, *, rows=PER_SLOT_RESOURCE_ROWS, state=IDLE, lease=False):
    """A schema 1 database: the current tables with the v1 slot table, its three indexes and `schema_version` 1."""
    root.mkdir(mode=0o700)
    connection = sqlite3.connect(root / DATABASE_FILE_NAME, isolation_level=None)
    connection.executescript(intent_store._SCHEMA)
    connection.executescript("DROP TABLE act_worker_slots;" + PER_SLOT_RESOURCE_TABLE)
    connection.execute("INSERT INTO schema_meta VALUES ('schema_version', '1')")
    connection.execute("INSERT INTO global_state (singleton, state, updated_ns) VALUES (1, ?, 0)", (state,))
    for row in rows:
        connection.execute("INSERT INTO act_worker_slots VALUES (?,?,?,?,?,?,?,?)",
                           (*row[:6], slot_json(row), row[6]))
    if lease:
        connection.execute("INSERT INTO gpu_workload_leases VALUES ('host','GPU-x','op','epoch',1,1,'act',1,1)")
    connection.close()
    return root / DATABASE_FILE_NAME


def snapshot(path):
    connection = sqlite3.connect(path)
    try:
        return (connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone(),
                connection.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall(),
                connection.execute("SELECT * FROM act_worker_slots ORDER BY 1,2,3").fetchall())
    finally:
        connection.close()


def test_a_fresh_store_is_schema_two_with_the_five_column_slot_table(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    try:
        assert store._query_one("SELECT value FROM schema_meta WHERE key='schema_version'")["value"] == "2"
        assert [row["name"] for row in store._query_all("PRAGMA table_info(act_worker_slots)")] == [
            "campaign_id", "worker_id", "execution_generation", "slot_json", "active"]
        names = {row["name"] for row in store._query_all("SELECT name FROM sqlite_master")}
        assert "act_worker_slots_v1" not in names and not {n for n in names if n.startswith("act_active_slot")}
    finally:
        store.close()


def test_an_idle_store_with_only_inactive_per_slot_rows_migrates_in_place_keeping_the_old_rows(tmp_path):
    path = make_per_slot_resource_store(tmp_path / "state")
    store = IntentStore.open(tmp_path / "state")
    try:
        assert store._query_one("SELECT value FROM schema_meta WHERE key='schema_version'")["value"] == "2"
        assert [row["name"] for row in store._query_all("PRAGMA table_info(act_worker_slots)")] == [
            "campaign_id", "worker_id", "execution_generation", "slot_json", "active"]
        assert store._query_all("SELECT * FROM act_worker_slots") == []
        old = store._query_all("SELECT * FROM act_worker_slots_v1 ORDER BY worker_id")
        assert [tuple(row)[:6] for row in old] == [row[:6] for row in PER_SLOT_RESOURCE_ROWS]
        assert [row["slot_json"] for row in old] == [slot_json(row) for row in PER_SLOT_RESOURCE_ROWS]
        assert [row["name"] for row in store._query_all(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'act_active_slot_%'")] == []
        # the rest of the store is untouched and usable: two slots of one campaign are now active together
        assert store.global_state() == (IDLE, None)
        registry = ActWorkerSlotRegistry(store)
        slots = tuple(ActWorkerSlot("campaign-b", f"w0{index}", 4) for index in range(2))
        with registry.reserve_many(slots):
            assert registry.slots() == slots
    finally:
        store.close()
    reopened = IntentStore.open(tmp_path / "state")      # idempotent: nothing is migrated twice
    try:
        assert len(reopened._query_all("SELECT * FROM act_worker_slots_v1")) == len(PER_SLOT_RESOURCE_ROWS)
    finally:
        reopened.close()
    assert path.is_file()


@pytest.mark.parametrize("problem", ["active_slot", "not_idle", "gpu_lease"])
def test_a_store_with_per_slot_resources_that_is_not_quiescent_is_refused_and_left_byte_for_byte_alone(tmp_path, problem):
    rows = PER_SLOT_RESOURCE_ROWS + (("campaign-a", "w02", 3, 183, "/act/campaign_a/w02", "/act/campaign_a/w02/arm_controller", 1),) \
        if problem == "active_slot" else PER_SLOT_RESOURCE_ROWS
    path = make_per_slot_resource_store(tmp_path / "state", rows=rows, state=BLOCKED if problem == "not_idle" else IDLE,
                         lease=problem == "gpu_lease")
    before = snapshot(path)

    with pytest.raises(MutationError, match="^STORE_MIGRATION_REFUSED"):
        IntentStore.open(tmp_path / "state")

    assert snapshot(path) == before and before[0] == ("1",)
    assert any("act_active_slot_domain" in (sql or "") for (sql,) in before[1])
    with pytest.raises(MutationError, match="^STORE_MIGRATION_REFUSED"):       # the lock was released: not 'LOCKED'
        IntentStore.open(tmp_path / "state")


def test_a_failure_in_the_middle_of_the_migration_rolls_everything_back(tmp_path):
    path = make_per_slot_resource_store(tmp_path / "state")
    connection = sqlite3.connect(path, isolation_level=None)
    connection.execute("CREATE TABLE act_worker_slots_v1 (squatter INTEGER)")    # the rename target is taken
    connection.close()
    before = snapshot(path)

    with pytest.raises(sqlite3.Error):
        IntentStore.open(tmp_path / "state")

    assert snapshot(path) == before and before[0] == ("1",)
    assert sum("act_active_slot_" in (sql or "") for (sql,) in before[1]) == 3     # the dropped indexes came back


def test_an_unknown_future_version_is_refused(tmp_path):
    path = make_per_slot_resource_store(tmp_path / "state")
    connection = sqlite3.connect(path, isolation_level=None)
    connection.execute("UPDATE schema_meta SET value='3' WHERE key='schema_version'")
    connection.close()

    with pytest.raises(MutationError, match="^STORE_SCHEMA_UNSUPPORTED"):
        IntentStore.open(tmp_path / "state")
