"""The physics fingerprint of a compiled MuJoCo model: a hash of everything that can change a trajectory, and of nothing else.

Design decision D1 (2026-10-23): visual randomisation reuses the nominal contact calibration, so the identity that gates it must not
move when only rendering changes, and must move when any physics value changes. The fingerprint is computed from the compiled
`MjModel` arrays, not from the XML text, so it does not depend on how the model was written (defaults, classes, include order).

Included: `opt` (timestep, integrator, solver, gravity, noslip, ...), every body, joint, dof, geom (collision shape, size, pose,
friction, contact parameters, mass), site, actuator, tendon, equality, contact pair and exclusion, sensor, key frame and the initial
state. Excluded as rendering: cameras, lights, materials, textures, skins, the visual options, a geom's colour, material and group,
a site's, tendon's and mesh's rendering data, and the counts of the excluded kinds. A texture or a material edit therefore leaves
the fingerprint unchanged, a friction, mass, geometry, damping, gain or timestep edit changes it.
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


def _arrays(model):
    """Every (name, ndarray) of the compiled model that is physics: a flat view of its public numeric attributes and `opt`."""
    found = {}
    for name in dir(model):
        if name.startswith("_") or name in _RENDER_NAMES or name.startswith(_RENDER_PREFIXES):
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
