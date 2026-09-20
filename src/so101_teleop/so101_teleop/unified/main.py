"""The one and only uvicorn entry point for the unified web service."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .app import create_unified_app
from .compose import compose_services


def installed_web_assets(module_file: str | Path | None = None) -> Path | None:
    """Return the installed bundle directory, or None when it is not present.

    The bundle lives at ``<prefix>/share/so101_teleop/web``. From an installed *module*
    (``<prefix>/lib/python3.X/site-packages/so101_teleop/unified/main.py``) that is three levels up,
    while from the installed *script* (``<prefix>/lib/so101_teleop/so101_unified_web_server.py``) it is
    two - so the ancestors are walked rather than a fixed offset assumed. Getting this wrong made an
    installed deployment serve 503 for every page while the bundle sat right there.
    """
    base = Path(module_file or __file__).resolve()
    for parent in base.parents[:6]:
        candidate = parent / "share" / "so101_teleop" / "web"
        if (candidate / "index.html").is_file():
            return candidate
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SO-101 unified web service")
    parser.add_argument("--host", default=os.environ.get("SO101_UNIFIED_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("SO101_UNIFIED_PORT", "8000"))
    )
    parser.add_argument("--static-dir", type=Path, default=None)
    parser.add_argument("--capture-dir", type=Path, default=None)
    parser.add_argument(
        "--check",
        action="store_true",
        help="build the app and exit without binding a port",
    )
    return parser


def build_app(args, environment: dict[str, str] | None = None):
    environment = dict(os.environ if environment is None else environment)
    if environment.get("SO101_TELEOP_OLD_PORT") and environment.get("SO101_VALIDATION_OLD_PORT"):
        if environment["SO101_TELEOP_OLD_PORT"] == environment["SO101_VALIDATION_OLD_PORT"]:
            raise SystemExit("SO101_PORT_CONFLICT: legacy ports must not collide")
    services = compose_services(environment)
    static_dir = args.static_dir or installed_web_assets()
    return create_unified_app(
        services,
        static_dir=static_dir,
        capture_dir=args.capture_dir,
        bind_address=args.host,
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    app = build_app(args)
    if args.check:
        print("SO101_UNIFIED_APP_OK")
        return
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
