"""Store records, the table schema and the owner intent row reader."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from so101_teleop.expert_validation.owner_tree import (
    OwnerIntent,
)


@dataclass(frozen=True)
class ProjectionSnapshot:
    """The durable reducer state and accepted cursor of one batch."""

    state: object | None
    cursor: object | None


class StoreConflict(RuntimeError):
    """A durable identity or transaction invariant was violated."""


class CommandOutcomeUnknown(RuntimeError):
    """A command began durably but has no committed result."""


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS commands (
  command_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, operation TEXT NOT NULL,
  state TEXT NOT NULL, result_json TEXT
);
CREATE TABLE IF NOT EXISTS manifests (
  manifest_id TEXT PRIMARY KEY, canonical_json TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
  source_config_sha256 TEXT NOT NULL, created_at_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS preflight_receipts (
  receipt_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL UNIQUE,
  manifest_id TEXT NOT NULL REFERENCES manifests(manifest_id),
  canonical_start_request_sha256 TEXT NOT NULL, receipt_json TEXT NOT NULL,
  receipt_sha256 TEXT NOT NULL, expires_at_monotonic_ns INTEGER NOT NULL, consumed_at_ns INTEGER
);
CREATE TABLE IF NOT EXISTS campaigns (
  campaign_id TEXT PRIMARY KEY, state TEXT NOT NULL,
  manifest_id TEXT NOT NULL REFERENCES manifests(manifest_id), executor_id TEXT NOT NULL,
  operation_id TEXT NOT NULL, executor_config_sha256 TEXT NOT NULL,
  execution_mode TEXT NOT NULL CHECK (execution_mode IN ('SEQUENTIAL','PARALLEL','ADAPTIVE')),
  execution_config_json TEXT NOT NULL, execution_config_sha256 TEXT NOT NULL,
  preflight_receipt_id TEXT NOT NULL UNIQUE REFERENCES preflight_receipts(receipt_id)
);
CREATE TABLE IF NOT EXISTS campaign_batches (
  batch_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
  batch_kind TEXT NOT NULL CHECK (batch_kind IN ('FIRST_PASS','FULL_RESTART_RETRY')),
  point_id TEXT, state TEXT NOT NULL, coordinator_epoch INTEGER, pool_generation INTEGER,
  journal_root TEXT NOT NULL, terminal_summary_sha256 TEXT, cleanup_receipt_sha256 TEXT
);
CREATE TABLE IF NOT EXISTS upstream_cursors (
  batch_id TEXT PRIMARY KEY REFERENCES campaign_batches(batch_id),
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('COORDINATOR','ADAPTIVE_RUNNER')),
  owner_epoch_or_generation INTEGER NOT NULL, segment_id TEXT NOT NULL, event_id TEXT NOT NULL,
  frame_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projection_state (
  batch_id TEXT PRIMARY KEY REFERENCES campaign_batches(batch_id),
  state_json TEXT NOT NULL,
  owner_epoch_or_generation INTEGER NOT NULL, segment_id TEXT NOT NULL,
  event_id TEXT NOT NULL, frame_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projection_events (
  batch_id TEXT NOT NULL REFERENCES campaign_batches(batch_id),
  sequence INTEGER NOT NULL, frame_sha256 TEXT NOT NULL, attempt_id TEXT,
  PRIMARY KEY (batch_id, sequence, frame_sha256)
);
CREATE TABLE IF NOT EXISTS projection_attempts (
  batch_id TEXT NOT NULL REFERENCES campaign_batches(batch_id),
  attempt_id TEXT NOT NULL, point_id TEXT,
  PRIMARY KEY (batch_id, attempt_id)
);
CREATE TABLE IF NOT EXISTS owned_execution (
  batch_id TEXT PRIMARY KEY REFERENCES campaign_batches(batch_id),
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('COORDINATOR','ADAPTIVE_WRAPPER')),
  state TEXT NOT NULL, spawn_token TEXT NOT NULL UNIQUE, expected_executable TEXT NOT NULL,
  argv_sha256 TEXT NOT NULL, environment_sha256 TEXT NOT NULL, source_commit TEXT NOT NULL,
  install_prefix TEXT NOT NULL, runtime_sha256 TEXT NOT NULL, pid INTEGER, pgid INTEGER,
  started_ticks INTEGER, control_socket TEXT, coordinator_epoch INTEGER, runner_pid INTEGER,
  runner_journal_root TEXT, acknowledged_at_ns INTEGER
);
CREATE TABLE IF NOT EXISTS adaptive_projection_cache (
  batch_id TEXT PRIMARY KEY REFERENCES campaign_batches(batch_id), current_generation INTEGER,
  current_level INTEGER, fallback_history_json TEXT NOT NULL, resource_observations_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS retry_queue (
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id), ordinal INTEGER NOT NULL,
  point_id TEXT NOT NULL, state TEXT NOT NULL, batch_id TEXT REFERENCES campaign_batches(batch_id),
  cleanup_receipt_sha256 TEXT, PRIMARY KEY (campaign_id, ordinal)
);
CREATE TABLE IF NOT EXISTS leases (
  lease_id TEXT PRIMARY KEY, service_session_id TEXT NOT NULL, generation INTEGER NOT NULL,
  expires_monotonic_ns INTEGER NOT NULL, state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fixed_control_bindings (
  batch_id TEXT PRIMARY KEY REFERENCES owned_execution(batch_id),
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id), batch_root TEXT NOT NULL,
  control_socket TEXT NOT NULL, coordinator_epoch INTEGER NOT NULL,
  control_token TEXT NOT NULL, control_token_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recovery_fences (
  campaign_id TEXT PRIMARY KEY REFERENCES campaigns(campaign_id),
  batch_id TEXT NOT NULL REFERENCES campaign_batches(batch_id),
  reason TEXT NOT NULL, command_id TEXT NOT NULL, created_at_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS owner_intents (
  spawn_token TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  batch_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('ADAPTER','CAMPAIGN','BROKER','WORKER','STATION')),
  generation INTEGER NOT NULL,
  parent_spawn_token TEXT,
  expected_executable TEXT NOT NULL,
  argv_sha256 TEXT NOT NULL,
  own_session INTEGER NOT NULL,
  created_at_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS owner_processes (
  spawn_token TEXT PRIMARY KEY REFERENCES owner_intents(spawn_token),
  pid INTEGER NOT NULL, pgid INTEGER NOT NULL, started_ticks INTEGER NOT NULL,
  command_sha256 TEXT NOT NULL, confirmed_at_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS owner_cleanup_receipts (
  campaign_id TEXT NOT NULL, batch_id TEXT NOT NULL, generation INTEGER NOT NULL,
  receipt_sha256 TEXT NOT NULL, receipt_json TEXT NOT NULL, recorded_at_ns INTEGER NOT NULL,
  PRIMARY KEY (campaign_id, batch_id, generation)
);
CREATE TABLE IF NOT EXISTS operator_recoveries (
  campaign_id TEXT PRIMARY KEY REFERENCES recovery_fences(campaign_id),
  command_id TEXT NOT NULL UNIQUE,
  receipt_json TEXT NOT NULL, receipt_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS retry_admissions (
  command_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
  context_kind TEXT NOT NULL CHECK (context_kind IN ('CANDIDATE','PRODUCTION')),
  context_id TEXT NOT NULL, context_scope TEXT NOT NULL,
  batch_id TEXT NOT NULL UNIQUE REFERENCES campaign_batches(batch_id),
  point_id TEXT NOT NULL,
  original_batch_id TEXT NOT NULL REFERENCES campaign_batches(batch_id),
  original_result_sha256 TEXT NOT NULL,
  execution_profile TEXT NOT NULL, schema_version INTEGER NOT NULL,
  config_sha256 TEXT NOT NULL, runtime_closure_sha256 TEXT NOT NULL,
  worker_count INTEGER NOT NULL, evidence_root TEXT NOT NULL,
  lease_id TEXT, lease_generation INTEGER, owner_generation INTEGER NOT NULL,
  max_runs INTEGER, spawn_token TEXT NOT NULL,
  binding_json TEXT NOT NULL, binding_sha256 TEXT NOT NULL, created_at_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS first_pass_admissions (
  command_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
  context_kind TEXT NOT NULL CHECK (context_kind IN ('CANDIDATE')),
  context_id TEXT NOT NULL, context_scope TEXT NOT NULL,
  batch_id TEXT NOT NULL UNIQUE REFERENCES campaign_batches(batch_id),
  manifest_id TEXT NOT NULL,
  execution_profile TEXT NOT NULL, schema_version INTEGER NOT NULL,
  config_sha256 TEXT NOT NULL, runtime_closure_sha256 TEXT NOT NULL,
  worker_count INTEGER NOT NULL, evidence_root TEXT NOT NULL,
  owner_generation INTEGER NOT NULL, max_runs INTEGER,
  spawn_token TEXT NOT NULL,
  binding_json TEXT NOT NULL, binding_sha256 TEXT NOT NULL, created_at_ns INTEGER NOT NULL
);
"""


def _owner_intent_from_row(row) -> OwnerIntent:
    return OwnerIntent(
        campaign_id=row["campaign_id"],
        batch_id=row["batch_id"],
        role=row["role"],
        generation=row["generation"],
        spawn_token=row["spawn_token"],
        parent_spawn_token=row["parent_spawn_token"],
        expected_executable=row["expected_executable"],
        argv_sha256=row["argv_sha256"],
        own_session=bool(row["own_session"]),
        created_at_ns=row["created_at_ns"],
    )
