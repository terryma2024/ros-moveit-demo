from pathlib import Path

from setuptools import setup


package_name = "so101_gazebo_demo_py"
python_package = "so101_gazebo_demo"
package_root = Path(__file__).resolve().parent


def launch_files() -> list[str]:
    return [str(path.relative_to(package_root)) for path in sorted((package_root / "launch").glob("*.launch.py"))]


setup(
    name=package_name,
    version="0.2.0",
    packages=[python_package],
    package_dir={python_package: "src"},
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", launch_files()),
    ],
    install_requires=["setuptools", "so101_demo_py"],
    zip_safe=True,
    maintainer="SO-101 maintainers",
    maintainer_email="maintainer@example.com",
    description="Deprecated compatibility forwarders for so101_demo_py.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "pick_place_state_machine = so101_gazebo_demo.forwarder:main",
            "gazebo_attachment_state_relay = so101_gazebo_demo.forwarder:unsupported_main",
            "reset_so101_world = so101_gazebo_demo.forwarder:unsupported_main",
            "so101_moveit_scene = so101_gazebo_demo.forwarder:unsupported_main",
        ]
    },
)
