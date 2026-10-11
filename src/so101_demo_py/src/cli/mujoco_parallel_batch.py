"""User entry point for an isolated, dynamically leased MuJoCo validation batch."""

from __future__ import annotations

import json
from pathlib import Path
import signal
import sys
import threading
import time

from so101_demo.cli.mujoco_batch.common import CliError, _write_json
from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
from so101_demo.cli.mujoco_batch.outcome import adaptive_outcome_document, outcome_document
from so101_demo.cli.mujoco_batch.provenance import verify_provenance
from so101_demo.cli.mujoco_batch.request import prepare_batch
from so101_demo.cli.mujoco_batch.worker_process import _run_worker_spec
from so101_demo.parallel_batch.adaptive_pool import (
    ProductionAdaptivePoolFactory,
)
from so101_demo.parallel_batch.adaptive_runner import (
    AdaptiveBatchRunner,
    AdaptiveRunnerError,
)
from so101_demo.parallel_batch.contracts import (
    ContractError,
)


def _run_with_shutdown_signals(call):
    """Turn SIGINT/SIGTERM into the same bounded exception/finally path."""

    if threading.current_thread() is not threading.main_thread():
        return call()
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    terminating = False

    def terminate(number, _frame):
        nonlocal terminating
        if terminating:
            return
        terminating = True
        raise CliError(f"SHUTDOWN_SIGNAL:{signal.Signals(number).name}")

    try:
        for number in previous:
            signal.signal(number, terminate)
        return call()
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def run_cli(
    argv=None,
    *,
    provenance_verifier=verify_provenance,
    composition_factory=ProductionBatchComposition,
) -> int:
    try:
        spec = prepare_batch(argv, provenance_verifier=provenance_verifier)
        if spec.adaptive_request is not None:
            task_root = spec.adaptive_request.evidence_root
            task_root.mkdir(parents=True, mode=0o700, exist_ok=True)
            runner = AdaptiveBatchRunner(
                spec.adaptive_request,
                ProductionAdaptivePoolFactory(
                    spec,
                    composition_factory=composition_factory,
                ),
            )
            root = spec.adaptive_request.runtime_root
            started = time.monotonic()
            try:
                _write_json(root / "batch_manifest.json", spec.manifest)
                summary = _run_with_shutdown_signals(runner.run)
            finally:
                runner.close()
            code, document = adaptive_outcome_document(
                summary,
                elapsed_s=time.monotonic() - started,
            )
            _write_json(root / "aggregate_results.json", document)
            print(json.dumps(document, sort_keys=True))
            return code
        composition = composition_factory(spec)
        root = spec.request.evidence_root
        if not root.exists():
            root.mkdir(parents=True, mode=0o700)
        if not spec.resume:
            _write_json(root / "batch_manifest.json", spec.manifest)
        summary = _run_with_shutdown_signals(composition.run)
        code, document = outcome_document(summary)
        aggregate = root / "aggregate_results.json"
        _write_json(aggregate, document)
        print(json.dumps(document, sort_keys=True))
        return code
    except (
        AdaptiveRunnerError,
        CliError,
        ContractError,
        OSError,
        ValueError,
    ) as error:
        print(json.dumps({"status": "ERROR", "message": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


def main(argv=None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values[:1] == ["--internal-worker"]:
        if len(values) != 2:
            return 1
        return _run_with_shutdown_signals(
            lambda: _run_worker_spec(Path(values[1]))
        )
    return run_cli(values)


if __name__ == "__main__":
    raise SystemExit(main())
