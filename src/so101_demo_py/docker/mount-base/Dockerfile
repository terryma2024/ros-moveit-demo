# Dependency-only image for running the host-built install tree: ROS, apt, torch and the pip set, no project code. The host's
# `install` tree is bind-mounted read-only at SO101_MOUNT_INSTALL (docs/superpowers/specs/2026-10-21-so101-mount-build-images-design.md).
#
# The apt versions are those of the build host (apt-pins.txt: scripts/env/apt_pins.py generate, from `image_env.py capture-host` and the
# package set of the previous image); a version the mirrors no longer offer is not pinned and apt takes the candidate (listed in
# progress-mount-images.md). Built once and pinned by ID. It reaches the network for apt (Tsinghua mirrors, current versions) and pip (Tsinghua PyPI, the PyTorch
# index for the CUDA wheels). Nothing under /act, /opt/venv or any site-packages is named so101_*: a test enforces it.
# No .pyc of our own: PIP_NO_COMPILE, PYTHONDONTWRITEBYTECODE, the ones apt's package scripts compile and the ones `python3 -m venv` (ensurepip)
# compiles for each venv's pip are removed in the same layer. The pyc of the upstream ROS image stay.
FROM docker.m.daocloud.io/library/ros:jazzy-ros-base-noble@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4

LABEL org.opencontainers.image.title="SO-101 mount base" \
      org.opencontainers.image.description="ROS 2 Jazzy CUDA runtime dependencies for the host-built SO-101 install tree"

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_COMPILE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 SOURCE_DATE_EPOCH=1704067200 PYTHONNOUSERSITE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 YOLO_OFFLINE=true \
    YOLO_CONFIG_DIR=/opt/ultralytics TORCH_HOME=/opt/torch-cache

COPY apt-packages.txt apt-pins.txt pip-requirements.lock inference-requirements.lock /tmp/mount-base/

RUN find / -xdev -name '*.pyc' | sort > /tmp/mount-base/pyc.before \
    && sed -i -e 's|http://packages.ros.org/ros2/ubuntu|http://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu|' -e 's|^Types: deb deb-src$|Types: deb|' /etc/apt/sources.list.d/ros2.sources \
    && sed -i -e 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.tuna.tsinghua.edu.cn/ubuntu/|' -e 's|http://security.ubuntu.com/ubuntu/|http://mirrors.tuna.tsinghua.edu.cn/ubuntu/|' /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get update \
    && apt-get install --yes --no-install-recommends --allow-downgrades fonts-dejavu-core libgl1 libglib2.0-0 python3-pip python3-venv ros-jazzy-vision-msgs \
         $(grep -v '^#' /tmp/mount-base/apt-packages.txt) $(cat /tmp/mount-base/apt-pins.txt) \
    && find / -xdev -name '*.pyc' | sort | comm -13 /tmp/mount-base/pyc.before - | xargs -r rm -f \
    && find / -xdev -type d -name __pycache__ -empty -delete \
    && rm -rf /var/lib/apt/lists/*

# /opt/venv: PyTorch and the perception requirements. The ordinary dependencies of PyTorch come from the primary mirror first, because pip
# does not prioritise --index-url over --extra-index-url.
RUN python3 -m venv --system-site-packages /opt/venv \
    && /opt/venv/bin/python -m pip install --no-compile --retries 10 --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
        cuda-bindings==13.3.1 cuda-pathfinder==1.8.0 filelock==3.32.5 fsspec==2026.7.0 Jinja2==3.1.6 MarkupSafe==3.0.3 mpmath==1.3.0 \
        networkx==3.6.1 numpy==1.26.4 Pillow==12.3.0 setuptools==84.0.0 sympy==1.14.0 typing_extensions==4.16.0 \
    && /opt/venv/bin/python -m pip install --no-compile --retries 10 --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
        --extra-index-url https://download.pytorch.org/whl/cu130 torch==2.13.0+cu130 torchvision==0.28.0+cu130 \
    && /opt/venv/bin/python -m pip install --no-compile --retries 10 --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
        --requirement /tmp/mount-base/inference-requirements.lock \
    && install -d -m 1777 /opt/ultralytics /opt/torch-cache \
    && install -m 0644 /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf /opt/ultralytics/Arial.ttf \
    && /usr/bin/bash -c 'source /opt/ros/jazzy/setup.bash && /opt/venv/bin/python -B -c "import open3d, rclpy, torch, torchvision, ultralytics; from vision_msgs.msg import Detection2DArray; assert open3d.__version__ == \"0.19.0\"; assert torch.__version__ == \"2.13.0+cu130\"; assert torchvision.__version__ == \"0.28.0+cu130\"; assert ultralytics.__version__ == \"8.4.115\""' \
    && find /opt/venv -type d -name __pycache__ -prune -exec rm -rf {} +

# /act/venv: the interpreter of the host-built console scripts' environment. Its .pth puts the mounted tree's site-packages first when
# SO101_MOUNT_INSTALL is set, then ROS, then /opt/venv.
RUN python3 -m venv --system-site-packages /act/venv \
    && printf '%s\n' 'import glob, os, sys; mount = os.environ.get("SO101_MOUNT_INSTALL"); sys.path[:0] = (sorted(glob.glob(mount + "/*/lib/python3.12/site-packages")) if mount else []) + ["/opt/ros/jazzy/lib/python3.12/site-packages", "/opt/venv/lib/python3.12/site-packages"]' \
       > /act/venv/lib/python3.12/site-packages/act-runtime.pth \
    && /act/venv/bin/python -m pip install --no-compile --no-deps --require-hashes --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r /tmp/mount-base/pip-requirements.lock \
    && find /act/venv -type d -name __pycache__ -prune -exec rm -rf {} + \
    && rm -rf /tmp/mount-base /root/.cache

# The NVIDIA container runtime injects libEGL_nvidia but not its glvnd vendor file; without it EGL lands on Mesa llvmpipe (CPU rendering).
RUN mkdir -p /usr/share/glvnd/egl_vendor.d \
    && printf '%s\n' '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json \
    && chmod 0644 /usr/share/glvnd/egl_vendor.d/10_nvidia.json

COPY bootstrap.bash /act/bootstrap.bash
COPY check-mount-commit.bash /act/check-mount-commit.bash
RUN chmod 0555 /act/bootstrap.bash /act/check-mount-commit.bash

WORKDIR /act
ENTRYPOINT ["/act/bootstrap.bash"]
