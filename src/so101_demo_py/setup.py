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
    install_requires=["PyYAML==6.0.2", "setuptools", "typing_extensions"],
    zip_safe=True,
    maintainer="SO-101 maintainers",
    maintainer_email="zjumty@gmail.com",
    description="Unified SO-101 MuJoCo and Gazebo pick-place demonstration.",
    license="Apache-2.0",
    extras_require={"test": ["pytest"]},
    entry_points={
        "console_scripts": [
            "fixed_cup_pick_place = so101_demo.cli.fixed_cup_pick_place:main",
            "dynamic_cup_pick_place = so101_demo.cli.dynamic_cup_pick_place:main",
            "run_qualification = so101_demo.cli.qualification:main",
            "scene_setup = so101_demo.cli.scene_setup:main",
            "gazebo_execute = so101_demo.backends.gazebo.execute:main",
            "motion_stack_ready = so101_demo.cli.motion_stack_ready:main",
            "cup_pose_subscriber = so101_demo.cli.cup_pose_subscriber:main",
            "cup_pose_tf_demo = so101_demo.cli.cup_pose_tf_demo:main",
            "rgbd_point_cloud = so101_demo.cli.rgbd_point_cloud:main",
            "rgbd_cup_pose = so101_demo.cli.rgbd_cup_pose:main",
            "rgbd_object_pose = so101_demo.cli.rgbd_object_pose:main",
            "generate_yolo_seg_dataset = "
            "so101_demo.cli.generate_yolo_seg_dataset:main",
            "prepare_grounding_dino_dataset = "
            "so101_demo.cli.prepare_grounding_dino_dataset:main",
            "train_grounding_dino = so101_demo.cli.train_grounding_dino:main",
            "train_grounding_dino_domain_retention = "
            "so101_demo.cli.train_grounding_dino_domain_retention:main",
            "verify_grounding_dino_checkpoint = "
            "so101_demo.cli.verify_grounding_dino_checkpoint:main",
            "revalidate_grounding_dino_checkpoint = "
            "so101_demo.cli.revalidate_grounding_dino_checkpoint:main",
            "evaluate_grounded_sam_frozen_candidate = "
            "so101_demo.cli.evaluate_grounded_sam_frozen_candidate:main",
            "grounded_sam_val_calibration = "
            "so101_demo.cli.grounded_sam_val_calibration:main",
            "train_yolo_seg = so101_demo.cli.train_yolo_seg:main",
            "rgbd_sensor_capture = so101_demo.cli.rgbd_sensor_capture:main",
            "so101_mujoco_perception_pick_place = "
            "so101_demo.cli.perception_pick_place_launch:main",
            "camera_preset = so101_demo.cli.camera_preset:main",
            "teleop_reset = so101_demo.cli.teleop_reset:main",
            "teleop_workflow = so101_demo.cli.teleop_workflow:main",
            "task_reachability = so101_demo.cli.task_reachability:main",
            "so101_mujoco_rgbd_batch = so101_demo.cli.mujoco_rgbd_batch:main",
            "text_pick_agent = so101_demo.cli.text_pick_agent:main",
            "prepare_grounded_sam_bundle = "
            "so101_demo.cli.prepare_grounded_sam_bundle:main",
            "perception_benchmark = so101_demo.cli.perception_benchmark:main",
        ]
    },
)
