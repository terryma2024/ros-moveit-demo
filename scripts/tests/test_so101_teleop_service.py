"""The slim installed teleop service manager: starts only the unified web service (no Expert Validation, no broker)."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "so101-teleop-service.py"
SPEC = importlib.util.spec_from_file_location("so101_teleop_service_manager", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
service = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(service)


class ServiceManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="so101-service-manager-")
        self.addCleanup(self.temp.cleanup)
        self.state_path = Path(self.temp.name) / "state.json"
        self.record = {
            "schema": 1, "running": True, "pid": 12345, "uid": os.getuid(), "started": "start-token",
            "python": "/opt/ros/jazzy/.venv/bin/python", "entry": "/installed/so101_unified_web_server.py",
            "host": "127.0.0.1", "port": 8014, "evidence_root": "/data/work/so101-evidence/test/run",
        }

    def test_the_command_line_keeps_the_operator_interface(self) -> None:
        args = service.arguments(["--platform", "linux", "start", "--host", "127.0.0.1", "--port", "8014"])
        self.assertEqual((args.platform, args.command, args.port), ("linux", "start", 8014))
        for command in ("doctor", "start", "status", "cleanup"):
            service.arguments(["--platform", "darwin", command])

    def test_the_launcher_has_no_expert_validation_or_model_options(self) -> None:
        for option in ("--yolo-weights", "--grounded-root"):
            with self.assertRaises(SystemExit), patch("sys.stderr"):
                service.arguments(["--platform", "linux", "doctor", option, "/x"])
        text = SCRIPT.read_text()
        for retired in ("SO101_VALIDATION", "expert-validation", "adaptive", "parallel_batch", "grounded", "yolo"):
            self.assertNotIn(retired, text)

    def test_the_layout_names_only_the_unified_entry_and_web_assets(self) -> None:
        cfg = service.defaults("linux")
        cfg["install_prefix"] = "/installed"
        self.assertEqual(sorted(service.layout(cfg)), ["entry", "web"])

    def test_the_child_environment_carries_no_validation_variables(self) -> None:
        for platform in ("darwin", "linux"):
            cfg = service.defaults(platform)
            cfg.update(platform=platform, install_prefix="/installed")
            env = service.child_environment(cfg, service.layout(cfg), Path("/data/work/so101-evidence/test/run"))
            self.assertFalse([name for name in env if name.startswith("SO101_VALIDATION")])
            self.assertEqual(env["SO101_UNIFIED_EVIDENCE_ROOT"], "/data/work/so101-evidence/test/run")
            self.assertEqual(env["SO101_TASK_ROOT"], env["SO101_UNIFIED_EVIDENCE_ROOT"])
            self.assertNotIn("SO101_UNIFIED_ROS_PYTHON", env)

    def test_start_and_check_use_installed_web_assets(self) -> None:
        cfg = service.defaults("linux")
        cfg.update({"platform": "linux", "install_prefix": "/installed", "host": "127.0.0.1", "port": 8014})
        expected = ["--static-dir", "/installed/so101_teleop/share/so101_teleop/web"]
        self.assertEqual(service.command(cfg)[-2:], expected)
        self.assertEqual(service.command(cfg, check=True)[-3:], [*expected, "--check"])

    def test_ready_needs_a_live_service_and_the_web_page(self) -> None:
        with patch.object(service, "request_json", return_value={"live": True, "started": True}), \
             patch.object(service.urllib.request, "build_opener") as build_opener:
            response = build_opener.return_value.open.return_value.__enter__.return_value
            response.status = 503
            self.assertFalse(service.ready("http://127.0.0.1:8014"))
            response.status = 200
            self.assertTrue(service.ready("http://127.0.0.1:8014"))
        with patch.object(service, "request_json", return_value={"live": True, "started": False}):
            self.assertFalse(service.ready("http://127.0.0.1:8014"))

    def test_changed_pid_identity_is_never_owned(self) -> None:
        with patch.object(service, "process_identity", return_value={
                "pid": 12345, "uid": os.getuid(), "started": "different-start",
                "argv": ["python", self.record["entry"], "--host", "127.0.0.1", "--port", "8014"], "state": "S"}):
            with self.assertRaisesRegex(service.Refused, "OWNER_START_CHANGED"):
                service.verify_owned(self.record)

    def test_cleanup_refuses_unregistered_service(self) -> None:
        with self.assertRaisesRegex(service.Refused, "NO_MANAGED_SERVICE"):
            service.cleanup(self.state_path)

    def test_cleanup_refuses_while_the_arbiter_is_not_idle_without_a_signal(self) -> None:
        service.write_state(self.state_path, self.record)
        for state in ("BLOCKED", "ACT_ACTIVE"):
            with patch.object(service, "verify_owned", return_value=True), \
                 patch.object(service, "request_json", return_value={"global_state": state}), \
                 patch.object(service.os, "kill") as kill:
                with self.assertRaisesRegex(service.Refused, f"SERVICE_BUSY: {state}"):
                    service.cleanup(self.state_path)
                kill.assert_not_called()
        self.assertTrue(service.read_state(self.state_path)["running"])

    def test_cleanup_with_an_unreadable_state_refuses(self) -> None:
        service.write_state(self.state_path, self.record)
        with patch.object(service, "verify_owned", return_value=True), \
             patch.object(service, "request_json", side_effect=OSError("down")), \
             patch.object(service.os, "kill") as kill:
            with self.assertRaisesRegex(service.Refused, "SERVICE_STATE_UNKNOWN"):
                service.cleanup(self.state_path)
            kill.assert_not_called()

    def test_cleanup_stops_only_the_recorded_pid_when_idle(self) -> None:
        service.write_state(self.state_path, self.record)
        checks = [True, True, True, False] if sys.platform == "linux" else [True, True, False]
        with patch.object(service, "verify_owned", side_effect=checks), \
             patch.object(service, "request_json", return_value={"global_state": "IDLE"}):
            if sys.platform == "linux":
                with patch.object(service.os, "pidfd_open", return_value=77) as open_pidfd, \
                     patch.object(service.signal, "pidfd_send_signal") as send, patch.object(service.os, "close"):
                    service.cleanup(self.state_path)
                    open_pidfd.assert_called_once_with(12345)
                    send.assert_called_once_with(77, signal.SIGTERM)
            else:
                with patch.object(service.os, "kill") as kill:
                    service.cleanup(self.state_path)
                    kill.assert_called_once_with(12345, signal.SIGTERM)
        self.assertFalse(service.read_state(self.state_path)["running"])

    def test_cleanup_tolerates_cmdline_disappearing_during_exit(self) -> None:
        service.write_state(self.state_path, self.record)
        before_exit = [True, True, True] if sys.platform == "linux" else [True, True]
        checks = before_exit + [service.Refused("OWNER_COMMAND_CHANGED"), False]
        with patch.object(service, "verify_owned", side_effect=checks), \
             patch.object(service, "request_json", return_value={"global_state": "IDLE"}), \
             patch.object(service, "process_identity", return_value={
                 "pid": 12345, "uid": os.getuid(), "started": "start-token", "argv": [], "state": "S"}), \
             patch.object(service.time, "sleep"):
            if sys.platform == "linux":
                with patch.object(service.os, "pidfd_open", return_value=77), \
                     patch.object(service.signal, "pidfd_send_signal"), patch.object(service.os, "close"):
                    service.cleanup(self.state_path)
            else:
                with patch.object(service.os, "kill"):
                    service.cleanup(self.state_path)
        self.assertFalse(service.read_state(self.state_path)["running"])


if __name__ == "__main__":
    unittest.main()
