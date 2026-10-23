"""Standalone wheel around the same CMake target used by the ROS package."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext
from wheel.bdist_wheel import bdist_wheel


class CMakeBuild(build_ext):
    def build_extension(self, ext):
        source = Path(__file__).resolve().parent
        build = Path(self.build_temp).resolve() / "core"
        build.mkdir(parents=True, exist_ok=True)
        command = ["cmake", "-S", str(source), "-B", str(build),
                   "-DSO101_QUIK_STANDALONE=ON", "-DBUILD_TESTING=OFF",
                   "-DCMAKE_BUILD_TYPE=Release", f"-DPython3_EXECUTABLE={sys.executable}"]
        if os.environ.get("Eigen3_DIR"):
            command.append("-DEigen3_DIR=" + os.environ["Eigen3_DIR"])
        subprocess.run(command, check=True)
        subprocess.run(["cmake", "--build", str(build), "--target", "so101_quik_core",
                        "--parallel", "2"], check=True)
        suffix = ".dylib" if sys.platform == "darwin" else ".so"
        output = Path(self.build_lib) / "so101_quik/lib"
        output.mkdir(parents=True, exist_ok=True)
        shutil.copy2(build / "lib" / ("libso101_quik_core" + suffix), output)


class CAbiWheel(bdist_wheel):
    def get_tag(self):
        _, _, platform = super().get_tag()
        return "py3", "none", platform


setup(
    name="so101-quik",
    version="0.1.0",
    description="Frozen weighted QuIK CPU library with C++ and Python interfaces.",
    packages=["so101_quik"],
    python_requires=">=3.10",
    ext_modules=[Extension("so101_quik._core", sources=[])],
    cmdclass={"build_ext": CMakeBuild, "bdist_wheel": CAbiWheel},
    package_data={"so101_quik": ["lib/*"]},
    data_files=[("share/so101_quik/config", ["config/quik.lock.json"]),
                ("share/so101_quik/third_party/quik", ["third_party/quik/LICENSE",
                  "third_party/quik/NOTICE", "third_party/quik/upstream-package.xml"])],
    license="AGPL-3.0-only",
    license_files=["third_party/quik/LICENSE", "third_party/quik/NOTICE"],
    maintainer="SO-101 maintainers",
    maintainer_email="zjumty@gmail.com",
    extras_require={"test": ["pytest", "pytest-xdist==3.8.0"]},
    zip_safe=False,
)
