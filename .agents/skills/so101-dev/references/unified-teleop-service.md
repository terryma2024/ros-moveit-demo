# 统一 Web 服务（Expert Validation 已退役）

Expert Validation 生产服务、它的网页、`scripts/so101-teleop-macos.zsh` / `scripts/so101-teleop-linux.sh` 启动器、Linux broker 批处理（`so101_parallel_batch`）和感知 broker 容器已于 2026-10-24 退役（挂载树迁移 M5，提交 P3b）。

统一 Web 服务（Teleop、Tasks、Archives）直接用 `so101_unified_web_server.py` 启动，见 `docs/guides/so101-unified-webapp-operation.md`。macOS 服务 campaign（`so101_macos_service_campaign`）和它的进程内 MPS broker 保留。
