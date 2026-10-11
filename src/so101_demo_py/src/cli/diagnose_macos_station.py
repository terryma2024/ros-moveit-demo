"""Bounded macOS station diagnostic: locate the first bad boundary, do not guess a cause.

Design section 4.2 replaces "wait for the whole motion stack and report a generic timeout"
with layered observation:

* two closed launch modes -- ``MINIMAL_CONTROLLER_MANAGER`` (controller_manager's own
  ``ros2_control_node``, no ``RobotSystem``) and ``ROBOT_SYSTEM_CONTROLLER_MANAGER`` (the
  MuJoCo hardware node with the same robot description and controller/plugin config as the
  station);
* a direct ``/controller_manager/list_controllers`` client that starts as soon as its own
  service is visible, independent of the MoveIt service/action graph;
* structured phases with independent deadlines (``PLUGIN_RESOLVED`` ...
  ``CONTROLLERS_ACTIVE``) and distinct failure codes for DDS invisibility, a bounded call
  timeout, inactive controllers and missing MoveIt services/actions.

The report records what was observed -- server PID/birth identity, loaded images, ROS
domain, the direct call result, the node/service graph and the phase deadlines. It never
declares a root cause from a single observation. Arbitrary launch argv is not accepted: the
CLI only selects one of the two closed modes.
"""

from __future__ import annotations

from collections.abc import Sequence
import json
import os
from pathlib import Path
import uuid

from so101_demo.cli.macos_station.contracts import StationMode
from so101_demo.cli.macos_station.diagnostic_run import parse_arguments, run_diagnostic
from so101_demo.cli.macos_station.farm_run import (
    run_fixed_dylib_farm_full_task_station,
    run_full_task_station_control,
)
from so101_demo.cli.macos_station.observation import resolve_mode, station_robot_description


def main(arguments: Sequence[str] | None = None) -> int:

    options = parse_arguments(arguments)
    mode = resolve_mode(options.mode)
    if mode is StationMode.FIXED_DYLIB_FARM_FULL_TASK_STATION:
        return run_fixed_dylib_farm_full_task_station(
            farm_contract_receipt=Path(options.farm_contract_receipt),
            run_binding_path=Path(options.run_binding),
            output_path=Path(options.output),
            timeout_s=options.timeout_s,
        )
    if mode is StationMode.FULL_TASK_STATION:
        report = run_full_task_station_control(
            manifest_path=Path(options.control_set_manifest),
            binding_path=Path(options.run_binding),
            control=options.control,
        )
        print(json.dumps(report, sort_keys=True), flush=True)
        return 0 if report["observation_class"] == "PASS" else 1
    session_id = options.session_id or f"diagnostic-{uuid.uuid4().hex}"
    if options.share_root is not None:
        share_root = Path(options.share_root)
    else:  # pragma: no cover - live path
        from ament_index_python.packages import get_package_share_directory

        share_root = Path(get_package_share_directory("so101_demo_py"))
    robot_description = None
    if mode is StationMode.ROBOT_SYSTEM_CONTROLLER_MANAGER:
        robot_description = station_robot_description(share_root)
    report, _handle = run_diagnostic(
        mode=mode,
        share_root=share_root,
        session_id=session_id,
        ros_domain_id=int(os.environ.get("ROS_DOMAIN_ID", "0")),
        timeout_s=options.timeout_s,
        robot_description=robot_description,
    )
    print(json.dumps(report.as_document(), sort_keys=True), flush=True)
    return 0 if report.failure_code is None else 1


if __name__ == "__main__":  # pragma: no cover - console script path
    raise SystemExit(main())
