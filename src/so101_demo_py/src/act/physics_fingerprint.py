"""The physics fingerprint of a compiled MuJoCo model: a hash of everything that can change a trajectory, and of nothing else.

Design decision D1 (2026-10-23): visual randomisation reuses the nominal contact calibration, so the identity that gates it must not
move when only rendering changes, and must move when any physics value changes. The fingerprint is computed from the compiled
`MjModel` arrays, not from the XML text, so it does not depend on how the model was written (defaults, classes, include order).

Included: `opt` (timestep, integrator, solver, gravity, noslip, ...), every body, joint, dof, geom (collision shape, size, pose,
friction, contact parameters, mass), site, actuator, tendon, equality, contact pair and exclusion, sensor, key frame and the initial
state. Excluded as rendering: cameras, lights, materials, textures, skins, the visual options, a geom's colour, material and group,
a site's, tendon's and mesh's rendering data, and the counts of the excluded kinds. A texture or a material edit therefore leaves
the fingerprint unchanged, a friction, mass, geometry, damping, gain or timestep edit changes it.

Version 1 (`physics_fingerprint`, the one every existing record carries) hashes the compiled model as it is, so ADDING a purely
visual geom changes it (the geom arrays grow). Version 2 (`stripped_physics_fingerprint*`, indoor scene design 2026-10-24) is for scenes
that add visual-only furniture: before hashing it strips every geom with `contype == 0` and `conaffinity == 0` (such a geom can
never collide, and a guard proves it carries no mass or inertia), the bodies that carried only such geoms, the meshes only they
used, and the asset-path bookkeeping (`npaths`, `paths`, `mesh_pathadr`, `hfield_pathadr`); the digest is domain separated and
the record says `fingerprint_version: 2`. Version 1 is unchanged and stays the one for records that already carry it.
"""

from __future__ import annotations

import hashlib

import numpy as np

#: attribute prefixes of the compiled model that are rendering only
_RENDER_PREFIXES = ("cam_", "light_", "mat_", "tex_", "skin_", "text_", "numeric_", "name_")
#: single attributes that are rendering only (colour, material and display group of an element; render-only mesh data)
_RENDER_NAMES = frozenset((
    "geom_rgba", "geom_matid", "geom_group", "site_rgba", "site_matid", "site_group", "tendon_rgba", "tendon_matid",
    "tendon_group", "tendon_width", "mesh_normal", "mesh_normaladr", "mesh_normalnum", "mesh_texcoord", "mesh_texcoordadr",
    "mesh_texcoordnum", "mesh_face_normal", "mesh_facenormal", "mesh_facetexcoord", "ncam", "nlight", "nmat", "ntex", "ntexdata",
    "nskin", "nskinvert", "nskinvert", "nskintexvert", "nskinface", "nskinbone", "nskinbonevert", "ntext", "ntextdata", "nnumeric",
    "nnumericdata", "nnames", "nnames_map", "ntupledata", "ntuple", "hfield_rgba",
    # bookkeeping that follows the names and the model text, not the physics: the name hash table and the model signature
    "names_map", "signature", "nbuffer"))


#: asset-path bookkeeping that follows the files an asset was read from, not the physics (version 2 only: version 1 hashed it)
_PATH_NAMES = frozenset(("npaths", "paths", "mesh_pathadr", "hfield_pathadr"))
FINGERPRINT_VERSION = 2
FINGERPRINT_VERSIONS = (1, 2)
_STRIPPED_DOMAIN = b"so101-physics-fingerprint-v2\n"


def _arrays(model, excluded=frozenset()):
    """Every (name, ndarray) of the compiled model that is physics: a flat view of its public numeric attributes and `opt`."""
    found = {}
    for name in dir(model):
        if name.startswith("_") or name in _RENDER_NAMES or name in excluded or name.startswith(_RENDER_PREFIXES):
            continue
        try:
            value = getattr(model, name)
        except Exception:      # noqa: BLE001 - an attribute that cannot be read is not part of the model data
            continue
        if isinstance(value, np.ndarray):
            found[name] = value
        elif isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
            found[name] = np.asarray(value)
    for name in dir(model.opt):
        if name.startswith("_"):
            continue
        value = getattr(model.opt, name)
        if isinstance(value, np.ndarray) or isinstance(value, (int, float, np.integer, np.floating)):
            found["opt." + name] = np.asarray(value)
    return found


def physics_fingerprint(model) -> str:
    """The sha256 of the physics arrays of `model`, in a fixed order, with their names, dtypes and shapes."""
    digest = hashlib.sha256()
    for name, value in sorted(_arrays(model).items()):
        data = np.ascontiguousarray(value)
        digest.update(f"{name}|{data.dtype.str}|{data.shape}|".encode())
        digest.update(data.tobytes())
    return digest.hexdigest()


def physics_fingerprint_of_file(path) -> str:
    """The fingerprint of the model the MJCF file `path` compiles to (includes and meshes resolve as MuJoCo does)."""
    import mujoco

    return physics_fingerprint(mujoco.MjModel.from_xml_path(str(path)))


def covered_names(model) -> list:
    """The names of the arrays the fingerprint covers (for tests and for the record of what it means)."""
    return sorted(_arrays(model))


# ---- version 2 ---------------------------------------------------------------------------------------------------------------


def _is_visual_only(geom) -> bool:
    """A geom that can never collide: `contype == 0` and `conaffinity == 0` (defaults and classes are already resolved)."""
    return geom.contype == 0 and geom.conaffinity == 0


def _compile(spec, what):
    try:
        return spec.compile()
    except ValueError as error:
        raise ValueError(f"PHYSICS_FINGERPRINT_STRIP_INVALID: {what}: {error}") from error


def _strip_visual_only(spec):
    """`(full model, stripped model, report)` of a spec: the visual-only elements are removed from a COPY of it.

    Raises `ValueError("PHYSICS_FINGERPRINT_STRIP_CHANGES_MASS: ...")` when the strip would change the mass or inertia of any body that
    stays, or when a removed body carried mass that is not welded to the world (the strip must change nothing a trajectory sees), and
    `PHYSICS_FINGERPRINT_STRIP_INVALID` when the stripped spec does not compile (a removed element was named by a contact pair, a
    sensor or an equality, or its body was the only thing that kept a moving body from having no mass)."""
    import mujoco

    full = _compile(spec.copy(), "the full model")
    work = spec.copy()
    carriers = []
    stripped_geoms = 0
    for geom in list(work.geoms):
        if _is_visual_only(geom):
            if geom.parent not in carriers:
                carriers.append(geom.parent)
            work.delete(geom)
            stripped_geoms += 1
    removed = []
    changed = True
    while changed:
        changed = False
        for body in list(carriers):
            if body.name in ("", "world") or body.explicitinertial or body.mocap:
                continue
            if body.geoms or body.joints or body.sites or body.cameras or body.lights or body.bodies:
                continue
            removed.append(body.name)
            carriers.remove(body)
            work.delete(body)
            changed = True
    used_meshes = {geom.meshname for geom in work.geoms if geom.meshname}
    stripped_meshes = 0
    for mesh in list(work.meshes):
        if mesh.name not in used_meshes:
            work.delete(mesh)
            stripped_meshes += 1
    stripped = _compile(work, "the stripped model")
    removed_ids = set()
    for name in removed:
        identifier = mujoco.mj_name2id(full, mujoco.mjtObj.mjOBJ_BODY, name)
        removed_ids.add(identifier)
        if full.body_mass[identifier] != 0.0 and full.body_weldid[identifier] != 0:
            raise ValueError("PHYSICS_FINGERPRINT_STRIP_CHANGES_MASS: removed body " + name)
    survivors = [identifier for identifier in range(full.nbody) if identifier not in removed_ids]
    if len(survivors) != stripped.nbody:
        raise ValueError("PHYSICS_FINGERPRINT_STRIP_INVALID: body count")
    for new, old in enumerate(survivors):
        if full.body(old).name != stripped.body(new).name:
            raise ValueError("PHYSICS_FINGERPRINT_STRIP_INVALID: body order")
        for array in ("body_mass", "body_inertia", "body_ipos", "body_iquat"):
            if not np.array_equal(getattr(full, array)[old], getattr(stripped, array)[new]):
                raise ValueError(f"PHYSICS_FINGERPRINT_STRIP_CHANGES_MASS: {array} of body {full.body(old).name!r}")
    return full, stripped, {"geoms": stripped_geoms, "bodies": len(removed), "meshes": stripped_meshes}


def _stripped_digest(model) -> str:
    digest = hashlib.sha256()
    digest.update(_STRIPPED_DOMAIN)
    for name, value in sorted(_arrays(model, _PATH_NAMES).items()):
        data = np.ascontiguousarray(value)
        digest.update(f"{name}|{data.dtype.str}|{data.shape}|".encode())
        digest.update(data.tobytes())
    return digest.hexdigest()


def stripped_physics_fingerprint_record(spec) -> dict:
    """`{"fingerprint_version": 2, "sha256", "stripped": {"geoms", "bodies", "meshes"}}` of an `mujoco.MjSpec`."""
    _full, stripped, report = _strip_visual_only(spec)
    return {"fingerprint_version": 2, "sha256": _stripped_digest(stripped), "stripped": report}


def stripped_physics_fingerprint(spec) -> str:
    """The version 2 fingerprint (a sha256 hex digest) of an `mujoco.MjSpec`: the physics of its collision-relevant model."""
    return stripped_physics_fingerprint_record(spec)["sha256"]


def _spec_of_file(path):
    import mujoco

    return mujoco.MjSpec.from_file(str(path))


def stripped_physics_fingerprint_of_file(path) -> str:
    """The version 2 fingerprint of the MJCF file `path` (includes and meshes resolve as MuJoCo does)."""
    return stripped_physics_fingerprint(_spec_of_file(path))


def stripped_physics_fingerprint_record_of_file(path) -> dict:
    return stripped_physics_fingerprint_record(_spec_of_file(path))


def stripped_physics_fingerprint_of_string(xml: str) -> str:
    """The version 2 fingerprint of MJCF text (its includes and assets must be absolute paths or resolvable from the cwd)."""
    import mujoco

    return stripped_physics_fingerprint(mujoco.MjSpec.from_string(xml))


def physics_fingerprint_of_file_version(path, version: int) -> str:
    """The fingerprint of `path` in the given version (1: `physics_fingerprint_of_file`; 2: `stripped_physics_fingerprint_of_file`)."""
    if version == 1:
        return physics_fingerprint_of_file(path)
    if version == 2:
        return stripped_physics_fingerprint_of_file(path)
    raise ValueError("PHYSICS_FINGERPRINT_VERSION_UNKNOWN: " + str(version))


def covered_names_stripped(model) -> list:
    """The names of the arrays version 2 covers (of a stripped model; for tests)."""
    return sorted(_arrays(model, _PATH_NAMES))
