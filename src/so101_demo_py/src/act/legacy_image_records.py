"""Read-only verifier of the image-mode container records of sealed campaigns.

New runs start from a mount tree only (design 2026-10-23, M1); about 96 sealed configs predate that and name self-contained images.
Verification of a sealed root never runs an image: it compares the recorded digests, the recorded readback and the identity. That
comparison lives here, used by `collection_qualification_recompute` (and through it by the merge), and nothing launches from it.

The readback shape check is a frozen copy of the image-mode `_report` and runtime contract of the production provenance module
(taken before that module became mount-only): later changes to the mounted readback must not change the verdict on a sealed root.
"""

from pathlib import Path
import re

#: where the image-mode readback of a frozen image reports its modules and ament prefixes
LEGACY_INSTALL_ROOT = "/act/install"


def _require(condition):
    if not condition:
        raise ValueError("IMAGE_PROVENANCE_INVALID")


def _sha(value, length=64):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(length) + r"}", value) is not None


def _git(commit, submodules):
    _require(_sha(commit, 40) and type(submodules) is dict)
    for path, value in submodules.items():
        _require(type(path) is str and path and not Path(path).is_absolute()
                 and ".." not in Path(path).parts and str(Path(path)) == path and _sha(value, 40))


def _runtime_contract(runtime, install_root):
    _require(type(runtime) is dict and set(runtime) == {
        "interpreter", "dependencies", "module_origins", "package_prefixes"})
    _require(runtime["interpreter"] == "/act/venv/bin/python")
    for group in ("dependencies", "module_origins", "package_prefixes"):
        _require(type(runtime[group]) is dict and bool(runtime[group]))
        for name, value in runtime[group].items():
            _require(type(name) is str and bool(name) and type(value) is str and bool(value))
            if group != "dependencies":
                path = Path(value)
                _require(path.is_absolute() and ".." not in path.parts
                         and path.is_relative_to(install_root) and str(path) == value)


def _report(report, install_root):
    _require(type(report) is dict and set(report) == {"schema_version", "kind",
        "package_source_sha256", "install_sha256", "git_commit", "submodules", "runtime"})
    _require(type(report["schema_version"]) is int and report["schema_version"] == 1
             and report["kind"] == "ACT_CONTAINER_IMAGE_READBACK")
    _require(_sha(report["package_source_sha256"]) and _sha(report["install_sha256"]))
    _git(report["git_commit"], report["submodules"])
    _runtime_contract(report["runtime"], install_root)


def image_problem(document, image, mount_build, run_errors):
    """Whether a container's recorded provenance is not the image of the identity. In mount mode (`mount_build` is the identity's
    `{commit, root}`) the readback names that commit, its paths lie under the mounted install, and the record repeats the mount; in
    image mode (`mount_build` is None, a sealed image-mode record) a record that names a mount is refused.

    `run_errors` is the exception tuple the recompute treats as an unreadable original."""

    try:
        report = document["provenance"]
        _report(report, LEGACY_INSTALL_ROOT if mount_build is None else mount_build["root"] + "/install")
        if document.get("mount_build") != mount_build or (mount_build is not None and report["git_commit"] != mount_build["commit"]):
            return True
        return not (document["image_digest"] == image["digest"]
                    and report["package_source_sha256"] == image["package_source_sha256"]
                    and report["install_sha256"] == image["install_sha256"])
    except (ImportError,) + tuple(run_errors):
        return True
