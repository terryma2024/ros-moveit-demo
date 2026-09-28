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
    parser.add_argument("--driver", required=True, help="module:callable that fills the batch")
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args(argv)

    from so101_demo.act.task8_measurement_contract import (
        close_measurement_batch, load_measurement_contract,
    )

    identities = json.loads(args.identities.read_text())
    contract = load_measurement_contract(args.contract, expected_hashes=identities)
    identity = {"source_provenance_sha256": identities["source_provenance_sha256"],
                "contract_sha256": contract["contract_sha256"]}
    _append_ledger(args.ledger, "PLANNED", identity, "admission verified")
    _append_ledger(args.ledger, "RUNNING", identity, "measurement starting")
    try:
        _load_driver(args.driver)(contract, args.batch_root)
    except BaseException as error:
        _append_ledger(args.ledger, "INVALID", identity, f"driver failed: {type(error).__name__}")
        raise
    sealed = close_measurement_batch(args.batch_root, identity)
    _append_ledger(args.ledger, "VALID", identity, f"sealed {sealed}")
    print(sealed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
