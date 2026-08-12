"""Materialize the installed prepared SDF with its controller configuration."""

from pathlib import Path


def materialize_prepared_model(template: Path, package_share: Path, output: Path) -> Path:
    text = template.read_text(encoding="utf-8")
    token = "@SO101_PACKAGE_SHARE@"
    if text.count(token) != 1:
        raise ValueError("prepared SDF must contain exactly one package-share token")
    if "so101_gazebo_demo_py" in text:
        raise ValueError("prepared SDF contains a legacy package dependency")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text.replace(token, str(package_share.resolve())), encoding="utf-8")
    return output
