import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import types
import unittest


REPOSITORY = Path(__file__).resolve().parents[4]
ROOT = REPOSITORY / ".agents" / "skills" / "gui-capture"
SCRIPT = ROOT / "scripts" / "gui-capture.py"


def load_capture_module():
    if not SCRIPT.is_file():
        raise AssertionError("the generalized capture helper does not exist yet")
    spec = importlib.util.spec_from_file_location("gui_window_capture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GuiCaptureTest(unittest.TestCase):
    def test_skill_is_renamed_and_no_old_owner_remains(self):
        self.assertTrue(ROOT.is_dir())
        self.assertFalse(
            (REPOSITORY / ".agents" / "skills" / "ai-station-gui").exists()
        )
        self.assertIn("name: gui-capture", (ROOT / "SKILL.md").read_text())

    def test_macos_capture_focuses_then_uses_screencapture_window_id(self):
        module = load_capture_module()
        events = []
        output = Path(self._testMethodName + ".png")
        self.addCleanup(output.unlink, missing_ok=True)
        window = {
            "id": 4107,
            "owner": "Codex",
            "title": "moveit-demo",
            "x": -1512,
            "y": 80,
            "width": 1400,
            "height": 900,
        }

        def focus(selected):
            events.append(("focus", selected["id"]))

        def run(command, **_kwargs):
            events.append(("run", command))
            output.write_bytes(b"png")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        module.capture_macos_window(
            window,
            output,
            focus_window=focus,
            runner=run,
            sleeper=lambda _seconds: None,
        )

        self.assertEqual(events[0], ("focus", 4107))
        self.assertEqual(
            events[1],
            ("run", ["screencapture", "-x", "-l", "4107", str(output)]),
        )
        self.assertEqual(output.read_bytes(), b"png")

    def test_macos_focus_allows_unique_geometry_match_when_cg_title_is_empty(self):
        module = load_capture_module()
        commands = []

        def run(command, **_kwargs):
            commands.append(command)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        module.focus_macos_window(
            {
                "owner_pid": 27393,
                "title": "",
                "x": 1405,
                "y": 360,
                "width": 943,
                "height": 889,
            },
            runner=run,
        )

        script = commands[0][-1]
        self.assertIn(
            "String(target.title) === '' ||",
            script,
            "an empty CoreGraphics title must not reject the unique PID/geometry match",
        )
        self.assertIn(
            "if (matches.length !== 1)",
            script,
            "the empty-title fallback must remain fail-closed on ambiguity",
        )

    def test_macos_window_inventory_preserves_global_multimonitor_coordinates(self):
        module = load_capture_module()
        payload = json.dumps(
            [
                {
                    "id": 90,
                    "owner": "Codex",
                    "owner_pid": 123,
                    "title": "Left monitor",
                    "layer": 0,
                    "onscreen": True,
                    "alpha": 1,
                    "bounds": {
                        "X": -1728,
                        "Y": 40,
                        "Width": 1200,
                        "Height": 800,
                    },
                }
            ]
        )

        windows = module.parse_macos_window_inventory(payload)

        self.assertEqual(windows[0]["x"], -1728)
        self.assertEqual(windows[0]["width"], 1200)

    def test_window_selector_accepts_exact_id_and_rejects_ambiguous_query(self):
        module = load_capture_module()
        windows = [
            {
                "id": 10,
                "owner": "Codex",
                "title": "alpha",
                "width": 800,
                "height": 600,
            },
            {
                "id": 20,
                "owner": "Codex",
                "title": "beta",
                "width": 800,
                "height": 600,
            },
        ]

        self.assertEqual(module.select_window(windows, window_id=20)["title"], "beta")
        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            module.select_window(windows, query="Codex")

    def test_manifest_contract_is_one_target_window_not_a_desktop(self):
        module = load_capture_module()
        output_root = Path(self._testMethodName)
        self.addCleanup(
            lambda: __import__("shutil").rmtree(output_root, ignore_errors=True)
        )
        window = {
            "id": 42,
            "owner": "RViz",
            "title": "Robot View",
            "width": 800,
            "height": 600,
            "x": 1920,
            "y": 0,
        }

        manifest = module.capture_session(
            output_root,
            query="Robot View",
            platform_name="macos",
            window_loader=lambda: [window],
            window_grabber=lambda _window, output: output.write_bytes(b"window-png"),
        )

        self.assertEqual(manifest["capture_mode"], "window")
        self.assertEqual(manifest["platform"], "macos")
        self.assertEqual(manifest["window"]["id"], 42)
        self.assertEqual(Path(manifest["image"]).read_bytes(), b"window-png")
        self.assertNotIn("desktop", manifest)

    def test_skill_contract_requires_exact_macos_window_capture(self):
        skill = (ROOT / "SKILL.md").read_text()
        sop = (ROOT / "references" / "platform-sop.md").read_text()
        contract = (ROOT / "references" / "capture-contract.md").read_text()

        for required in (
            "macOS",
            "GNOME",
            "snapshot -> action -> fresh snapshot",
            "screencapture -l",
            "Multi-monitor",
            "GNOME Wayland",
        ):
            self.assertIn(required, skill)
        self.assertIn("AXRaise", sop)
        self.assertIn("negative `x` or `y`", sop)
        self.assertIn("not a crop of the combined desktop", sop)
        self.assertIn("Window-level capture is preferred", sop)
        self.assertIn("desktop capture explicitly", sop)
        self.assertNotIn("macOS deliberately rejects desktop", skill)
        self.assertNotIn("macOS does not support this mode", contract)

    def test_current_so101_skills_use_the_renamed_owner(self):
        current_docs = (
            REPOSITORY
            / ".agents"
            / "skills"
            / "so101-dev"
            / "references"
            / "ai-station-access.md",
            REPOSITORY
            / ".agents"
            / "skills"
            / "so101-dev"
            / "references"
            / "test-and-acceptance.md",
            REPOSITORY / ".agents" / "skills" / "gazebo-video-debug" / "SKILL.md",
        )

        for path in current_docs:
            text = path.read_text()
            self.assertIn("gui-capture", text, path)
            self.assertNotIn("ai-station-gui", text, path)

    def test_gnome_inventory_uses_absolute_multimonitor_geometry(self):
        module = load_capture_module()
        payload = (
            '  0x4200106 "moveit.rviz - RViz": ("rviz2" "rviz2")  '
            '1887x2091+14+49  -1906+124\n'
        )

        windows = module.parse_gnome_x11_window_inventory(payload)

        self.assertEqual(windows[0]["x"], -1906)
        self.assertEqual(windows[0]["y"], 124)

    def test_macos_desktop_capture_is_available_for_explicit_debug_use(self):
        module = load_capture_module()
        output_root = Path(self._testMethodName)
        self.addCleanup(
            lambda: __import__("shutil").rmtree(output_root, ignore_errors=True)
        )

        try:
            manifest = module.capture_session(
                output_root,
                desktop=True,
                platform_name="macos",
                desktop_grabber=lambda output: output.write_bytes(b"macos-desktop"),
            )
        except RuntimeError as error:
            self.fail(f"explicit macOS desktop capture must be supported: {error}")

        self.assertEqual(manifest["capture_mode"], "desktop")
        self.assertIsNone(manifest["window"])
        self.assertEqual(Path(manifest["image"]).name, "desktop.png")
        self.assertEqual(Path(manifest["image"]).read_bytes(), b"macos-desktop")

    def test_macos_desktop_capture_uses_screencapture(self):
        module = load_capture_module()
        self.assertTrue(
            hasattr(module, "capture_macos_desktop"),
            "macOS desktop capture backend is missing",
        )
        output = Path(self._testMethodName + ".png")
        self.addCleanup(output.unlink, missing_ok=True)
        commands = []

        def run(command, **_kwargs):
            commands.append(command)
            output.write_bytes(b"png")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        module.capture_macos_desktop(output, runner=run)

        self.assertEqual(commands, [["screencapture", "-x", str(output)]])

    def test_atomic_capture_uses_a_visible_temporary_name_for_screencapture(self):
        module = load_capture_module()
        output_root = Path(self._testMethodName)
        self.addCleanup(
            lambda: __import__("shutil").rmtree(output_root, ignore_errors=True)
        )
        temporary_names = []

        module.capture_session(
            output_root,
            query="Robot View",
            platform_name="macos",
            window_loader=lambda: [
                {
                    "id": 42,
                    "owner": "RViz",
                    "title": "Robot View",
                    "width": 800,
                    "height": 600,
                    "x": 0,
                    "y": 0,
                }
            ],
            window_grabber=lambda _window, output: (
                temporary_names.append(output.name), output.write_bytes(b"png")
            ),
        )

        self.assertFalse(temporary_names[0].startswith("."))

    def test_gnome_window_capture_raises_activates_and_restores(self):
        module = load_capture_module()
        output = Path(self._testMethodName + ".png")
        self.addCleanup(output.unlink, missing_ok=True)
        events = []
        grabs = []

        class Image:
            def save(self, output_path, image_format):
                grabs.append((output_path, image_format))
                output_path.write_bytes(b"gnome-window")

        pil = types.ModuleType("PIL")
        pil.ImageGrab = SimpleNamespace(
            grab=lambda **kwargs: (grabs.append(kwargs), Image())[1]
        )
        previous_pil = sys.modules.get("PIL")
        sys.modules["PIL"] = pil
        self.addCleanup(
            lambda: sys.modules.__setitem__("PIL", previous_pil)
            if previous_pil is not None
            else sys.modules.pop("PIL", None)
        )

        class Manager:
            def raise_window(self, window_id):
                events.append(("raise", window_id))

            def activate_window(self, window_id):
                events.append(("activate", window_id))

            def close(self):
                events.append(("close", None))

        original_active = module.active_gnome_x11_window_id
        module.active_gnome_x11_window_id = lambda: 99
        self.addCleanup(
            setattr, module, "active_gnome_x11_window_id", original_active
        )

        module.capture_gnome_x11_window(
            {
                "id": 42,
                "x": -1906,
                "y": 124,
                "width": 800,
                "height": 600,
            },
            output,
            display_name=":1",
            manager_factory=lambda _display: Manager(),
            sleeper=lambda _seconds: None,
        )

        self.assertEqual(
            events,
            [("raise", 42), ("activate", 42), ("activate", 99), ("close", None)],
        )
        self.assertEqual(
            grabs[0]["bbox"], (-1906, 124, -1106, 724)
        )
        self.assertEqual(output.read_bytes(), b"gnome-window")


if __name__ == "__main__":
    unittest.main()
