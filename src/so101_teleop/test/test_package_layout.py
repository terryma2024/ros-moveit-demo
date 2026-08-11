from pathlib import Path
import xml.etree.ElementTree as ET


PACKAGE = Path(__file__).resolve().parents[1]
CPP = PACKAGE.parent / "so101_gazebo_demo_cpp"


def test_teleop_is_a_single_standalone_package():
    assert PACKAGE.name == "so101_teleop"
    assert (PACKAGE / "package.xml").is_file()
    assert (PACKAGE / "CMakeLists.txt").is_file()
    assert (PACKAGE / "so101_teleop" / "server.py").is_file()
    assert (PACKAGE / "web" / "package.json").is_file()
    assert (PACKAGE / "launch" / "so101_teleop.launch.py").is_file()
    assert (PACKAGE / "scripts" / "tile_ai_station_guis.py").is_file()
    assert (PACKAGE / "scripts" / "gazebo_window_recorder.py").is_file()
    assert (PACKAGE / "scripts" / "so101_stack_inventory.py").is_file()
    assert (PACKAGE / "so101_teleop" / "gui" / "x11.py").is_file()


def test_cpp_package_has_no_legacy_teleop_or_tiler_entry():
    forbidden = (
        CPP / "so101_teleop",
        CPP / "web",
        CPP / "launch" / "so101_teleop.launch.py",
        CPP / "config" / "so101_teleop.yaml",
        CPP / "scripts" / "so101_teleop_server.py",
        CPP / "scripts" / "tile_ai_station_guis.py",
        CPP / "scripts" / "ai_station_x11.py",
        CPP / "scripts" / "gazebo_window_recorder.py",
        CPP / "scripts" / "so101_stack_inventory.py",
        CPP / "test" / "teleop",
        CPP / "test" / "test_tile_ai_station_guis.py",
        CPP / "test" / "test_ai_station_x11.py",
        CPP / "test" / "test_gazebo_window_recorder.py",
        CPP / "test" / "test_so101_stack_inventory.py",
    )
    assert not [str(path) for path in forbidden if path.exists()]


def test_gui_diagnostics_are_installed_by_the_teleop_owner():
    cmake = (PACKAGE / "CMakeLists.txt").read_text()
    for executable in (
        "tile_ai_station_guis.py",
        "gazebo_window_recorder.py",
        "so101_stack_inventory.py",
    ):
        assert f"scripts/{executable}" in cmake

    package = ET.parse(PACKAGE / "package.xml").getroot()
    dependencies = {
        element.text
        for tag in ("depend", "exec_depend")
        for element in package.findall(tag)
    }
    assert {"ffmpeg", "libx11-6", "x11-utils"} <= dependencies
