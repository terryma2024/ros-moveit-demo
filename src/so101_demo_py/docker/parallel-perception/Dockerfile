FROM docker.m.daocloud.io/library/ros:jazzy-ros-base-noble@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4

ENV DEBIAN_FRONTEND=noninteractive PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 YOLO_OFFLINE=true \
    YOLO_CONFIG_DIR=/tmp/ultralytics TORCH_HOME=/tmp/torch HF_HOME=/tmp/huggingface

RUN --mount=type=cache,id=so101-yolo-inference-apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=so101-yolo-inference-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install --yes --no-install-recommends \
        libgl1 libglib2.0-0 python3-pip python3-venv \
    && python3 -m venv --system-site-packages /opt/venv

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu130
RUN --mount=type=cache,id=so101-pip-py312-cu130,target=/root/.cache/pip,sharing=locked \
    python -m pip install --retries 10 --index-url "${PIP_INDEX_URL}" \
        --extra-index-url "${PYTORCH_INDEX_URL}" \
        torch==2.13.0+cu130 torchvision==0.28.0+cu130 \
        ultralytics==8.4.115 transformers==4.56.2 scipy==1.17.1 \
        huggingface-hub==0.34.4 safetensors==0.6.2 tokenizers==0.22.0 \
        numpy==1.26.4 Pillow==12.3.0 PyYAML==6.0.2

COPY src/so101_demo_py /opt/so101_demo_py
RUN python -m pip install --no-deps /opt/so101_demo_py \
    && python -c 'import importlib.metadata as m; from so101_demo.runtime.parallel_perception_runtime import PINS; assert all(m.version(p.split("==")[0]) == p.split("==")[1] for p in PINS)' \
    && python -c 'import torch, torchvision, ultralytics, transformers, scipy; from transformers import Sam2Model, Sam2Processor, AutoModelForZeroShotObjectDetection'

ARG DOCKERFILE_SHA256
ARG LOCK_SHA256
ARG SOURCE_SHA256
LABEL so101.parallel.dockerfile_sha256=$DOCKERFILE_SHA256 \
      so101.parallel.lock_sha256=$LOCK_SHA256 \
      so101.parallel.source_sha256=$SOURCE_SHA256
RUN DOCKERFILE_SHA256=$DOCKERFILE_SHA256 LOCK_SHA256=$LOCK_SHA256 SOURCE_SHA256=$SOURCE_SHA256 \
    python -c 'import os,pathlib; from so101_demo.runtime.parallel_perception_runtime import canonical_json; pathlib.Path("/opt/parallel-provenance.json").write_bytes(canonical_json({n:os.environ[n.upper()] for n in ("dockerfile_sha256","lock_sha256","source_sha256")}))'
WORKDIR /tmp
ENTRYPOINT ["/opt/venv/bin/so101_parallel_perception_broker"]
