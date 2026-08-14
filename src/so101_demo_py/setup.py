from pathlib import Path

from setuptools import find_packages, setup

package_name = "so101_demo_py"
python_package = "so101_demo"
package_root = Path(__file__).resolve().parent
subpackages = find_packages(where="src")


def installed_resources() -> list[tuple[str, list[str]]]:
    entries: list[tuple[str, list[str]]] = []
    for root_name in ("config", "assets", "launch"):
        root = package_root / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                relative = path.relative_to(package_root)
                entries.append(
                    (f"share/{package_name}/{relative.parent}", [str(relative)])
                )
    return entries


setup(
    name=package_name,
    version="0.1.0",
    packages=[python_package]
    + [f"{python_package}.{subpackage}" for subpackage in subpackages],
    package_dir={python_package: "src"},
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            [f"resource/{package_name}"],
        ),
        (f"share/{package_name}", ["package.xml"]),
    ]
    + installed_resources(),
    install_requires=["setuptools", "typing_extensions"],
    zip_safe=True,
    maintainer="SO-101 maintainers",
    maintainer_email="zjumty@gmail.com",
    description="Unified SO-101 MuJoCo and Gazebo pick-place demonstration.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "pick_place = so101_demo.cli.pick_place:main",
            "run_qualification = so101_demo.cli.qualification:main",
            "scene_setup = so101_demo.cli.scene_setup:main",
            "gazebo_execute = so101_demo.backends.gazebo.execute:main",
            "gazebo_ready = so101_demo.cli.gazebo_ready:main",
            "coke_pose_subscriber = so101_demo.cli.coke_pose_subscriber:main",
            "camera_preset = so101_demo.cli.camera_preset:main",
            "teleop_reset = so101_demo.cli.teleop_reset:main",
            "teleop_workflow = so101_demo.cli.teleop_workflow:main",
        ]
    },
)
