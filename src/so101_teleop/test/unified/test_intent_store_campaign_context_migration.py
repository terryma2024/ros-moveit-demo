"""The unified store moves from schema 2 to 3 in place: `act_campaign_contexts` loses the UNIQUE on `campaign_id`.

Every store here is a fixture built in a temporary directory; no registered store is ever opened.
"""

import sqlite3

import pytest

from so101_teleop.unified import intent_store
from so101_teleop.unified.contracts import IDLE
from so101_teleop.unified.intent_store import DATABASE_FILE_NAME, IntentStore

VERSION_TWO_CONTEXTS = """
CREATE TABLE act_campaign_contexts (
  operation_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL UNIQUE,
  context_json TEXT NOT NULL
);
"""
ROWS = (("op-a", "campaign-a", '{"k":1}'), ("op-b", "campaign-b", '{"k":2}'))


def make_version_two_store(root, *, rows=ROWS):
    root.mkdir(mode=0o700)
    connection = sqlite3.connect(root / DATABASE_FILE_NAME, isolation_level=None)
    connection.executescript(intent_store._SCHEMA)
    connection.executescript("DROP TABLE act_campaign_contexts;" + VERSION_TWO_CONTEXTS)
    connection.execute("INSERT INTO schema_meta VALUES ('schema_version', '2')")
    connection.execute("INSERT INTO global_state (singleton, state, updated_ns) VALUES (1, ?, 0)", (IDLE,))
    for row in rows:
        connection.execute("INSERT INTO act_campaign_contexts VALUES (?,?,?)", row)
    connection.close()


def version(store):
    return store._query_one("SELECT value FROM schema_meta WHERE key='schema_version'")["value"]


def test_a_version_two_store_migrates_keeping_every_context_row_readable(tmp_path):
    make_version_two_store(tmp_path / "state")
    store = IntentStore.open(tmp_path / "state")
    try:
        assert version(store) == "3"
        rows = store._query_all("SELECT operation_id, campaign_id, context_json FROM act_campaign_contexts ORDER BY 1")
        assert [tuple(row) for row in rows] == list(ROWS)
        assert "UNIQUE" not in store._query_one("SELECT sql FROM sqlite_master WHERE name='act_campaign_contexts'")["sql"]
        names = {row["name"] for row in store._query_all("SELECT name FROM sqlite_master")}
        assert "act_campaign_contexts_next" not in names
    finally:
        store.close()


def test_after_the_migration_one_campaign_id_may_hold_several_contexts_but_an_operation_only_one(tmp_path):
    make_version_two_store(tmp_path / "state")
    store = IntentStore.open(tmp_path / "state")
    try:
        store._connection.execute("INSERT INTO act_campaign_contexts VALUES ('op-c', 'campaign-a', '{}')")
        assert store._query_one("SELECT COUNT(*) FROM act_campaign_contexts WHERE campaign_id='campaign-a'")[0] == 2
        with pytest.raises(sqlite3.IntegrityError):
            store._connection.execute("INSERT INTO act_campaign_contexts VALUES ('op-c', 'campaign-z', '{}')")
    finally:
        store.close()


def test_migrating_twice_and_reopening_a_current_store_change_nothing(tmp_path):
    make_version_two_store(tmp_path / "state")
    IntentStore.open(tmp_path / "state").close()
    store = IntentStore.open(tmp_path / "state")
    try:
        assert version(store) == "3"
        assert store._query_one("SELECT COUNT(*) FROM act_campaign_contexts")[0] == 2
    finally:
        store.close()


def test_a_version_two_store_with_no_context_rows_migrates(tmp_path):
    make_version_two_store(tmp_path / "state", rows=())
    store = IntentStore.open(tmp_path / "state")
    try:
        assert version(store) == "3"
        assert store._query_one("SELECT COUNT(*) FROM act_campaign_contexts")[0] == 0
    finally:
        store.close()


def test_a_fresh_store_has_no_unique_on_the_campaign_id(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    try:
        assert "UNIQUE" not in store._query_one("SELECT sql FROM sqlite_master WHERE name='act_campaign_contexts'")["sql"]
    finally:
        store.close()
