# Python 依赖安装加速

## 适用边界

当 SO-101 任务需要用 `uv pip install` 安装 Python 依赖，尤其是 `open3d` 这类大体积 wheel 时，
使用清华大学 TUNA PyPI 镜像，并让该镜像域名在本次命令中绕过代理。

这是一条临时、单命令策略：不修改 `uv` 持久配置，也不修改 Xray 路由。若用户要求判断当前最快镜像，
必须重新验证镜像可用性和同一制品的实际吞吐，不能把本策略写成实时测速结论。

## Open3D 命令

```zsh
NO_PROXY=pypi.tuna.tsinghua.edu.cn \
no_proxy=pypi.tuna.tsinghua.edu.cn \
uv pip install \
  --default-index https://pypi.tuna.tsinghua.edu.cn/simple \
  open3d
```

同时设置大写 `NO_PROXY` 和小写 `no_proxy`，以兼容不同网络库对环境变量名称的读取方式。
镜像参数使用 `--default-index`。

如果当前 shell 已有必须保留的 `NO_PROXY` 或 `no_proxy` 条目，不要直接覆盖；把
`pypi.tuna.tsinghua.edu.cn` 以逗号分隔追加到对应变量，再执行安装。

安装其他 Python 包时只替换最后的 `open3d` 包名；不要因此增加 `--system` 或改变当前虚拟环境边界。
