from pathlib import Path

from setuptools import find_packages, setup


package_name = "so101_gazebo_demo_py"


def installed_assets() -> list[tuple[str, list[str]]]:
    entries: list[tuple[str, list[str]]] = []
    for directory in ("config", "urdf", "meshes", "worlds", "rviz"):
        for path in sorted(Path(directory).rglob("*")):
            if path.is_file():
                destination = f"share/{package_name}/{path.parent}"
                entries.append((destination, [str(path)]))
    return entries


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/docs", ["docs/provenance.json"]),
    ] + installed_assets(),
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="SO-101 maintainers",
    maintainer_email="maintainer@example.com",
    description="Standalone Python SO-101 Gazebo pick-place demonstration.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={"console_scripts": []},
)
