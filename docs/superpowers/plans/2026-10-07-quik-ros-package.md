# QuIK ROS 2 package implementation plan

> For agentic workers: use `superpowers:executing-plans` inline in the existing task worktree. The user approved the complete design and this execution scope with `ok`; do not delegate or ask for the same approval again.

**Goal:** Install QuIK as one independent ROS 2 package and make `so101_demo_py` a declared consumer.

**Architecture:** `so101_quik` builds one frozen C++ core and exposes it through `so101_quik::core` and a Python standard-library loader. The demo keeps its URDF conversion, canonical FK, acceptance checks and backend selection. The official setup builds the two distributions in dependency order.

**Tech stack:** ROS 2 Jazzy, ament_cmake, ament_cmake_python, C++17, Eigen 3.4.0, ctypes, setuptools 79.0.1, wheel 0.45.1, CMake 3.31.6.

**Spec:** `docs/superpowers/specs/2026-10-07-quik-ros-package-design.md`.

## Global constraints

- Worktree: `/Users/matianyi/.codex/worktrees/0a4f/moveit-demo`; branch `codex/prepare-horizon-ik-20261004-01a10735`.
- Registered evidence root: `/opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735`; this phase uses its `quik-ros-package-01` child.
- Frozen source HEAD: `38e333507127a8073061811a7b08a02e41cbe7d1`.
- QuIK `a9ebd1f21dfd3c9f0869140dfb0a4ae5a538cccc`, orientation weight `0.08`, Eigen `3.4.0`, unchanged vendor bytes and solver settings.
- Flags: `-O3 -DNDEBUG -fno-fast-math -ffp-contract=off -std=c++17`; no native solver changes.
- Gates: position `0.002 m`, orientation `0.10 rad`, joint margin `0.002 rad`; default backend `native`.
- Package version `0.1.0`; C++ target `so101_quik::core`; `load_native_library() -> tuple[ctypes.CDLL, pathlib.Path]`.
- NumPy remains `1.26.4` on Linux and `2.4.6` on macOS; other approved bootstrap pins remain unchanged.
- No shared checkout/runtime writes, simulator launch, remote messages or evidence deletion.
- Same-platform per-backend 64 requests, 20 full horizon documents and 2003 QuIK FK matrices must match exactly. Known QuIK P18/P19 failures remain part of the baseline.
- Mac ordinary test interpreter `/opt/ros/jazzy/.venv/bin/python`; full Python scopes run separately with `min(8, logical CPUs)` workers. No `benchmark_test/` collection.
- Linux comparison uses CPU14 with SMT15 idle, 3 AB/3 BA pairs per backend, 6 fresh processes per version, 20 points and 3 timed repeats. Median and p95 ratios must each be at most `1.05`.

## Task 1: Independent package and installed consumers

Files: create `src/so101_quik/{CMakeLists.txt,package.xml,setup.py,pyproject.toml,MANIFEST.in}`, `cmake/`, `include/so101_quik/c_api.h`, `src/quik_c_api.cpp`, `so101_quik/__init__.py`, `test/test_native_library.py`, `test/test_cpp_api.cpp`. Move demo's `third_party/quik/` and `config/ik/quik.lock.json` into this package.

Consumes: the existing four C ABI functions, their 5-joint arrays, weighted solver header and existing lock. Produces: a Python loader with typed symbols, independent shared library, installed C++ target and standalone wheel built from the same CMake target.

- [x] Add a failing behavior test that imports the new installed package inside the test body, loads the library, creates a planar 5-joint chain and verifies literal FK results. Missing package is an assertion failure after collection, not an environment RED.
- [x] Save the directed fixed-interpreter RED command, exit and JUnit under this phase.
- [x] Move frozen files, verify every vendor SHA against the prior lock, and split only the CPython module shell from the existing C++ wrapper.
- [x] Implement source-hash verification and exact Eigen lookup in CMake. Export the target and headers. Install an identical core copy as Python data; use a fixed `@rpath` identity on macOS so install does not alter its bytes.
- [x] Add the standard-library loader, deterministic package-relative path and explicit ImportError for absent or unloadable artifacts.
- [x] Build a task-private CMake/Eigen tool prefix, compile/install only the new package, and rerun the behavior test GREEN.
- [x] Verify a nonzero pose solve and distinct context geometry. Run Python with `-S` and only the new installed package on its path to prove that neither demo nor NumPy is needed.
- [x] Compile and run an installed-target C++ consumer using the same hand-checked FK/solve inputs. Register the C++ behavior test in CTest.

Behavior fixture (independent literal oracle):

```python
dh = (ctypes.c_double * 20)(0.1, 0, 0, 0, 0.2, 0, 0, 0,
                           0.1, 0, 0, 0, 0.1, 0, 0, 0, 0.1, 0, 0, 0)
identity = (ctypes.c_double * 16)(1, 0, 0, 0, 0, 1, 0, 0,
                                 0, 0, 1, 0, 0, 0, 0, 1)
q = (ctypes.c_double * 5)(0, 0, 0, 0, math.pi / 2)
expected = (0, -1, 0, 0.5, 1, 0, 0, 0.1,
            0, 0, 1, 0, 0, 0, 0, 1)
context = library.quik_create(dh, identity, identity, 0)
output = (ctypes.c_double * 16)()
try:
    assert context
    assert library.quik_fk(context, q, output) == 0
    assert tuple(output) == pytest.approx(expected, abs=1e-12)
finally:
    library.quik_destroy(context)
```

## Task 2: Demo dependency and factory integration

Files: modify `src/so101_demo_py/{package.xml,setup.py,src/control/moveit/quik_ik.py,test/test_pose_ik_backends.py}`; remove the old `_quik_native.cpp` after its code has migrated.

Consumes: `so101_quik.load_native_library()`. Produces: the unchanged public pose IK interface with an actual external package/library path.

- [x] Change the missing-backend test to mask `so101_quik` and run it against the existing installed baseline. It must fail because the old adapter still succeeds through its embedded extension.
- [x] Add the package dependency and pinned Python distribution requirement; remove QuIK compilation and vendor installation from demo setup.
- [x] Change only the constructor's loading/type-binding boundary to `self._library, self._artifact = load_native_library()`. Keep context creation, finalizer, lock, geometry, solve, normalization and canonical gates as they are.
- [x] Catch explicit loading errors under `QUIK_BACKEND_UNAVAILABLE`; retain all numerical failure behavior and no-fallback semantics.
- [x] Build both packages into a new private ROS overlay and verify dependency order, package prefix, module path, library path and identical library copies.
- [x] Run the backend directed tests and installed Mac behavior capture against EXP-050. Reject any numerical drift before continuing.

RED assertion:

```python
monkeypatch.setitem(sys.modules, "so101_quik", None)
with pytest.raises(UnderactuatedIkError, match="^QUIK_BACKEND_UNAVAILABLE:"):
    _solver("quik")
```

## Task 3: Formal setup for two packages

Files: modify `scripts/{setup-so101-quik.sh,so101_quik_setup.py,so101-quik-bootstrap.lock.env}`, `src/so101_demo_py/test/test_quik_setup.py`, `docs/guides/so101-ik-backend-selection.md`; add an English `src/so101_quik/README.md` and update the ledger.

Consumes: the new package's standalone CMake target/wheel and the existing pinned bootstrap. Produces: first/repeat setup, complete two-package source fingerprints and installed-artifact verification, with Eigen3_DIR for ROS builds.

- [x] Add a failing setup fingerprint test: create a complete tiny two-package source tree, fingerprint it, change the new package's C++ source, and require the fingerprint to change. The old helper ignores this package and must fail.
- [x] Add pinned CMake to the private dependencies, install private Eigen CMake metadata, and copy the new package without writing into the caller's checkout.
- [x] Build/install the QuIK wheel first and the demo wheel second, run dependency checks and verify both actual installed solvers. Fingerprint both packages, all relevant bootstrap inputs, new C++ artifacts and private dependency trees.
- [x] Write build-env.sh with Eigen3_DIR and retain the setup's prefix/transport/archive/integrity contracts.
- [x] Run directed setup regressions, then actual first/repeat setup in a new Mac prefix and a new bare Ubuntu 24.04 container. Verify failed SHA/version/library cases and successful restored readback.
- [x] Update usage commands to build both packages in dependency order and document C++/Python consumers and retained backend limitations.

Fingerprint regression:

```python
first = helper().source_inputs(repo)
(repo / "src/so101_quik/src/quik_c_api.cpp").write_text("changed core input")
second = helper().source_inputs(repo)
assert first != second
```

## Task 4: Numerical, package and latency acceptance

Evidence scripts live under `quik-ros-package-01`; they do not become product runtime dependencies.

- [x] Confirm every imported artifact belongs to the declared private overlay, and that frozen numerical/vendor/input hashes still match.
- [x] Compare complete Mac 64-request, 20-point and 2003-FK outputs exactly. Recompute accepted canonical geometric gates.
- [x] Run the entire demo ordinary test directory and the new package's Python test directory separately with xdist8 on this Mac, fresh short NVMe scratch, exact fixed ROS Python, JUnit and worker proofs. Run new-package CTest and `colcon test-result`.
- [x] Build before/after ROS overlays on ai-station without changing old checkouts or source. Verify installed C++ and Python consumers.
- [x] Establish before/after Linux behavior with the same fixed runtime and inputs, then run all 24 predeclared isolated-P-core comparison processes. Validate all documents and the <=1.05 median/p95 contract, and restore CPU/governor/cgroup state.
- [x] Transfer all remote records without dereferencing special files, verify archive paths/hashes/sizes/symlinks and retain invalid attempts.
- [x] Finish inline implementation review and write acceptance, provenance, retention and ledger checkpoint.
- [x] Commit and push the authorized current Gitee branch with standard Git, then verify remote SHA and clean local worktree.

ROS build boundary:

```zsh
colcon build --base-paths src/so101_quik src/so101_demo_py \
  --packages-up-to so101_demo_py \
  --build-base "$phase/build" --install-base "$phase/install" \
  --cmake-args -DPython3_EXECUTABLE=/opt/ros/jazzy/.venv/bin/python
```

The actual runner supplies a task-owned absolute `phase`, complete validated underlays and the private pinned CMake/Eigen environment. Direct tests and formal gates record actual executable, prefix, worker count and exit separately.
