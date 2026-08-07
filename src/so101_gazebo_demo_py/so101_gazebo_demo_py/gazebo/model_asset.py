"""Materialize an immutable prepared SDF with its installed package path."""

from pathlib import Path


_SHARE_TOKEN = "@SO101_PACKAGE_SHARE@"


def materialize_prepared_model(template: Path, package_share: Path, output: Path) -> Path:
    text = template.read_text(encoding="utf-8")
    if text.count(_SHARE_TOKEN) != 1:
        raise ValueError("prepared SDF must contain exactly one package-share token")
    if "libso101_attachment_collision_system.so" in text or "model://so101_gazebo_demo/" in text:
        raise ValueError("prepared SDF contains a forbidden legacy runtime dependency")
    rendered = text.replace(_SHARE_TOKEN, str(package_share.resolve()))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    return output
