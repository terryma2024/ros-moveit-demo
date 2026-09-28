"""Build the canonical Task 8 source provenance document for the current tree and overlay."""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Task 8 live source provenance document")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--install-overlay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    from so101_demo.act.source_provenance import build_source_provenance, write_source_provenance

    document = build_source_provenance(args.source_root, args.install_overlay)
    path = write_source_provenance(document, args.output)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
