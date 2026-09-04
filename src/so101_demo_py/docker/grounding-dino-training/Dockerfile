FROM nvcr.io/nvidia/cuda:13.0.2-cudnn-runtime-ubuntu24.04@sha256:4d242f206abc4b9588a6506cce2d88932cc879849395aae3785075179718cc49

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

RUN --mount=type=cache,id=so101-yolo-training-apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=so101-yolo-training-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        python3 \
        python3-pip \
        python3-venv \
    && python3 -m venv /opt/venv

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu130

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
        numpy==2.5.2 \
        Pillow==12.3.0 \
        setuptools==84.0.0 \
        sympy==1.14.0 \
        typing_extensions==4.16.0

RUN --mount=type=cache,id=so101-pip-py312-cu130,target=/root/.cache/pip,sharing=locked \
    python -m pip install --retries 10 \
        --index-url "${PIP_INDEX_URL}" \
        --extra-index-url "${PYTORCH_INDEX_URL}" \
        torch==2.13.0+cu130 torchvision==0.28.0+cu130

COPY src/so101_demo_py/config/perception/requirements.lock /tmp/requirements.lock

RUN --mount=type=cache,id=so101-pip-py312-cu130,target=/root/.cache/pip,sharing=locked \
    grep -Fx 'transformers==4.56.2' /tmp/requirements.lock \
    && python -m pip install --retries 10 \
        --index-url "${PIP_INDEX_URL}" \
        --requirement /tmp/requirements.lock

COPY src/so101_demo_py /opt/so101_demo_py

RUN python -m pip install --no-cache-dir --no-deps /opt/so101_demo_py \
    && python -c 'import torch, torchvision, transformers; assert torch.__version__ == "2.13.0+cu130"; assert torchvision.__version__ == "0.28.0+cu130"; assert transformers.__version__ == "4.56.2"'

LABEL org.opencontainers.image.title="SO-101 Grounding DINO Tiny trainer" \
      org.opencontainers.image.description="Pinned offline CUDA fine-tuning environment for generic cup detection" \
      org.opencontainers.image.source="https://gitee.com/zjumty/robot-demo-001"

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    CUBLAS_WORKSPACE_CONFIG=:4096:8

WORKDIR /training-output

ENTRYPOINT ["train_grounding_dino"]
