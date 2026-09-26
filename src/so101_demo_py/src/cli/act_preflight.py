"""Emit current ACT calibration status; unmeasured checks never pass."""

import argparse
import json
from pathlib import Path

from so101_demo.act.calibration import (REQUIRED_CHECKS, installed_calibration_identity,
                                        require_gate, validate_partial)


def main(arguments=None):
    parser = argparse.ArgumentParser(prog="act_preflight")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--measured-report", type=Path)
    parser.add_argument("--source-root", type=Path)
    options = parser.parse_args(arguments)
    source_commit, config_hash = installed_calibration_identity(options.source_root)
    report = dict(schema_version=1,status="CALIBRATION_REQUIRED",source_commit=source_commit,
                  config_sha256=config_hash, measurements={},
                  checks={key:"UNMEASURED" for key in sorted(REQUIRED_CHECKS)})
    if options.measured_report:
        measured = json.loads(options.measured_report.read_text())
        if measured["source_commit"] != source_commit or measured["config_sha256"] != config_hash:
            raise ValueError("CALIBRATION_SOURCE_CONFIG_MISMATCH")
        if measured.get("status") == "QUALIFIED":
            require_gate(measured, "formal_collection")
        elif measured.get("status") == "TASK8_READY":
            require_gate(measured, "pick_place_validation")
        else:
            validate_partial(measured)
        report = measured
    options.output.parent.mkdir(parents=True,exist_ok=True)
    # Preserve every report version; never overwrite earlier measured evidence.
    with options.output.open("x") as stream:
        json.dump(report,stream,indent=2); stream.write("\n")
    print(report["status"])
    return 0 if report["status"] in ("TASK8_READY", "QUALIFIED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
