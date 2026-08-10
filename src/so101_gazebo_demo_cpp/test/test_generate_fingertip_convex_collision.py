"""Tests for offline fingertip ROI extraction and convex asset manifests."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

try:
    import trimesh
except ModuleNotFoundError:
    trimesh = None

pytestmark = pytest.mark.skipif(
    trimesh is None, reason='offline VHACD asset generation dependencies are optional'
)


PACKAGE_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE_DIR / 'scripts' / 'generate_fingertip_convex_collision.py'
BUILD_ASSET_ROOT = (
    PACKAGE_DIR.parents[1] / 'build' / 'so101_gazebo_demo_cpp' / 'fingertip_pad_assets'
)


def load_module():
    assert SCRIPT.exists(), 'generic fingertip convex generator is missing'
    spec = importlib.util.spec_from_file_location('generate_fingertip', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def two_separated_boxes():
    first = trimesh.creation.box(extents=(0.02, 0.02, 0.02))
    second = first.copy()
    second.apply_translation((0.10, 0.0, 0.0))
    return trimesh.util.concatenate((first, second))


def test_roi_extraction_excludes_triangles_outside_bounds():
    module = load_module()
    roi = module.Roi((-0.02, -0.02, -0.02), (0.02, 0.02, 0.02))

    extracted = module.extract_roi(two_separated_boxes(), roi)

    assert extracted.bounds[:, 0].tolist() == pytest.approx([-0.01, 0.01], abs=1e-6)
    assert len(extracted.faces) == 12


def test_roi_extraction_clips_straddling_triangles_to_exact_bounds():
    module = load_module()
    mesh = trimesh.creation.box(extents=(0.02, 0.02, 0.02))
    mesh.apply_translation((0.015, 0.0, 0.0))
    roi = module.Roi((-0.02, -0.02, -0.02), (0.02, 0.02, 0.02))

    extracted = module.extract_roi(mesh, roi)

    assert extracted.bounds[1, 0] == pytest.approx(0.02, abs=1e-9)
    assert extracted.bounds[0, 0] == pytest.approx(0.005, abs=1e-9)


def test_empty_roi_fails_closed():
    module = load_module()
    roi = module.Roi((0.20, 0.20, 0.20), (0.21, 0.21, 0.21))

    with pytest.raises(ValueError, match='fingertip ROI is empty'):
        module.extract_roi(two_separated_boxes(), roi)


def test_missing_vhacd_backend_has_actionable_error(monkeypatch):
    module = load_module()

    def missing_backend(*args, **kwargs):
        raise ModuleNotFoundError("No module named 'vhacdx'")

    monkeypatch.setattr(trimesh.Trimesh, 'convex_decomposition', missing_backend)

    with pytest.raises(RuntimeError, match='vhacdx.*numpy<2'):
        module.decompose_mesh(
            trimesh.creation.box(), max_convex_hulls=8, voxel_resolution=400000
        )


def test_small_boundary_fragments_can_be_filtered_by_volume_ratio():
    module = load_module()
    large = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    fragment = trimesh.creation.box(extents=(0.1, 0.1, 0.1))

    retained = module.filter_small_pieces(
        [fragment, large], minimum_piece_volume_ratio=0.01
    )

    assert retained == [large]


def test_dense_face_audit_detects_convex_hull_crossing_a_concave_source():
    """Vertices on-source are insufficient: audit convex face interiors."""
    module = load_module()
    source = trimesh.creation.icosphere(subdivisions=2, radius=0.01)
    dent = source.vertices[:, 2] > 0.0075
    source.vertices[dent, 2] -= 0.003
    source.fix_normals()
    assert source.is_watertight

    result = module.audit_convex_hull_outward_protrusion(
        source, source.convex_hull, samples_per_edge=24
    )

    assert result['max_outward_protrusion_m'] > 0.0001
    assert result['collision_face_index'] >= 0
    assert result['source_face_index'] >= 0
    assert len(result['worst_point']) == 3
    assert len(result['closest_source_point']) == 3


def test_actual_pad_convex_face_interiors_do_not_protrude_from_tpu_visual():
    """Audit every hull face, including the live peak pieces fixed-005 / moving-002."""
    module = load_module()
    threshold_m = 0.0001
    for side in ('fixed', 'moving'):
        visual = trimesh.load_mesh(
            BUILD_ASSET_ROOT / side / 'fingertip_pad.stl', force='mesh', process=False
        )
        pieces = sorted((BUILD_ASSET_ROOT / side).glob('fingertip_pad_collision_*.stl'))
        assert len(visual.triangles) == 12 * len(pieces)
        for index, path in enumerate(pieces):
            visual_triangles = visual.triangles[12 * index:12 * (index + 1)]
            vertices = visual_triangles.reshape(-1, 3)
            source = trimesh.Trimesh(
                vertices=vertices,
                faces=np.arange(len(vertices)).reshape(-1, 3),
                process=True,
            )
            collision = trimesh.load_mesh(path, force='mesh', process=True).convex_hull
            assert source.is_watertight
            assert source.is_winding_consistent
            # This exact property closes the space between the regular samples:
            # a convex source is identical to its convex hull, so no unsampled
            # face interior can bridge a hidden concavity.
            assert source.is_convex
            audit = module.audit_convex_hull_outward_protrusion(
                source, collision, samples_per_edge=16
            )
            assert audit['max_outward_protrusion_m'] <= threshold_m


def test_generation_passes_budget_and_emits_binary_deterministic_manifest(
    tmp_path, monkeypatch
):
    module = load_module()
    source = tmp_path / 'source.stl'
    source.write_bytes(trimesh.exchange.stl.export_stl(two_separated_boxes()))
    calls = []

    def fake_decompose(mesh, *, max_convex_hulls, voxel_resolution):
        calls.append((max_convex_hulls, voxel_resolution, len(mesh.faces)))
        return [mesh.convex_hull]

    monkeypatch.setattr(module, 'decompose_mesh', fake_decompose)
    roi = module.Roi((-0.02, -0.02, -0.02), (0.02, 0.02, 0.02))
    first = tmp_path / 'first'
    second = tmp_path / 'second'

    manifest_a = module.generate_collision_set(
        source,
        first,
        prefix='fixed_finger_contact_convex',
        roi=roi,
        max_convex_hulls=8,
        voxel_resolution=400000,
    )
    manifest_b = module.generate_collision_set(
        source,
        second,
        prefix='fixed_finger_contact_convex',
        roi=roi,
        max_convex_hulls=8,
        voxel_resolution=400000,
    )

    assert calls == [(8, 400000, 12), (8, 400000, 12)]
    assert manifest_a == manifest_b
    assert manifest_a['schema_version'] == 1
    assert manifest_a['roi_min'] == [-0.02, -0.02, -0.02]
    assert manifest_a['roi_max'] == [0.02, 0.02, 0.02]
    assert manifest_a['max_convex_hulls'] == 8
    assert manifest_a['voxel_resolution'] == 400000
    assert manifest_a['minimum_piece_volume_ratio'] == 0.0
    assert len(manifest_a['source_sha256']) == 64
    assert manifest_a['pieces'][0]['filename'] == 'fixed_finger_contact_convex_000.stl'
    assert len(manifest_a['pieces'][0]['sha256']) == 64
    piece = first / manifest_a['pieces'][0]['filename']
    assert not piece.read_bytes().startswith(b'solid')
    assert json.loads((first / 'manifest.json').read_text()) == manifest_a
