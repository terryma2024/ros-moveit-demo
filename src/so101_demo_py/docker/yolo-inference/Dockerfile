FROM docker.m.daocloud.io/library/ros:jazzy-ros-base-noble@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4

LABEL org.opencontainers.image.title="SO-101 YOLO11n-Seg inference" \
      org.opencontainers.image.description="Pinned ROS 2 Jazzy CUDA inference environment for SO-101 YOLO11n-Seg" \
      org.opencontainers.image.source="https://gitee.com/zjumty/robot-demo-001"

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    YOLO_OFFLINE=true \
    YOLO_CONFIG_DIR=/opt/ultralytics \
    TORCH_HOME=/opt/torch-cache

RUN --mount=type=cache,id=so101-yolo-inference-apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=so101-yolo-inference-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
        fonts-dejavu-core \
        libgl1 \
        libglib2.0-0 \
        python3-pip \
        python3-venv \
        ros-jazzy-vision-msgs \
    && python3 -m venv --system-site-packages /opt/venv

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu130

# Preinstall PyTorch's ordinary Python dependencies from the primary mirror.
# pip does not otherwise prioritize --index-url over --extra-index-url.
RUN --mount=type=cache,id=so101-pip-py312-cu130,target=/root/.cache/pip,sharing=locked \
    python -m pip install --retries 10 \
        --index-url "${PIP_INDEX_URL}" \
        cuda-bindings==13.3.1 \
        cuda-pathfinder==1.8.0 \
        filelock==3.32.5 \
        fsspec==2026.7.0 \
        Jinja2==3.1.6 \
        MarkupSafe==3.0.3 \
        mpmath==1.3.0 \
        networkx==3.6.1 \
        numpy==1.26.4 \
        Pillow==12.3.0 \
        setuptools==84.0.0 \
        sympy==1.14.0 \
        typing_extensions==4.16.0

RUN --mount=type=cache,id=so101-pip-py312-cu130,target=/root/.cache/pip,sharing=locked \
    python -m pip install --retries 10 \
        --index-url "${PIP_INDEX_URL}" \
        --extra-index-url "${PYTORCH_INDEX_URL}" \
        torch==2.13.0+cu130 torchvision==0.28.0+cu130

COPY src/so101_demo_py/config/perception/inference-requirements.lock \
    /tmp/inference-requirements.lock

RUN --mount=type=cache,id=so101-pip-py312-cu130,target=/root/.cache/pip,sharing=locked \
    python -m pip install --retries 10 \
        --index-url "${PIP_INDEX_URL}" \
        --requirement /tmp/inference-requirements.lock

COPY src/so101_demo_py /opt/so101_demo_py

RUN python -m pip install --no-cache-dir --no-deps /opt/so101_demo_py \
    && install -d -m 1777 /opt/ultralytics /opt/torch-cache \
    && install -m 0644 \
        /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf \
        /opt/ultralytics/Arial.ttf \
    && /ros_entrypoint.sh python -c 'import open3d, rclpy, torch, torchvision, ultralytics; from vision_msgs.msg import Detection2DArray; assert open3d.__version__ == "0.19.0"; assert torch.__version__ == "2.13.0+cu130"; assert torchvision.__version__ == "0.28.0+cu130"; assert ultralytics.__version__ == "8.4.115"'

WORKDIR /evidence

ENTRYPOINT ["/ros_entrypoint.sh", "rgbd_object_pose"]
