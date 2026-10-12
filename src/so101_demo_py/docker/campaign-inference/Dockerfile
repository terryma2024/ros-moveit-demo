# This cached dependency base has the exact current CUDA/Head package versions.
# All campaign code comes from the new common source snapshot and /act/install.
# The build coordinator checks this local tag's exact ID before and after build:
# sha256:010dca70ce3ce995367793642c2e5515718986253cecacc032e9f7f7ec6c5457.
# BuildKit interprets a bare image ID in FROM as a repository/tag, so use the
# existing local tag and independently check the resulting layer ancestry.
FROM so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 YOLO_OFFLINE=true \
    AMENT_PREFIX_PATH=/act/install:/opt/ros/jazzy \
    PATH=/act/venv/bin:/act/install/bin:/opt/ros/jazzy/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

COPY source /act/source
RUN chmod -R a+rX,a-w /act/source \
    && python3 -m venv --system-site-packages /act/venv \
    && printf '%s\n' 'import sys; sys.path[:0] = ["/act/install/lib/python3.12/site-packages", "/act/install/local/lib/python3.12/dist-packages", "/opt/ros/jazzy/lib/python3.12/site-packages", "/opt/venv/lib/python3.12/site-packages"]' \
       > /act/venv/lib/python3.12/site-packages/act-runtime.pth
RUN cp -a /act/source /act/build-source \
    && chmod -R u+w /act/build-source \
    && /act/venv/bin/python -m pip install --no-deps --no-build-isolation --prefix /act/install /act/build-source/src/so101_demo_py
COPY source/src/so101_demo_py/docker/campaign-inference/bootstrap.bash /act/bootstrap.bash
RUN chmod 0555 /act/bootstrap.bash \
    && printf '%s\n' inference > /act/image-role \
    && mkdir -p /act/install/share \
    && chmod -R a+rX,a-w /act/install \
    && chmod u+w /act/install/share \
    && /act/venv/bin/python -I -c 'from so101_demo.runtime.container_campaign.provenance import write_build_freeze; write_build_freeze("inference")' \
    && chmod a-w /act/install/share /act/install/share/act-image-dependencies.json /act/provenance.json /act/image-role \
    && /act/bootstrap.bash /act/venv/bin/python -I -m so101_demo.runtime.container_campaign.provenance

WORKDIR /act
ENTRYPOINT ["/act/bootstrap.bash", "/act/venv/bin/python", "-I", "-m", "so101_demo.runtime.container_campaign.image_bootstrap"]
