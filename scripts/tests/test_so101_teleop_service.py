"""Safety checks for the cross-platform installed service manager."""

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
            "schema": 1,
            "running": True,
            "pid": 12345,
            "uid": os.getuid(),
            "started": "start-token",
            "python": "/opt/ros/jazzy/.venv/bin/python",
            "entry": "/installed/so101_unified_web_server.py",
            "host": "127.0.0.1",
            "port": 8014,
            "evidence_root": "/data/work/so101-evidence/test/run",
        }

    def test_host_profiles_keep_platform_execution_config(self) -> None:
        mac = service.defaults("darwin")
        linux = service.defaults("linux")
        self.assertEqual(mac["config"], "parallel_batch_v4_macos_mps_w2.yaml")
        self.assertEqual(mac["coordinator"], "so101_macos_service_campaign")
        self.assertEqual(linux["config"], "parallel_batch_v3.yaml")
        self.assertEqual(linux["coordinator"], "so101_parallel_batch")

    def test_validation_service_does_not_enable_unconfigured_ros_bridge(self) -> None:
        cfg = service.defaults("darwin")
        cfg["platform"] = "darwin"
        cfg["install_prefix"] = "/installed"
        paths = service.layout(cfg)
        env = service.child_environment(cfg, paths, Path("/opt/data/work/so101-evidence/test/run"))
        self.assertNotIn("SO101_UNIFIED_ROS_PYTHON", env)
        self.assertNotIn("SO101_UNIFIED_INSTALL_PREFIX", env)
        self.assertNotIn("SO101_UNIFIED_SOCKET_DIR", env)
        self.assertEqual(env["SO101_TASK_ROOT"], env["SO101_UNIFIED_EVIDENCE_ROOT"])

    def test_start_and_check_use_installed_web_assets(self) -> None:
        cfg = service.defaults("linux")
        cfg.update({"platform": "linux", "install_prefix": "/installed",
                    "host": "127.0.0.1", "port": 8014})
        expected = ["--static-dir", "/installed/so101_teleop/share/so101_teleop/web"]
        self.assertEqual(service.command(cfg)[-2:], expected)
        self.assertEqual(service.command(cfg, check=True)[-3:], [*expected, "--check"])

    def test_ready_requires_web_page_as_well_as_validation(self) -> None:
        health = {"domains": {"validation": "ready"}}
        with patch.object(service, "request_json", return_value=health), \
             patch.object(service.urllib.request, "build_opener") as build_opener:
            response = build_opener.return_value.open.return_value.__enter__.return_value
            response.status = 503
            self.assertFalse(service.ready("http://127.0.0.1:8014"))
            response.status = 200
            self.assertTrue(service.ready("http://127.0.0.1:8014"))

    def test_changed_pid_identity_is_never_owned(self) -> None:
        with patch.object(service, "process_identity", return_value={
            "pid": 12345, "uid": os.getuid(), "started": "different-start",
            "argv": ["python", self.record["entry"], "--host", "127.0.0.1",
                     "--port", "8014"], "state": "S",
        }):
            with self.assertRaisesRegex(service.Refused, "OWNER_START_CHANGED"):
                service.verify_owned(self.record)

    def test_cleanup_refuses_unregistered_service(self) -> None:
        with self.assertRaisesRegex(service.Refused, "NO_MANAGED_SERVICE"):
            service.cleanup(self.state_path)

    def test_cleanup_refuses_active_campaign_without_signal(self) -> None:
        service.write_state(self.state_path, self.record)
        with patch.object(service, "verify_owned", return_value=True), \
             patch.object(service, "request_json", return_value=[{
                 "campaign_id": "campaign-1", "status": "RUNNING",
                 "batch_cleanup_complete": False,
             }]), \
             patch.object(service.os, "kill") as kill:
            with self.assertRaisesRegex(service.Refused, "CAMPAIGN_ACTIVE: campaign-1"):
                service.cleanup(self.state_path)
            kill.assert_not_called()
        self.assertTrue(service.read_state(self.state_path)["running"])

    def test_cleanup_refuses_terminal_label_without_cleanup_receipt(self) -> None:
        service.write_state(self.state_path, self.record)
        with patch.object(service, "verify_owned", return_value=True), \
             patch.object(service, "request_json", return_value=[{
                 "campaign_id": "campaign-2", "status": "INFRA_FAILED",
                 "batch_cleanup_complete": False,
             }]), \
             patch.object(service.os, "kill") as kill:
            with self.assertRaisesRegex(service.Refused, "CAMPAIGN_ACTIVE: campaign-2"):
                service.cleanup(self.state_path)
            kill.assert_not_called()

    def test_cleanup_stops_only_recorded_pid_after_terminal_campaign(self) -> None:
        service.write_state(self.state_path, self.record)
        campaigns = [{"campaign_id": "campaign-3", "status": "COMPLETED_WITH_FAILURES",
                      "batch_cleanup_complete": True}]
        ownership_checks = [True, True, True, False] if sys.platform == "linux" else [True, True, False]
        with patch.object(service, "verify_owned", side_effect=ownership_checks), \
             patch.object(service, "request_json", return_value=campaigns):
            if sys.platform == "linux":
                with patch.object(service.os, "pidfd_open", return_value=77) as open_pidfd, \
                     patch.object(service.signal, "pidfd_send_signal") as send, \
                     patch.object(service.os, "close"):
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
             patch.object(service, "request_json", return_value=[]), \
             patch.object(service, "process_identity", return_value={
                 "pid": 12345, "uid": os.getuid(), "started": "start-token",
                 "argv": [], "state": "S",
             }), \
             patch.object(service.time, "sleep"):
            if sys.platform == "linux":
                with patch.object(service.os, "pidfd_open", return_value=77), \
                     patch.object(service.signal, "pidfd_send_signal"), \
                     patch.object(service.os, "close"):
                    service.cleanup(self.state_path)
            else:
                with patch.object(service.os, "kill"):
                    service.cleanup(self.state_path)
        self.assertFalse(service.read_state(self.state_path)["running"])


if __name__ == "__main__":
    unittest.main()
