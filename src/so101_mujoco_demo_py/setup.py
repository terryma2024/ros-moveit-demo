from pathlib import Path

from setuptools import find_packages, setup

package_name = "so101_mujoco_demo_py"
package_root = Path(__file__).resolve().parent


def installed_model_assets() -> list[tuple[str, list[str]]]:
    entries: list[tuple[str, list[str]]] = []
    for directory in ("config", "launch", "mjcf", "urdf"):
        for path in sorted((package_root / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                relative = path.relative_to(package_root)
                entries.append((f"share/{package_name}/{relative.parent}", [str(relative)]))
    return entries


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            [f"resource/{package_name}"],
        ),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/docs", ["docs/provenance.json"]),
    ]
    + installed_model_assets(),
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="SO-101 maintainers",
    maintainer_email="maintainer@example.com",
    description="Independent Python SO-101 MuJoCo pick-place demonstration.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={"console_scripts": ["pick_place_state_machine = so101_mujoco_demo_py.cli:main"]},
)
