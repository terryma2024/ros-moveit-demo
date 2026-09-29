"""Run one Task 8 calibration measurement and seal its raw batch.

The measurement itself is the driver named by ``--driver`` (``module:callable``); this entry
point owns admission (bound contract), the ledger transitions PLANNED -> RUNNING ->
VALID|INVALID, and the one-way batch seal. A failed or refused measurement never leaves a
sealed batch behind.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

_STATES = ("PLANNED", "RUNNING", "VALID", "INVALID")


def _load_driver(spec: str):
    module_name, _, attribute = spec.partition(":")
    if not module_name or not attribute:
        raise ValueError("MEASUREMENT_DRIVER_INVALID")
    return getattr(importlib.import_module(module_name), attribute)


def _append_ledger(path: Path, state: str, identity: dict, note: str) -> None:
    if state not in _STATES:
        raise ValueError("MEASUREMENT_LEDGER_STATE_INVALID")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"- Task 8P2 measurement {state}: "
                     f"contract={identity.get('contract_sha256')} "
                     f"provenance={identity.get('source_provenance_sha256')} {note}\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one Task 8 calibration measurement and close its raw batch")
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--identities", type=Path, required=True)
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--driver", default=None,
                        help="test-only module:callable override; production runs use the built-in driver")
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args(argv)

    from so101_demo.act.task8_measurement_contract import (
        close_measurement_batch, load_measurement_contract, require_v2_identity,
    )
    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementContext

    identities = json.loads(args.identities.read_text())
    contract = load_measurement_contract(args.contract, expected_hashes=identities)
    # the batch is sealed with the contract's ten-member identity; the ledger line keeps its own two-field shape
    identity = require_v2_identity(identities)
    ledger_identity = {"source_provenance_sha256": identity["source_provenance_sha256"],
                       "contract_sha256": contract["contract_sha256"]}
    _append_ledger(args.ledger, "PLANNED", ledger_identity, "admission verified")
    _append_ledger(args.ledger, "RUNNING", ledger_identity, "measurement starting")
    try:
        if args.driver:
            _load_driver(args.driver)(contract, args.batch_root)      # test-only injection
        else:
            from so101_demo.act.task8_measurement_driver import Task8MujocoMeasurementDriver
            context = CalibrationMeasurementContext(
                generation=identities["source_commit"],
                contract_sha256=identities["contract_sha256"],
                measurement_plan_sha256=identities["measurement_plan_sha256"],
                safe_interval_rad=identities["safe_interval_rad"],
                candidate_sha256=identities["candidate_sha256"], policy_sha256=identities["policy_sha256"],
                driver_source_sha256=identities["source_provenance_sha256"],
                controller_generation=identities["controller_generation"],
                broker_generation=identities["broker_generation"],
                evidence_root=str(args.batch_root.parent),
                resource_binding=identities["resource_binding"])
            from so101_demo.act.task8_measurement_driver import production_driver
            production_driver().run(context, args.batch_root)
    except BaseException as error:
        _append_ledger(args.ledger, "INVALID", ledger_identity, f"driver failed: {type(error).__name__}")
        raise
    sealed = close_measurement_batch(args.batch_root, identity)
    _append_ledger(args.ledger, "VALID", ledger_identity, f"sealed {sealed}")
    print(sealed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
