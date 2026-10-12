# The coordinator verifies the cached base ID and resulting layer ancestry.
# Expected ID: sha256:5998505c1debdd1a3410ed6bd1aec8796ef3f82e3b3dc403bbc992423b6304fd.
FROM so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 YOLO_OFFLINE=true
RUN apt-get update && apt-get install --yes --no-install-recommends \
    build-essential cmake python3-dev python3-venv python3-colcon-common-extensions \
    libboost-all-dev libeigen3-dev libfmt-dev libglfw3-dev libegl1-mesa-dev libtinyxml2-dev \
    ros-jazzy-moveit ros-jazzy-moveit-configs-utils ros-jazzy-ros2-control ros-jazzy-ros2-controllers \
    ros-jazzy-control-toolbox ros-jazzy-mujoco-vendor ros-jazzy-backward-ros \
    ros-jazzy-ros-gz-interfaces ros-jazzy-tf2-geometry-msgs ros-jazzy-vision-msgs
RUN apt-get install --yes --no-install-recommends \
    ros-jazzy-ros2-control-cmake ros-jazzy-ros2-control-test-assets \
    ros-jazzy-example-interfaces ros-jazzy-launch-testing-ros
RUN python3 -m venv --system-site-packages /act/venv \
    && printf '%s\n' 'import sys; sys.path[:0] = ["/act/install/lib/python3.12/site-packages", "/act/install/local/lib/python3.12/dist-packages", "/opt/ros/jazzy/lib/python3.12/site-packages", "/opt/venv/lib/python3.12/site-packages"]' \
       > /act/venv/lib/python3.12/site-packages/act-runtime.pth \
    && NO_PROXY="${NO_PROXY:+$NO_PROXY,}pypi.tuna.tsinghua.edu.cn" no_proxy="${no_proxy:+$no_proxy,}pypi.tuna.tsinghua.edu.cn" \
       /act/venv/bin/python -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple pydantic==2.14.1 mujoco==3.4.0 colcon-override-check==0.0.1

COPY source /act/source
RUN chmod -R a+rX,a-w /act/source \
    && cp -a /act/source /act/build-source && chmod -R u+w /act/build-source \
    && mkdir -p /act/build-tools
COPY source/src/so101_demo_py/docker/campaign-shard/build-bun.bash /act/build-tools/bun
RUN chmod 0555 /act/build-tools/bun
ENV PATH=/act/build-tools:/act/source/build-deps/node/bin:/act/venv/bin:/opt/ros/jazzy/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    SO101_TELEOP_BUN=/act/build-tools/bun \
    AMENT_PREFIX_PATH=/act/install:/opt/ros/jazzy
RUN /usr/bin/bash -c 'set -eo pipefail; source /opt/ros/jazzy/setup.bash; cd /act/build-source; \
    /act/venv/bin/python -c '\''import json, pathlib; print("ROS_PACKAGE_READBACK=" + json.dumps(sorted(p.name for p in pathlib.Path("/opt/ros/jazzy/share").iterdir() if p.is_dir())))'\''; \
    /act/venv/bin/python -m colcon --log-base /act/build-log build --base-paths src third_party \
      --build-base /act/build --install-base /act/install --merge-install --packages-up-to so101_demo_py \
      --allow-overriding controller_manager hardware_interface_testing mujoco_ros2_control mujoco_ros2_control_msgs mujoco_ros2_control_plugins \
      --parallel-workers 4 --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON \
      -DPython3_EXECUTABLE=/act/venv/bin/python -DPYTHON_EXECUTABLE=/act/venv/bin/python \
      -DFETCHCONTENT_SOURCE_DIR_LODEPNG=/act/source/build-deps/lodepng -DFETCHCONTENT_FULLY_DISCONNECTED=ON'

COPY source/src/so101_demo_py/docker/campaign-inference/bootstrap.bash /act/bootstrap.bash
RUN chmod 0555 /act/bootstrap.bash && printf '%s\n' shard > /act/image-role \
    && chmod -R a+rX,a-w /act/install && chmod u+w /act/install/share \
    && /act/bootstrap.bash /act/venv/bin/python -I -c 'from so101_demo.runtime.container_campaign.provenance import write_build_freeze; write_build_freeze("shard")' \
    && chmod a-w /act/install/share /act/install/share/act-image-dependencies.json /act/provenance.json /act/image-role \
    && /act/bootstrap.bash /act/venv/bin/python -I -m so101_demo.runtime.container_campaign.provenance

ENV PATH=/act/venv/bin:/act/install/bin:/opt/ros/jazzy/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
WORKDIR /act
ENTRYPOINT ["/act/bootstrap.bash", "/act/venv/bin/python", "-I", "-m", "so101_demo.runtime.container_campaign.image_bootstrap"]
