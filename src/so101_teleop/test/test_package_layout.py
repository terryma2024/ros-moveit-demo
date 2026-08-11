from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
CPP = PACKAGE.parent / "so101_gazebo_demo_cpp"


def test_teleop_is_a_single_standalone_package():
    assert PACKAGE.name == "so101_teleop"
    assert (PACKAGE / "package.xml").is_file()
    assert (PACKAGE / "CMakeLists.txt").is_file()
    assert (PACKAGE / "so101_teleop" / "server.py").is_file()
    assert (PACKAGE / "web" / "package.json").is_file()
    assert (PACKAGE / "launch" / "so101_teleop.launch.py").is_file()


def test_cpp_package_has_no_legacy_teleop_or_tiler_entry():
    forbidden = (
        CPP / "so101_teleop",
        CPP / "web",
        CPP / "launch" / "so101_teleop.launch.py",
        CPP / "config" / "so101_teleop.yaml",
        CPP / "scripts" / "so101_teleop_server.py",
        CPP / "scripts" / "tile_ai_station_guis.py",
        CPP / "scripts" / "ai_station_x11.py",
        CPP / "test" / "teleop",
        CPP / "test" / "test_tile_ai_station_guis.py",
        CPP / "test" / "test_ai_station_x11.py",
    )
    assert not [str(path) for path in forbidden if path.exists()]
