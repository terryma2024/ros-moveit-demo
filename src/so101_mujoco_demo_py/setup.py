from pathlib import Path

from setuptools import setup


package_name = "so101_mujoco_demo_py"
package_root = Path(__file__).resolve().parent


def launch_files() -> list[str]:
    return [str(path.relative_to(package_root)) for path in sorted((package_root / "launch").glob("*.launch.py"))]


setup(
    name=package_name,
    version="0.2.0",
    packages=[package_name],
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
            "pick_place_state_machine = so101_mujoco_demo_py.forwarder:main",
            "run_qualification = so101_mujoco_demo_py.forwarder:qualification_main",
            "scene_setup = so101_mujoco_demo_py.forwarder:scene_setup_main",
            "analyze_contact_calibration = so101_mujoco_demo_py.forwarder:unsupported_main",
            "camera_preset = so101_mujoco_demo_py.forwarder:unsupported_main",
            "collect_contact_calibration = so101_mujoco_demo_py.forwarder:unsupported_main",
            "headless_execution = so101_mujoco_demo_py.forwarder:unsupported_main",
            "staged_approach = so101_mujoco_demo_py.forwarder:unsupported_main",
            "summarize_full_restart_baseline = so101_mujoco_demo_py.forwarder:unsupported_main",
            "teleop_reset = so101_mujoco_demo_py.forwarder:unsupported_main",
            "teleop_workflow = so101_mujoco_demo_py.forwarder:unsupported_main",
        ]
    },
)
