# The networked apt and pip steps live in the so101-campaign-shard-deps base (docker/campaign-shard-deps), pinned by ID in
# scripts/images/base-image-ids.json, so this build runs with --network none like the inference build.
#
# Three stages. `deps` is that base. `build` compiles the colcon closure in two layers: the rarely changing native packages
# first (third_party and so101_quik), then the packages that change with the code (so101_mujoco_support, so101_teleop,
# so101_demo_py). `final` is `deps` plus the complete read-only /act/source and the finished /act/install; it never contains
# the build tree.
#
# Same content for the same commit on every host (docs/superpowers/specs/2026-10-21-so101-image-content-identity-design.md):
# no .pyc is generated (PIP_NO_COMPILE, PYTHONDONTWRITEBYTECODE, no compileall), the C++ compiler maps the build paths, and
# the image build uses no ccache.
FROM so101-campaign-shard-deps:ros-jazzy-yolo11n-v1 AS deps

FROM deps AS build

ENV CCACHE_DISABLE=1 PYTHONHASHSEED=0 \
    PATH=/act/build-tools:/act/source/build-deps/node/bin:/act/venv/bin:/opt/ros/jazzy/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    SO101_TELEOP_BUN=/act/build-tools/bun \
    AMENT_PREFIX_PATH=/act/install:/opt/ros/jazzy

# Native layer: only the files the third_party packages and so101_quik compile from.
COPY source/third_party /act/build-source/third_party
COPY source/src/so101_quik /act/build-source/src/so101_quik
COPY source/build-deps/lodepng /act/source/build-deps/lodepng
RUN chmod -R a+rX,a-w /act/source
RUN /usr/bin/bash -c 'set -eo pipefail; source /opt/ros/jazzy/setup.bash; cd /act/build-source; \
    /act/venv/bin/python -m pytest --version; \
    /act/venv/bin/python -c '\''import json, pathlib; print("ROS_PACKAGE_READBACK=" + json.dumps(sorted(p.name for p in pathlib.Path("/opt/ros/jazzy/share").iterdir() if p.is_dir())))'\''; \
    /act/venv/bin/python -m colcon --log-base /act/build-log build --base-paths src third_party \
      --build-base /act/build --install-base /act/install --merge-install \
      --packages-select controller_manager hardware_interface_testing joint_state_broadcaster joint_trajectory_controller mujoco_3d_lidar mujoco_ros2_control mujoco_ros2_control_msgs mujoco_ros2_control_plugins so101_clock_test_hardware so101_queued_state_publisher so101_quik \
      --allow-overriding controller_manager hardware_interface_testing joint_state_broadcaster joint_trajectory_controller mujoco_ros2_control mujoco_ros2_control_msgs mujoco_ros2_control_plugins \
      --parallel-workers 4 --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON \
      -DCMAKE_C_FLAGS='\''-ffile-prefix-map=/act/build-source=/act/src -fdebug-prefix-map=/act/build-source=/act/src'\'' -DCMAKE_CXX_FLAGS='\''-ffile-prefix-map=/act/build-source=/act/src -fdebug-prefix-map=/act/build-source=/act/src'\'' -DCMAKE_C_COMPILER_LAUNCHER= -DCMAKE_CXX_COMPILER_LAUNCHER= \
      -DPython3_EXECUTABLE=/act/venv/bin/python -DPYTHON_EXECUTABLE=/act/venv/bin/python \
      -DFETCHCONTENT_SOURCE_DIR_LODEPNG=/act/source/build-deps/lodepng -DFETCHCONTENT_FULLY_DISCONNECTED=ON'
# rosidl_generator_c and rosidl_typesupport_introspection_c both write <msg>__type_support.c, and the install rule that should keep
# only the headers has no EXCLUDE, so both copies are installed and the one that finished generating last wins: a race between two
# builds of one commit. Nothing compiles the installed copies (the libraries come from the build tree). They are deleted right after
# the packages that install them, because so101_demo_py writes debug-provenance-manifest.json with a hash of every installed file.
RUN find /act/install/include -type f -name '*.c' -delete

# Code layer: the Bun toolchain first (stable), then the sources that change.
COPY source/src/so101_demo_py/docker/campaign-shard/build-bun.bash /act/build-tools/bun
COPY source/build-deps/bun /act/source/build-deps/bun
COPY source/build-deps/node /act/source/build-deps/node
COPY source/build-deps/bun-cache /act/build-source/build-deps/bun-cache
RUN chmod 0555 /act/build-tools/bun && chmod -R a+rX,a-w /act/source && chmod -R u+w /act/build-source/build-deps
COPY source/scripts /act/build-source/scripts
COPY source/src /act/build-source/src
RUN /usr/bin/bash -c 'set -eo pipefail; source /opt/ros/jazzy/setup.bash; source /act/install/local_setup.bash; cd /act/build-source; \
    /act/venv/bin/python -m pytest --version; \
    /act/venv/bin/python -m colcon --log-base /act/build-log build --base-paths src third_party \
      --build-base /act/build --install-base /act/install --merge-install \
      --packages-select so101_mujoco_support \
      --allow-overriding controller_manager hardware_interface_testing joint_state_broadcaster joint_trajectory_controller mujoco_ros2_control mujoco_ros2_control_msgs mujoco_ros2_control_plugins \
      --parallel-workers 4 --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON \
      -DCMAKE_C_FLAGS='\''-ffile-prefix-map=/act/build-source=/act/src -fdebug-prefix-map=/act/build-source=/act/src'\'' -DCMAKE_CXX_FLAGS='\''-ffile-prefix-map=/act/build-source=/act/src -fdebug-prefix-map=/act/build-source=/act/src'\'' -DCMAKE_C_COMPILER_LAUNCHER= -DCMAKE_CXX_COMPILER_LAUNCHER= \
      -DPython3_EXECUTABLE=/act/venv/bin/python -DPYTHON_EXECUTABLE=/act/venv/bin/python \
      -DFETCHCONTENT_SOURCE_DIR_LODEPNG=/act/source/build-deps/lodepng -DFETCHCONTENT_FULLY_DISCONNECTED=ON'
RUN find /act/install/include -type f -name '*.c' -delete
RUN /usr/bin/bash -c 'set -eo pipefail; source /opt/ros/jazzy/setup.bash; source /act/install/local_setup.bash; cd /act/build-source; \
    /act/venv/bin/python -m pytest --version; \
    /act/venv/bin/python -m colcon --log-base /act/build-log build --base-paths src third_party \
      --build-base /act/build --install-base /act/install --merge-install \
      --packages-select so101_teleop so101_demo_py \
      --allow-overriding controller_manager hardware_interface_testing joint_state_broadcaster joint_trajectory_controller mujoco_ros2_control mujoco_ros2_control_msgs mujoco_ros2_control_plugins \
      --parallel-workers 4 --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON \
      -DCMAKE_C_FLAGS='\''-ffile-prefix-map=/act/build-source=/act/src -fdebug-prefix-map=/act/build-source=/act/src'\'' -DCMAKE_CXX_FLAGS='\''-ffile-prefix-map=/act/build-source=/act/src -fdebug-prefix-map=/act/build-source=/act/src'\'' -DCMAKE_C_COMPILER_LAUNCHER= -DCMAKE_CXX_COMPILER_LAUNCHER= \
      -DPython3_EXECUTABLE=/act/venv/bin/python -DPYTHON_EXECUTABLE=/act/venv/bin/python \
      -DFETCHCONTENT_SOURCE_DIR_LODEPNG=/act/source/build-deps/lodepng -DFETCHCONTENT_FULLY_DISCONNECTED=ON'

FROM deps AS final

COPY source /act/source
RUN chmod -R a+rX,a-w /act/source
COPY --from=build /act/install /act/install

# The vendor ros2 console script selects system Python. Keep its exact installed
# body but bind this shard's copy to the frozen interpreter and inventory it.
RUN mkdir -p /act/install/bin \
    && /act/venv/bin/python -c 'from pathlib import Path; source=Path("/opt/ros/jazzy/bin/ros2").read_bytes(); assert source.startswith(b"#!"); body=source.split(b"\n",1)[1]; Path("/act/install/bin/ros2").write_bytes(b"#!/act/venv/bin/python\n"+body)' \
    && chmod 0555 /act/install/bin/ros2

# The NVIDIA container runtime injects libEGL_nvidia but not its glvnd vendor file; without it the simulator's EGL
# display (camera_plugin.cpp) lands on Mesa llvmpipe, i.e. CPU rendering. Outside /act, so no provenance hash covers it.
RUN mkdir -p /usr/share/glvnd/egl_vendor.d \
    && printf '%s\n' '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json \
    && chmod 0644 /usr/share/glvnd/egl_vendor.d/10_nvidia.json

ENV PATH=/act/venv/bin:/act/install/bin:/opt/ros/jazzy/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    AMENT_PREFIX_PATH=/act/install:/opt/ros/jazzy
COPY source/src/so101_demo_py/docker/campaign-inference/bootstrap.bash /act/bootstrap.bash
RUN chmod 0555 /act/bootstrap.bash && printf '%s\n' shard > /act/image-role \
    && chmod -R a+rX,a-w /act/install && chmod u+w /act/install/share \
    && /act/bootstrap.bash /act/venv/bin/python -B -I -c 'from so101_demo.runtime.container_campaign.provenance import write_build_freeze; write_build_freeze("shard")' \
    && chmod a-w /act/install/share /act/install/share/act-image-dependencies.json /act/provenance.json /act/image-role \
    && /act/bootstrap.bash /act/venv/bin/python -B -I -m so101_demo.runtime.container_campaign.provenance

WORKDIR /act
ENTRYPOINT ["/act/bootstrap.bash", "/act/venv/bin/python", "-I", "-m", "so101_demo.runtime.container_campaign.image_bootstrap"]
