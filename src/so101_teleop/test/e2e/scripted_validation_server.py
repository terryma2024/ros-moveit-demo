#!/usr/bin/env python3
"""Run one scripted expert-validation server pair for L1 Chrome contract tests.

The product port serves the production FastAPI routes and the real Web bundle
around the scripted service port.  The control port is a separate socket that
only the test driver uses to advance events, inject faults, and read the
command log; it is never a product route and never installed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

import uvicorn

from scripted_service import (
    create_scripted_control_app,
    create_scripted_validation_app,
    load_scenario,
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--control-port", required=True, type=int)
    parser.add_argument("--static-dir", type=Path, default=None)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--ready-file", required=True, type=Path)
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    scenario, digest = load_scenario(args.scenario)
    service_app = create_scripted_validation_app(scenario, digest, args.static_dir)
    service = service_app.state.scripted_service
    control_app = create_scripted_control_app(service)

    evidence_dir = args.evidence_dir.resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if evidence_dir.is_symlink():
        raise RuntimeError("EVIDENCE_DIR_INVALID")

    product_config = uvicorn.Config(
        service_app,
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
        access_log=False,
    )
    control_config = uvicorn.Config(
        control_app,
        host="127.0.0.1",
        port=args.control_port,
        log_level="warning",
        access_log=False,
    )
    product_server = uvicorn.Server(product_config)
    control_server = uvicorn.Server(control_config)

    log_path = evidence_dir / "scripted-server.log"
    with log_path.open("a", encoding="utf-8") as log:
        log.write(
            json.dumps(
                {
                    "scenario_id": scenario.scenario_id,
                    "scenario_sha256": digest,
                    "port": args.port,
                    "control_port": args.control_port,
                }
            )
            + "\n"
        )

    async def serve() -> None:
        product_task = asyncio.create_task(product_server.serve())
        control_task = asyncio.create_task(control_server.serve())
        deadline = asyncio.get_event_loop().time() + 10.0
        while not (product_server.started and control_server.started):
            if asyncio.get_event_loop().time() > deadline:
                raise RuntimeError("SCRIPTED_SERVER_START_TIMEOUT")
            if product_task.done() or control_task.done():
                raise RuntimeError("SCRIPTED_SERVER_START_FAILED")
            await asyncio.sleep(0.05)
        ready = {
            "scenario_id": scenario.scenario_id,
            "scenario_sha256": digest,
            "port": args.port,
            "control_port": args.control_port,
            "pid": __import__("os").getpid(),
        }
        args.ready_file.write_text(json.dumps(ready) + "\n", encoding="utf-8")
        await asyncio.gather(product_task, control_task)

    try:
        await serve()
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 0
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
