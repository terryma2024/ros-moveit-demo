# so101_quik

This ROS 2 package builds the frozen weighted QuIK CPU solver as one shared
library. It provides a CMake target for C++ and a Python loader for the same C ABI.
It has no dependency on `so101_demo_py`, ROS nodes or NumPy at runtime.

## Build

From the repository root, prepare the pinned dependencies and source the normal
ROS underlays:

```bash
bash scripts/setup-so101-quik.sh --prefix "$HOME/.local/share/so101-quik"
source "$HOME/.local/share/so101-quik/build-env.sh"
colcon build --packages-select so101_quik
source install/local_setup.bash
```

Use the setup's `--python` option when preparing dependencies for an existing ROS
Python. On macOS, source the `.zsh` overlays and use the project's fixed ROS
interpreter. Build the demo and this dependency together with
`colcon build --packages-up-to so101_demo_py`.

The ROS build needs CMake 3.22 or newer, C++17, `ament_cmake`,
`ament_cmake_python` and exactly Eigen 3.4.0. The official setup pins CMake 3.31.6
and installs Eigen's CMake configuration privately. Every vendored source hash
and all numerical compiler flags come from `config/quik.lock.json`.

## C++ consumer

```cmake
find_package(so101_quik 0.1.0 EXACT REQUIRED CONFIG)
add_executable(my_solver main.cpp)
target_link_libraries(my_solver PRIVATE so101_quik::core)
```

Include `<so101_quik/c_api.h>` in `main.cpp`. The package also installs the QuIK
C++ headers under its exported include directory. Downstream ROS packages declare
`<depend version_eq="0.1.0">so101_quik</depend>` in `package.xml`.

## Python consumer

```python
import ctypes
from so101_quik import load_native_library

library, artifact = load_native_library()
dh = (ctypes.c_double * 20)(
    .1, 0, 0, 0, .2, 0, 0, 0, .1, 0, 0, 0,
    .1, 0, 0, 0, .1, 0, 0, 0)
identity = (ctypes.c_double * 16)(
    1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
context = library.quik_create(dh, identity, identity, 0)
if not context:
    raise RuntimeError("QuIK context creation failed")
try:
    q = (ctypes.c_double * 5)()
    transform = (ctypes.c_double * 16)()
    if library.quik_fk(context, q, transform) != 0:
        raise RuntimeError("QuIK FK failed")
    print(artifact, transform[3])  # TCP x = 0.6 m for this planar fixture
finally:
    library.quik_destroy(context)
```

DH contains five `[a, alpha, d, theta]` rows. Transforms contain 16 doubles in
row-major order; joint vectors contain five doubles. `quik_solve` additionally
writes six residuals and one integer each for iterations and termination reason.
The caller keeps buffers valid, serializes calls on each context and destroys it
once. Different contexts own their geometry independently.

The raw library reports numerical results. Robot-specific limits and acceptance
tolerances belong to the consumer. The demo retains its 2 mm position, 0.10 rad
orientation and 0.002 rad joint-margin checks. Its public backend interface and
default `native` selection remain available.

The frozen weighted profile uses orientation weight `0.08`. Existing 20-point
qualification passes 18/20 with QuIK; P18 and P19 remain rejected. This package
extraction does not extend that qualification to physical grasps.

## Standalone installation and tests

The formal setup builds a platform wheel from the same CMake library target and
installs `so101-quik==0.1.0` before the demo. Its Python package contains the shared
library as data, so loading it does not require a CPython extension ABI.
Missing or corrupt library data raises `QUIK_LIBRARY_UNAVAILABLE` explicitly.

The ROS package registers C++ FK/IK tests and its full Python scope in CTest.
Python tests run with `min(8, logical CPUs)` workers. For project verification,
use the fixed ROS Python, the installed overlay and a fresh NVMe `TMPDIR`.

QuIK and this C++ bridge retain AGPL-3.0-only licensing. See
`third_party/quik/LICENSE` and `NOTICE`. The notice is preserved byte for byte;
its historical `config/ik/quik.lock.json` reference now lives at
`config/quik.lock.json` in this package.
