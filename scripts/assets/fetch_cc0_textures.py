#!/usr/bin/env python3
"""Select, download and resize CC0 albedo textures for the indoor appearance library (indoor scene design 2026-10-24, P3).

Source: Poly Haven (https://polyhaven.com, every asset CC0 1.0, https://polyhaven.com/license). Only the colour (diffuse / albedo) map at 1K is
downloaded (its URL and md5 come from `GET https://api.polyhaven.com/files/<id>`, and the md5 is checked); it is resized to 512 x 512 (Lanczos) and written as a deterministic PNG. The textures are NOT committed (git size, see the design
note): they form a separately hashed pack, and `cc0-manifest.json` (committed) is its identity.

    python scripts/assets/fetch_cc0_textures.py --pack PACK_DIR --catalogue polyhaven-textures.json --manifest-out cc0-manifest.json

`--catalogue` is the Poly Haven `GET https://api.polyhaven.com/assets?t=textures` answer (fetched once; it is read from a file so the selection
is reproducible). The selection is deterministic: indoor-suitable textures (outdoor, terrain, rock, sand, gravel and similar categories are
excluded), one surface per texture (floor, else wall, else table), a seeded sample per surface. `PACK_DIR/raw/` keeps the downloaded files
(sha256 before resizing) and `PACK_DIR/<surface>_polyhaven_<id>.png` the 512 px results (sha256 after). The mount-tree build copies the pack with
`scripts/assets/gen_indoor_textures.py --cc0-pack PACK_DIR --out <install textures dir>` and checks each file against the manifest.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

SEED = 20261025
SIZE = 512
EXCLUDED = {"outdoor", "terrain", "natural", "rock", "sand", "snow", "bark", "gravel", "aerial", "asphalt", "road", "cobblestone", "roofing",
            "sandstone", "moon"}
TARGETS = {"wall": 55, "floor": 60, "table": 65}
FILES_API = "https://api.polyhaven.com/files/{id}"
PAGE = "https://polyhaven.com/a/{id}"
LICENCE = "CC0-1.0"
LICENCE_URL = "https://polyhaven.com/license"
USER_AGENT = "so101-indoor-assets/1 (CC0 texture pack builder; zjumty@gmail.com)"


def surface_of(categories) -> str:
    return "floor" if "floor" in categories else "wall" if "wall" in categories else "table"


def candidates(catalogue: dict) -> dict:
    """`{surface: [asset id, ...]}`: the indoor-suitable assets of each surface in a seeded order; the first `TARGETS[surface]` that have a 1K colour
    JPG are taken (an asset without one is skipped and the next candidate replaces it)."""
    usable = {}
    for asset, info in catalogue.items():
        categories = set(info.get("categories", []))
        if categories & EXCLUDED or any(item.startswith("collection:") and item != "collection: the_shed" for item in categories):
            continue
        usable.setdefault(surface_of(categories), []).append(asset)
    ordered = {}
    for surface in TARGETS:
        pool = sorted(usable.get(surface, []))
        random.Random(f"{SEED}/{surface}").shuffle(pool)
        ordered[surface] = pool
    return ordered


def select(catalogue: dict, source=None) -> tuple:
    """`([(asset id, surface)] sorted, {asset id: source})`; `source(asset)` returns the listing or raises `KeyError`/`OSError` for an asset without
    a 1K colour JPG (default `source_of`)."""
    source = source or source_of
    chosen, sources = [], {}
    for surface, pool in candidates(catalogue).items():
        taken = 0
        for asset in pool:
            if taken == TARGETS[surface]:
                break
            try:
                sources[asset] = source(asset)
            except (KeyError, OSError, ValueError):
                continue
            chosen.append((asset, surface))
            taken += 1
    return sorted(chosen, key=lambda item: (item[1], item[0])), sources


def texture_id(asset: str, surface: str) -> str:
    slug = re.sub(r"[^a-z0-9_]", "_", asset.lower())
    return f"cc0/{surface}_polyhaven_{slug}"


def _get(url: str, attempts: int = 4) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except OSError:
            if attempt == attempts:
                raise
            time.sleep(5 * attempt)


def source_of(asset: str) -> dict:
    """The colour map Poly Haven lists for `asset` at 1K as a JPG: `{"url", "md5", "size"}` (the file name differs by asset: diff, albedo, col)."""
    return json.loads(_get(FILES_API.format(id=asset)))["Diffuse"]["1k"]["jpg"]


def download(asset: str, target: Path, source: dict) -> dict:
    """Fetch the 1K colour JPG of `asset` into `target` (skipped when a file with the listed md5 is there); verify the md5 Poly Haven lists."""
    if not (target.is_file() and hashlib.md5(target.read_bytes()).hexdigest() == source["md5"]):
        data = _get(source["url"])
        if hashlib.md5(data).hexdigest() != source["md5"]:
            raise OSError(f"MD5_MISMATCH: {asset}")
        part = target.with_suffix(".part")
        part.write_bytes(data)
        part.replace(target)
    return source


def resize(raw: Path):
    import numpy as np
    from PIL import Image

    with Image.open(raw) as image:
        original = image.size
        rgb = image.convert("RGB").resize((SIZE, SIZE), Image.LANCZOS)
    return original, np.asarray(rgb)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pack", required=True, type=Path)
    parser.add_argument("--catalogue", required=True, type=Path)
    parser.add_argument("--manifest-out", required=True, type=Path)
    parser.add_argument("--licences-out", type=Path, help="also write the human-readable LICENSES.md here")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--download-only", action="store_true", help="fetch the 1K files into PACK/raw and stop (no resizing, no manifest)")
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    arguments = parser.parse_args(argv)
    # indoor_assets by path: the PNG encoder and the mean colour are the library's
    import importlib.util

    spec = importlib.util.spec_from_file_location("so101_indoor_assets", Path(__file__).resolve().parents[2] / "src/so101_demo_py/src/act/indoor_assets.py")
    assets = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = assets
    spec.loader.exec_module(assets)

    catalogue = json.loads(arguments.catalogue.read_text())
    chosen, listed = select(catalogue)
    raw_dir = arguments.pack / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(arguments.workers) as pool:
        futures = {asset: pool.submit(download, asset, raw_dir / f"{asset}.jpg", listed[asset]) for asset, _surface in chosen}
        for position, (asset, future) in enumerate(futures.items(), 1):
            future.result()
            print(f"[{position}/{len(futures)}] {asset}", flush=True)
    if arguments.download_only:
        print(json.dumps({"status": "DOWNLOADED", "files": len(chosen)}))
        return 0
    entries = []
    for asset, surface in chosen:
        raw = raw_dir / f"{asset}.jpg"
        original, pixels = resize(raw)
        identifier = texture_id(asset, surface)
        data = assets.png_bytes(pixels)
        name = identifier.split("/", 1)[1] + ".png"
        (arguments.pack / name).write_bytes(data)
        info = catalogue[asset]
        entries.append({"id": identifier, "surface": surface, "source": "polyhaven", "asset_id": asset, "name": info.get("name"),
                        "source_url": PAGE.format(id=asset), "download_url": listed[asset]["url"], "md5_listed": listed[asset]["md5"], "licence": LICENCE, "licence_url": LICENCE_URL,
                        "download_date": arguments.date, "authors": sorted((info.get("authors") or {}).keys()),
                        "categories": sorted(info.get("categories", [])), "map": "diffuse (albedo), 1K JPG",
                        "original_size": list(original), "sha256_original": hashlib.sha256(raw.read_bytes()).hexdigest(),
                        "sha256_resized": hashlib.sha256(data).hexdigest(), "bytes_resized": len(data), "mean_rgb": assets.mean_srgb(pixels)})
    manifest = {"kind": "SO101_INDOOR_CC0_TEXTURE_MANIFEST", "schema_version": 1, "size": SIZE, "selection_seed": SEED, "targets": TARGETS,
                "excluded_categories": sorted(EXCLUDED), "licence": LICENCE, "licence_url": LICENCE_URL,
                "note": "colour maps only, resized to 512 px; the files form a separately hashed pack (not in git), identified by this manifest",
                "textures": entries}
    manifest["pack_sha256"] = assets.cc0_pack_sha256(manifest)
    arguments.manifest_out.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if arguments.licences_out:
        lines = ["# Indoor CC0 textures", "", f"All textures are CC0 1.0 (public domain dedication), from Poly Haven ({LICENCE_URL}).",
                 "Colour (diffuse) maps at 1K, downloaded " + arguments.date + ", resized to 512 px. No attribution is required; the authors are listed",
                 "for reference.", "", "| id | asset | source | authors | sha256 resized |", "|---|---|---|---|---|"]
        lines += [f"| {e['id']} | {e['asset_id']} | {e['source_url']} | {', '.join(e['authors'])} | {e['sha256_resized'][:16]} |" for e in entries]
        arguments.licences_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    counts = {surface: sum(1 for entry in entries if entry["surface"] == surface) for surface in TARGETS}
    print(json.dumps({"status": "OK", "textures": len(entries), "per_surface": counts}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
