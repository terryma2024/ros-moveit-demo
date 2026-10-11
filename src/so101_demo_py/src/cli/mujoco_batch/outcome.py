"""Outcome documents of a finished batch and the broker readiness check."""

from __future__ import annotations

from so101_demo.cli.mujoco_batch.common import CliError
from so101_demo.parallel_batch.adaptive_contracts import (
    AdaptiveBatchSummary,
    BatchTerminalStatus,
)
from so101_demo.parallel_batch.contracts import (
    BatchSummary,
    RunMode,
)


def outcome_document(summary: BatchSummary) -> tuple[int, dict[str, object]]:
    if not isinstance(summary, BatchSummary):
        raise CliError("BATCH_SUMMARY_REQUIRED")
    document = {
        "schema_version": 1,
        "run_mode": summary.run_mode.value,
        "batch_terminal": summary.batch_terminal,
        "batch_cleanup_complete": summary.batch_cleanup_complete,
        "point_statuses": {key: value.value for key, value in summary.point_statuses.items()},
        "validation_statuses": {
            key: value.value for key, value in summary.validation_statuses.items()
        },
        "validation_complete": summary.validation_complete,
        "validation_passed": summary.validation_passed,
        "qualification_applicable": summary.qualification_applicable,
        "qualification_passed": summary.qualification_passed,
        # The Teacher success rate counts every started, legal Teacher attempt. The data side is reported apart from
        # it: how many committed results passed the independent QC and how many episodes may be exported.
        "teacher_attempts_started": summary.teacher_attempts_started,
        "teacher_passed": summary.teacher_passed,
        "teacher_success_rate": summary.teacher_success_rate,
        "act_data_qc_passed": summary.act_data_qc_passed,
        "act_data_pass_rate": summary.act_data_pass_rate,
        "committable_episodes": summary.committable_episodes,
    }
    if summary.run_mode is RunMode.EXECUTE:
        passed = summary.qualification_passed
    else:
        passed = summary.validation_passed and summary.batch_cleanup_complete
    return (0 if passed else 1), document


def adaptive_outcome_document(
    summary: AdaptiveBatchSummary, *, elapsed_s: float
) -> tuple[int, dict[str, object]]:
    """Return the stable top-level projection for an adaptive batch."""

    if not isinstance(summary, AdaptiveBatchSummary):
        raise CliError("ADAPTIVE_BATCH_SUMMARY_REQUIRED")
    if (
        isinstance(elapsed_s, bool)
        or not isinstance(elapsed_s, (int, float))
        or not 0.0 <= float(elapsed_s) < float("inf")
    ):
        raise CliError("ADAPTIVE_ELAPSED_INVALID")
    document = {
        "schema_version": 1,
        "mode": "adaptive_workers",
        "status": summary.status.value,
        "initial_worker_count": summary.initial_worker_count,
        "final_worker_count": summary.final_worker_count,
        "levels_used": list(summary.levels_used),
        "fallback_transitions": [
            {
                "generation": transition.generation,
                "from_count": transition.from_count,
                "to_count": transition.to_count,
                "failure": {
                    "kind": transition.failure.kind.value,
                    "generation": transition.failure.generation,
                    "worker_count": transition.failure.worker_count,
                    "detail": transition.failure.detail,
                },
            }
            for transition in summary.transitions
        ],
        "point_statuses": {
            result.point_id: result.status.value
            for result in summary.point_results
        },
        "infra_attempts": {
            result.point_id: result.infra_attempts
            for result in summary.point_results
        },
        "batch_cleanup_complete": summary.cleanup_complete,
        "elapsed_s": float(elapsed_s),
    }
    return (
        0 if summary.status is BatchTerminalStatus.COMPLETED else 1,
        document,
    )


def _validate_broker_ready(document, expected):
    fields = {
        "schema_version", "kind", "batch_id", "run_mode", "coordinator_epoch",
        "broker_generation", "image_id", "yolo_weights_sha256",
        "grounded_manifest_sha256", "models",
    }
    if type(document) is not dict or set(document) != fields:
        raise CliError("BROKER_READY_RECEIPT_SCHEMA")
    if document["schema_version"] != 1 or document["kind"] != "so101_parallel_broker_ready":
        raise CliError("BROKER_READY_RECEIPT_SCHEMA")
    for name, value in expected.items():
        if type(document.get(name)) is not type(value) or document.get(name) != value:
            raise CliError("BROKER_READY_RECEIPT_IDENTITY")
    models = document["models"]
    expected_models = {
        "plastic-cup-yolo11n-seg-v1": {
            "ready": True,
            "weights_sha256": expected["yolo_weights_sha256"],
        },
        "grounded-sam": {
            "ready": True,
            "manifest_sha256": expected["grounded_manifest_sha256"],
        },
    }
    if models != expected_models:
        raise CliError("BROKER_READY_RECEIPT_MODELS")
    return True
