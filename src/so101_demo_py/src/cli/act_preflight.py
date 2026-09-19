"""Emit current ACT calibration status; unmeasured checks never pass."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from so101_demo.act.calibration import REQUIRED_CHECKS, require_qualified


def main(arguments=None):
    parser = argparse.ArgumentParser(prog="act_preflight")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--measured-report", type=Path)
    options = parser.parse_args(arguments)
    from ament_index_python.packages import get_package_share_directory
    share = Path(get_package_share_directory("so101_demo_py"))
    roots = (share / "assets/mujoco/act", share / "config/mujoco/act")
    files = {str(path.relative_to(share)): hashlib.sha256(path.read_bytes()).hexdigest()
             for root in roots for path in sorted(root.rglob("*")) if path.is_file()}
    if not files or any(not root.is_dir() for root in roots):
        raise ValueError("ACT_PROFILE_UNAVAILABLE")
    config_hash = hashlib.sha256(json.dumps(files,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    source_commit = subprocess.check_output(["git", "-C", str(Path(__file__).resolve().parent),
                                            "rev-parse", "HEAD"], text=True).strip()
    report = dict(schema_version=1,status="CALIBRATION_REQUIRED",source_commit=source_commit,
                  config_sha256=config_hash, measurements={},
                  checks={key:"UNMEASURED" for key in sorted(REQUIRED_CHECKS)})
    if options.measured_report:
        measured = json.loads(options.measured_report.read_text())
        if measured["source_commit"] != source_commit or measured["config_sha256"] != config_hash:
            raise ValueError("CALIBRATION_SOURCE_CONFIG_MISMATCH")
        require_qualified(measured)
        report = measured
    options.output.parent.mkdir(parents=True,exist_ok=True)
    # Preserve every report version; never overwrite earlier measured evidence.
    with options.output.open("x") as stream:
        json.dump(report,stream,indent=2); stream.write("\n")
    print(report["status"])
    return 0 if report["status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
