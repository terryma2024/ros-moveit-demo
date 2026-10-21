#!/usr/bin/env python3
"""apt-pins: the `name=version` list that makes an image's apt packages the same versions as a host (stdlib only).

generate  --host HOST.json --image IMAGE.json [--output FILE]
    HOST.json / IMAGE.json are manifests from `image_env.py capture-host` / `capture-image`. Every package of the image that the host
    also has is written as `name=<host version>`; image-only packages are listed on stderr and left out (apt chooses them).
unavailable  --pins FILE --madison FILE
    `--madison` is the output of `apt-cache madison` for the pinned names inside the image (all sources configured). Prints the
    pins whose version no configured source offers, one per line; exit 1 when there are any.
"""

from __future__ import annotations

import argparse
import json
import sys


def pins(host_apt: dict[str, str], image_apt: dict[str, str]) -> tuple[list[str], list[str]]:
    shared = sorted(name for name in image_apt if name in host_apt)
    image_only = sorted(name for name in image_apt if name not in host_apt)
    return [f"{name}={host_apt[name]}" for name in shared], image_only


def offered(madison_text: str) -> set[tuple[str, str]]:
    """`apt-cache madison` lines `name | version | source` into (name, version) pairs."""
    pairs = set()
    for line in madison_text.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 3 and parts[0]:
            pairs.add((parts[0], parts[1]))
    return pairs


def unavailable(pin_lines: list[str], madison_text: str) -> list[str]:
    have = offered(madison_text)
    return [line for line in pin_lines if tuple(line.split("=", 1)) not in have]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--host", required=True)
    gen.add_argument("--image", required=True)
    gen.add_argument("--output")
    una = sub.add_parser("unavailable")
    una.add_argument("--pins", required=True)
    una.add_argument("--madison", required=True)
    args = parser.parse_args(argv)
    if args.command == "generate":
        lines, image_only = pins(json.load(open(args.host))["apt"], json.load(open(args.image))["apt"])
        text = "".join(line + "\n" for line in lines)
        if args.output:
            open(args.output, "w").write(text)
        else:
            sys.stdout.write(text)
        print(f"{len(lines)} pins; image-only (unpinned): {' '.join(image_only) or 'none'}", file=sys.stderr)
        return 0
    lines = [line.strip() for line in open(args.pins) if line.strip()]
    missing = unavailable(lines, open(args.madison).read())
    for line in missing:
        print(line)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
