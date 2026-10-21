# The networked steps of the shard image, built once and pinned by ID in scripts/images/base-image-ids.json. The shard build
# (docker/campaign-shard) starts from this image and runs with --network none.
#
# apt: the exact pkg=version set of the ai-station shard image (apt-packages.txt), no recommends.
# pip: the fully resolved venv set with hashes (pip-requirements.lock), --require-hashes --no-deps.
# No .pyc: PIP_NO_COMPILE, PYTHONDONTWRITEBYTECODE, and the ones apt's package scripts compile are removed in the same layer.
# Design: docs/superpowers/specs/2026-10-21-so101-image-content-identity-design.md
FROM so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_COMPILE=1 SOURCE_DATE_EPOCH=1704067200 \
    PYTHONNOUSERSITE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 YOLO_OFFLINE=true

COPY apt-packages.txt pip-requirements.lock /tmp/shard-deps/
RUN find / -xdev -name '*.pyc' | sort > /tmp/shard-deps/pyc.before \
    && apt-get update \
    && apt-get install --yes --no-install-recommends $(grep -v '^#' /tmp/shard-deps/apt-packages.txt) \
    && find / -xdev -name '*.pyc' | sort | comm -13 /tmp/shard-deps/pyc.before - | xargs -r rm -f \
    && find / -xdev -type d -name __pycache__ -empty -delete \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --system-site-packages /act/venv \
    && printf '%s\n' 'import sys; sys.path[:0] = ["/act/install/lib/python3.12/site-packages", "/act/install/local/lib/python3.12/dist-packages", "/opt/ros/jazzy/lib/python3.12/site-packages", "/opt/venv/lib/python3.12/site-packages"]' \
       > /act/venv/lib/python3.12/site-packages/act-runtime.pth \
    && NO_PROXY="${NO_PROXY:+$NO_PROXY,}pypi.tuna.tsinghua.edu.cn" no_proxy="${no_proxy:+$no_proxy,}pypi.tuna.tsinghua.edu.cn" \
       /act/venv/bin/python -m pip install --no-compile --no-deps --require-hashes --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r /tmp/shard-deps/pip-requirements.lock \
    && rm -rf /tmp/shard-deps /root/.cache
