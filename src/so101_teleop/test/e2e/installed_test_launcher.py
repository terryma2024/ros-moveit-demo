#!/usr/bin/env python3
"""L2 installed test launcher.

Composes the production validation service from a copied install prefix and
injects the typed test execution port.  This module is never installed as a
product entry point, and no environment variable switches a production
launcher into this mode.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

import uvicorn


def _bootstrap_install_imports(install_prefix: Path) -> None:
    """Resolve production modules from the copied install, not the source tree."""

    # The interpreter directory is a property of the host's install, not of the launcher: ai-station
    # builds 3.12 and macOS runs 3.11, and hardcoding either one refused the other with
    # INSTALL_PREFIX_SITE_PACKAGES_MISSING, which surfaced as INSTALLED_SERVER_EXITED:2 in every
    # installed spec.
    site_packages = sorted(install_prefix.glob("*/lib/python3.*/site-packages"))
    if not site_packages:
        raise RuntimeError("INSTALL_PREFIX_SITE_PACKAGES_MISSING")
    script_dir = str(Path(__file__).resolve().parent)
    kept = [
        entry
        for entry in sys.path
        if entry and "ws_moveit" not in entry and entry != script_dir
    ]
    sys.path[:] = [script_dir, *(str(path) for path in site_packages), *kept]
    for module in ("so101_demo", "so101_teleop"):
        sys.modules.pop(module, None)

    import so101_demo
    import so101_teleop

    for module in (so101_demo, so101_teleop):
        module_path = Path(module.__file__).resolve()
        if not module_path.is_relative_to(install_prefix):
            raise RuntimeError(f"INSTALL_IMPORT_ORIGIN:{module.__name__}={module_path}")


def create_installed_test_app(
    *,
    install_prefix: Path,
    evidence_root: Path,
    execution_port,
    environment: dict[str, str],
    static_dir: Path | None = None,
):
    """Compose production modules with the typed test execution port."""

    _bootstrap_install_imports(install_prefix)

    from so101_teleop.expert_validation.api import create_expert_validation_app
    from so101_teleop.expert_validation.production import create_production_service

    service = create_production_service(
        evidence_root,
        environment=environment,
        execution_port=execution_port,
    )
    app = create_expert_validation_app(service, static_dir)
    app.state.installed_test_service = service
    return app


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-prefix", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--static-dir", type=Path, default=None)
    parser.add_argument("--ready-file", required=True, type=Path)
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    install_prefix = args.install_prefix.resolve()
    if install_prefix.is_symlink() or not install_prefix.is_dir():
        raise RuntimeError("INSTALL_PREFIX_INVALID")
    from execution_port import HelperExecutionPort

    port = HelperExecutionPort(
        python=sys.executable,
        helpers_dir=Path(__file__).resolve().parent / "process_helpers",
        spec_path=args.spec.resolve(),
    )
    app = create_installed_test_app(
        install_prefix=install_prefix,
        evidence_root=args.evidence_root,
        execution_port=port,
        environment=dict(os.environ),
        static_dir=args.static_dir,
    )
    config = uvicorn.Config(
        app, host="127.0.0.1", port=args.port, log_level="warning", access_log=False
    )
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())
    deadline = asyncio.get_event_loop().time() + 15.0
    while not server.started:
        if asyncio.get_event_loop().time() > deadline or serve_task.done():
            raise RuntimeError("INSTALLED_TEST_SERVER_START_FAILED")
        await asyncio.sleep(0.05)
    args.ready_file.write_text(
        json.dumps({
            "port": args.port,
            "pid": os.getpid(),
            "install_prefix": str(install_prefix),
            "qualification": asdict(port.qualification_manifest()),
        }) + "\n",
        encoding="utf-8",
    )
    await serve_task
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return asyncio.run(_run(args))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
