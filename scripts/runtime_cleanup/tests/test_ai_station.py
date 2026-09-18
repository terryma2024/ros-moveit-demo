import importlib.util
import io
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'ai_station.py'
spec = importlib.util.spec_from_file_location('ai_station_cleanup', SCRIPT)
cleanup = None
if SCRIPT.exists():
    cleanup = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = cleanup
    spec.loader.exec_module(cleanup)


class CommandTests(unittest.TestCase):
    def test_usage_is_available_without_ros_or_third_party_python(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--apply', result.stdout)


@unittest.skipIf(cleanup is None, 'implementation not yet present')
class SafetyTests(unittest.TestCase):
    def process(self, argv, exe='/usr/bin/python3', maps=''):
        return cleanup.Process(123, 1, 100, 1000, tuple(argv), exe, 'S', maps)

    def test_codex_prompt_and_inherited_ros_context_are_not_runtime_identity(self):
        process = self.process(['codex', 'stop so101_teleop_server.py and ros2'], '/usr/bin/codex')
        self.assertFalse(cleanup.runtime_reason(process))

    def test_training_script_is_not_classified_by_so101_prefix(self):
        self.assertFalse(cleanup.runtime_reason(self.process(['python3', '/work/so101_act_train.py'])))

    def test_teleop_entry_and_ros_installed_binary_are_targets(self):
        self.assertTrue(cleanup.runtime_reason(self.process(['python3', '/work/so101_teleop_server.py'])))
        self.assertTrue(cleanup.runtime_reason(self.process(['/opt/ros/jazzy/lib/rviz2/rviz2'], '/opt/ros/jazzy/lib/rviz2/rviz2')))

    def test_loaded_ros_library_identifies_an_arbitrary_python_node(self):
        self.assertTrue(cleanup.runtime_reason(self.process(['python3', '/work/custom_node.py'], maps='/opt/ros/jazzy/lib/librcl.so')))

    def test_interpreter_flags_and_daemon_module_are_recognized(self):
        self.assertTrue(cleanup.runtime_reason(self.process(['python3', '-u', '/work/so101_teleop_server.py'])))
        self.assertTrue(cleanup.runtime_reason(self.process(['python3', '-m', 'ros2cli.daemon'])))

    def test_pid_reuse_refuses_signal(self):
        original = self.process(['python3', '/work/so101_teleop_server.py'])
        replacement = cleanup.Process(123, 1, 101, 1000, original.argv, original.exe, 'S', '')
        with patch.object(cleanup, 'read_process', return_value=replacement), patch.object(cleanup.os, 'pidfd_open', return_value=55), patch.object(cleanup.os, 'close'), patch.object(cleanup.signal, 'pidfd_send_signal') as send:
            with self.assertRaisesRegex(RuntimeError, 'identity changed'):
                cleanup.stop_process(original, 0.1)
            send.assert_not_called()

    def test_timeout_does_not_escalate_to_term_or_kill(self):
        original = self.process(['python3', '/work/so101_teleop_server.py'])
        with patch.object(cleanup, 'read_process', return_value=original), patch.object(cleanup.os, 'pidfd_open', return_value=55), patch.object(cleanup.os, 'close'), patch.object(cleanup.select, 'select', return_value=([], [], [])), patch.object(cleanup.signal, 'pidfd_send_signal') as send:
            with self.assertRaisesRegex(RuntimeError, 'no automatic escalation'):
                cleanup.stop_process(original, 0.1)
            send.assert_called_once_with(55, signal.SIGINT)

    def test_tmux_permission_error_is_not_treated_as_an_absent_server(self):
        denied = subprocess.CompletedProcess([], 1, '', 'error connecting: Permission denied')
        with patch.object(cleanup.shutil, 'which', return_value='/usr/bin/tmux'), patch.object(cleanup.subprocess, 'run', return_value=denied):
            with self.assertRaisesRegex(RuntimeError, 'Permission denied'):
                cleanup.list_panes()

    def test_replaced_session_is_not_closed(self):
        original = {'session': 'so101-teleop', 'pane': '%62', 'pid': '100', 'command': 'zsh'}
        replacement = {**original, 'pid': '101'}
        with patch.object(cleanup, 'list_panes', return_value=[replacement]), patch.object(cleanup, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'identity changed'):
                cleanup.close_sessions({'panes': [original], 'processes': []}, Path('/unused'))
            run.assert_not_called()

    def test_session_with_non_ros_child_is_preserved(self):
        pane = {'session': 'so101-teleop', 'pane': '%62', 'pid': '123', 'command': 'zsh'}
        shell = self.process(['zsh'], '/usr/bin/zsh')
        child = cleanup.Process(124, 123, 101, 1000, ('codex',), '/usr/bin/codex', 'S', '')
        root = Path('/proc/124')
        with patch.object(cleanup, 'list_panes', return_value=[pane]), patch.object(cleanup.Path, 'iterdir', return_value=[root]), patch.object(cleanup, 'read_process', side_effect=[shell, child]), patch.object(cleanup, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'still has child'):
                cleanup.close_sessions({'panes': [pane], 'processes': [shell]}, Path('/unused'))
            run.assert_not_called()

    def test_preview_never_signals_or_closes_sessions(self):
        with patch.object(cleanup.socket, 'gethostname', return_value='AI-STATION-001'), patch.object(cleanup, 'snapshot', return_value={'processes': [], 'targets': [], 'panes': [], 'blockers': []}), patch.object(cleanup, 'stop_process') as stop, patch.object(cleanup, 'close_sessions') as close, patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(cleanup.main([]), 0)
            stop.assert_not_called()
            close.assert_not_called()

    def test_host_mismatch_prevents_any_discovery_or_action(self):
        with patch.object(cleanup.socket, 'gethostname', return_value='another-host'), patch.object(cleanup, 'snapshot') as scan:
            self.assertEqual(cleanup.main([]), 2)
            scan.assert_not_called()

    def test_blocked_apply_performs_no_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory) / 'new-evidence')
            with patch.object(cleanup.socket, 'gethostname', return_value='AI-STATION-001'), patch.object(cleanup, 'snapshot', return_value={'processes': [], 'targets': [], 'panes': [], 'blockers': ['active managed service']}), patch.object(cleanup, 'stop_process') as stop:
                self.assertEqual(cleanup.main(['--apply', '--evidence-dir', output]), 2)
                stop.assert_not_called()

    def test_existing_evidence_directory_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / 'before.json'
            original.write_text('keep this evidence')
            with patch.object(cleanup.socket, 'gethostname', return_value='AI-STATION-001'), patch.object(cleanup, 'snapshot') as scan:
                self.assertEqual(cleanup.main(['--apply', '--evidence-dir', directory]), 2)
                scan.assert_not_called()
            self.assertEqual(original.read_text(), 'keep this evidence')

    def test_invalid_timeout_is_rejected_before_inspection(self):
        with patch.object(cleanup.socket, 'gethostname', return_value='AI-STATION-001'), patch.object(cleanup, 'snapshot') as scan:
            self.assertEqual(cleanup.main(['--timeout', 'nan']), 2)
            scan.assert_not_called()

    def test_real_pidfd_stop_preserves_helper_environment_files(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / 'so101_teleop_server.py'
            helper.write_text('import time\ntime.sleep(60)\n')
            process = subprocess.Popen([sys.executable, str(helper)], stderr=subprocess.DEVNULL)
            try:
                target = cleanup.read_process(process.pid)
                self.assertTrue(cleanup.runtime_reason(target))
                cleanup.stop_process(target, 2)
                process.wait(timeout=2)
                self.assertEqual(helper.read_text(), 'import time\ntime.sleep(60)\n')
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()


if __name__ == '__main__':
    unittest.main()
