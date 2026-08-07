from setuptools import find_packages, setup


package_name = "so101_gazebo_demo_py"


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/docs", ["docs/provenance.json"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="SO-101 maintainers",
    maintainer_email="maintainer@example.com",
    description="Standalone Python SO-101 Gazebo pick-place demonstration.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={"console_scripts": []},
)
