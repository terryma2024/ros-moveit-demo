"""A copy of the indoor assets in which the procedural textures of the committed manifest exist as PNGs (the install tree has them from the mount build)."""

from __future__ import annotations

import shutil
from pathlib import Path

from paths import PACKAGE_ROOT

ACT_ASSETS = PACKAGE_ROOT / "assets/mujoco/act"


def build_pool_tree(base: Path, ids=None) -> Path:
    """`base/mujoco/{act, assets, textures/indoor}`; returns `base/mujoco/act`. `act` is a real directory (the scenes reach `../textures`), the other
    asset directories are links, the legacy textures and manifests are links, and the procedural PNGs of `ids` (default: the whole pool) are written."""
    from so101_demo.act import indoor_assets

    root = Path(base) / "mujoco"
    shutil.copytree(ACT_ASSETS, root / "act")
    for entry in ACT_ASSETS.parent.iterdir():
        if entry.name not in ("act", "textures"):
            (root / entry.name).symlink_to(entry)
    textures = root / "textures/indoor"
    textures.mkdir(parents=True)
    source = ACT_ASSETS.parent / "textures/indoor"
    for path in source.glob("*.*"):
        (textures / path.name).symlink_to(path)
    indoor_assets.materialize(indoor_assets.load_manifest(source / indoor_assets.PROC_MANIFEST), textures, ids=ids)
    write_cc0(textures, indoor_assets.load_manifest(source / indoor_assets.CC0_MANIFEST))
    return root / "act"


def write_cc0(textures: Path, manifest: dict) -> None:
    """The CC0 files of the manifest: the real pack when `INDOOR_CC0_PACK` names one, else flat 512 px placeholders of each texture's mean colour (the
    pack is not in git; the tests need the files to exist, not their pixels)."""
    import os

    import numpy as np
    from so101_demo.act import indoor_assets

    pack = os.environ.get("INDOOR_CC0_PACK")
    target = textures / indoor_assets.CC0_DIRECTORY
    target.mkdir(exist_ok=True)
    for entry in manifest["textures"]:
        name = entry["id"].split("/", 1)[1] + ".png"
        if pack and (Path(pack) / name).is_file():
            shutil.copyfile(Path(pack) / name, target / name)
        else:
            colour = np.round(np.asarray(entry["mean_rgb"]) * 255).astype(np.uint8)
            (target / name).write_bytes(indoor_assets.png_bytes(np.broadcast_to(colour, (indoor_assets.SIZE, indoor_assets.SIZE, 3)).copy()))
