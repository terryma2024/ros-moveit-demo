"""Behavior contract for the manifest-driven URDF-to-SDF preparation boundary."""

import hashlib
import importlib.util
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


PACKAGE_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE_DIR / 'scripts' / 'prepare_simulation_model.py'
FIXED_MANIFEST = PACKAGE_DIR / 'meshes' / 'so101' / 'collision' / 'fixed_finger_contact' / 'manifest.json'
MOVING_MANIFEST = PACKAGE_DIR / 'meshes' / 'so101' / 'collision' / 'moving_jaw_contact' / 'manifest.json'


def load_module():
    assert SCRIPT.exists(), 'simulation model preparation boundary is missing'
    spec = importlib.util.spec_from_file_location('prepare_simulation_model', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _read_manifest(path):
    with open(path, 'r', encoding='utf-8') as stream:
        return json.load(stream)


def _fingertip_sdf(fixed_manifest, moving_manifest):
    """Build SDF matching the two manifests' piece names."""
    fixed_collisions = ''.join(
        f'''<collision name="{piece['filename'].replace('.stl', '')}">
          <geometry><mesh><uri>{piece['filename']}</uri></mesh></geometry>
        </collision>'''
        for piece in fixed_manifest['pieces']
    )
    moving_collisions = ''.join(
        f'''<collision name="{piece['filename'].replace('.stl', '')}">
          <geometry><mesh><uri>{piece['filename']}</uri></mesh></geometry>
        </collision>'''
        for piece in moving_manifest['pieces']
    )
    return f'''<sdf version="1.11">
  <model name="so101">
    <link name="gripper">
      {fixed_collisions}
    </link>
    <link name="jaw">
      {moving_collisions}
    </link>
  </model>
</sdf>'''


def _native_pad_collisions():
    return ''.join(
        f'''<collision name="gripper_fixed_joint_lump__{side}_fingertip_pad_collision_{index:03d}_collision_{index}">
          <geometry><mesh><uri>model://so101_gazebo_demo/meshes/so101/generated/{asset_side}/fingertip_pad_collision_{index:03d}.stl</uri></mesh></geometry>
        </collision>'''
        for side, asset_side, count in (('fixed', 'fixed', 7), ('moving', 'moving', 6))
        for index in range(count)
    )


# ---------------------------------------------------------------------------
# load_manifest
# ---------------------------------------------------------------------------

def test_load_manifest_reads_installed_fixed_set():
    module = load_module()
    manifest = module.load_manifest(FIXED_MANIFEST)
    assert manifest['prefix'] == 'fixed_finger_contact_convex'
    assert manifest['schema_version'] == 1
    assert 1 <= len(manifest['pieces']) <= 12
    for piece in manifest['pieces']:
        assert 'filename' in piece
        assert 'sha256' in piece
        assert len(piece['sha256']) == 64


def test_load_manifest_reads_installed_moving_set():
    module = load_module()
    manifest = module.load_manifest(MOVING_MANIFEST)
    assert manifest['prefix'] == 'moving_jaw_contact_convex'
    assert 1 <= len(manifest['pieces']) <= 12


def test_load_manifest_rejects_missing_file():
    module = load_module()
    with pytest.raises(FileNotFoundError):
        module.load_manifest(Path('/tmp/so101_nonexistent_manifest.json'))


def test_load_manifest_rejects_bad_schema_version(tmp_path):
    module = load_module()
    bad = tmp_path / 'bad_manifest.json'
    bad.write_text(json.dumps({'schema_version': 99, 'prefix': 'x', 'pieces': []}))
    with pytest.raises(ValueError, match='schema'):
        module.load_manifest(bad)


def test_load_manifest_validates_piece_sha_against_files(tmp_path):
    module = load_module()
    collision_dir = tmp_path / 'collision'
    collision_dir.mkdir()
    piece = collision_dir / 'test_convex_000.stl'
    piece.write_bytes(b'fake stl content')
    wrong_hash = '0' * 64
    manifest = {
        'schema_version': 1,
        'prefix': 'test_convex',
        'pieces': [{'filename': 'test_convex_000.stl', 'sha256': wrong_hash}],
    }
    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='sha256|hash|SHA'):
        module.load_manifest(manifest_path, collision_root=collision_dir)


def test_load_manifest_rejects_missing_piece_file(tmp_path):
    module = load_module()
    collision_dir = tmp_path / 'collision'
    collision_dir.mkdir()
    manifest = {
        'schema_version': 1,
        'prefix': 'test_convex',
        'pieces': [{'filename': 'nonexistent_000.stl', 'sha256': 'a' * 64}],
    }
    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises((ValueError, FileNotFoundError)):
        module.load_manifest(manifest_path, collision_root=collision_dir)


# ---------------------------------------------------------------------------
# enable_fingertip_convex_hulls
# ---------------------------------------------------------------------------

def test_fingertip_convex_hulls_marks_both_prefixes():
    module = load_module()
    fixed = _read_manifest(FIXED_MANIFEST)
    moving = _read_manifest(MOVING_MANIFEST)
    sdf = _fingertip_sdf(fixed, moving)

    result = module.enable_fingertip_convex_hulls(sdf, [fixed, moving])
    root = ET.fromstring(result)

    for prefix in ('fixed_finger_contact_convex', 'moving_jaw_contact_convex'):
        collisions = [
            c for c in root.iter('collision')
            if c.attrib.get('name', '').startswith(prefix)
        ]
        assert len(collisions) > 0, f'no collisions with prefix {prefix}'
        for collision in collisions:
            mesh = collision.find('geometry/mesh')
            assert mesh is not None
            assert mesh.attrib.get('optimization') == 'convex_hull'
            assert mesh.find('convex_decomposition') is None


def test_fingertip_convex_hulls_marks_native_tpu_pad_pieces():
    """Convex TPU pieces must not fall into Bullet's 10 mm GImpact margin."""
    module = load_module()
    fixed = _read_manifest(FIXED_MANIFEST)
    moving = _read_manifest(MOVING_MANIFEST)
    sdf = _fingertip_sdf(fixed, moving).replace(
        '</link>', _native_pad_collisions() + '</link>', 1
    )

    result = module.enable_fingertip_convex_hulls(sdf, [fixed, moving])
    root = ET.fromstring(result)
    pads = [
        collision for collision in root.iter('collision')
        if '_fingertip_pad_collision_' in collision.attrib.get('name', '')
    ]
    assert len(pads) == 13
    for collision in pads:
        mesh = collision.find('geometry/mesh')
        assert mesh is not None
        assert mesh.attrib.get('optimization') == 'convex_hull'


def test_fingertip_contact_material_is_injected_into_generated_sdf():
    """The URDF converter drops Gazebo contact tags; preparation must restore them."""
    module = load_module()
    fixed = _read_manifest(FIXED_MANIFEST)
    moving = _read_manifest(MOVING_MANIFEST)
    sdf = _fingertip_sdf(fixed, moving).replace(
        '</link>', _native_pad_collisions() + '</link>', 1
    )
    material = {
        'axial_friction_coefficient': 3.0,
        'transverse_friction_coefficient': 1.2,
        'contact_stiffness_n_m': 1000000.0,
        'contact_damping_n_s_m': 100.0,
        'max_correcting_velocity_m_s': 0.01,
        'min_depth_m': 0.0001,
    }

    result = module.apply_fingertip_contact_material(sdf, material)
    root = ET.fromstring(result)
    pads = [
        collision for collision in root.iter('collision')
        if '_fingertip_pad_collision_' in collision.attrib.get('name', '')
    ]
    assert len(pads) == 13
    for collision in pads:
        direction = (
            '0 0 1'
            if 'fixed_fingertip' in collision.attrib['name'] else '0 1 0'
        )
        assert collision.findtext('surface/friction/ode/mu') == '3.0'
        assert collision.findtext('surface/friction/ode/mu2') == '1.2'
        assert collision.findtext('surface/friction/ode/fdir1') == direction
        assert collision.findtext('surface/friction/bullet/friction') == '3.0'
        assert collision.findtext('surface/friction/bullet/friction2') == '1.2'
        # bullet-featherstone ignores SDF fdir1.  Its anisotropic axes are the
        # compound link's local axes, so emitting fdir1 would promise behavior
        # that the selected engine cannot provide.
        assert collision.find('surface/friction/bullet/fdir1') is None
        assert collision.findtext('surface/contact/ode/kp') == '1000000.0'
        assert collision.findtext('surface/contact/ode/kd') == '100.0'
        assert collision.findtext('surface/contact/ode/max_vel') == '0.01'
        assert collision.findtext('surface/contact/ode/min_depth') == '0.0001'
        assert collision.findtext('surface/contact/bullet/kp') == '1000000.0'
        assert collision.findtext('surface/contact/bullet/kd') == '100.0'


def test_fingertip_material_reaches_bullet_compound_link_owner_collision():
    """Bullet reads friction only from the first collision of a compound link."""
    module = load_module()
    fixed_pads = ''.join(
        f'''<collision name="fixed_fingertip_pad_collision_{index:03d}_collision_{index}">
          <geometry><mesh><uri>fixed-{index}.stl</uri></mesh></geometry>
        </collision>'''
        for index in range(7)
    )
    moving_pads = ''.join(
        f'''<collision name="moving_fingertip_pad_collision_{index:03d}_collision_{index}">
          <geometry><mesh><uri>moving-{index}.stl</uri></mesh></geometry>
        </collision>'''
        for index in range(6)
    )
    sdf = f'''<sdf version="1.11"><model name="so101">
      <link name="gripper">
        <collision name="fixed_finger_contact_convex_000_collision"/>
        {fixed_pads}
      </link>
      <link name="jaw">
        <collision name="moving_jaw_contact_convex_000_collision"/>
        {moving_pads}
      </link>
    </model></sdf>'''
    material = {
        'axial_friction_coefficient': 3.0,
        'transverse_friction_coefficient': 1.2,
        'contact_stiffness_n_m': 1000000.0,
        'contact_damping_n_s_m': 100.0,
        'max_correcting_velocity_m_s': 0.01,
        'min_depth_m': 0.0001,
    }

    root = ET.fromstring(module.apply_fingertip_contact_material(sdf, material))
    for link_name in ('gripper', 'jaw'):
        owner = root.find(f".//link[@name='{link_name}']/collision")
        assert owner is not None
        assert owner.findtext('surface/friction/bullet/friction') == '3.0'
        assert owner.findtext('surface/friction/bullet/friction2') == '1.2'
        assert owner.find('surface/friction/bullet/fdir1') is None
        # Bullet Featherstone also resolves compound-contact material from the
        # first collision owned by the link.  Stiffness only on a later pad
        # child is therefore as ineffective as friction only on that child.
        assert owner.findtext('surface/contact/bullet/kp') == '1000000.0'
        assert owner.findtext('surface/contact/bullet/kd') == '100.0'


def test_generated_sdf_native_pad_detection_parses_collision_names():
    module = load_module()
    sdf = '''<sdf version="1.11"><model name="so101"><link name="gripper">
      <collision name="gripper_fixed_joint_lump__fixed_fingertip_pad_collision_000_collision_7"/>
    </link></model></sdf>'''

    assert module.has_native_fingertip_pads(sdf)


def test_fingertip_convex_hulls_rejects_name_mismatch():
    module = load_module()
    fixed = _read_manifest(FIXED_MANIFEST)
    moving = _read_manifest(MOVING_MANIFEST)
    sdf = '<sdf version="1.11"><model name="so101"/></sdf>'

    with pytest.raises(ValueError):
        module.enable_fingertip_convex_hulls(sdf, [fixed, moving])


def test_fingertip_convex_hulls_rejects_duplicate_collision():
    module = load_module()
    fixed = _read_manifest(FIXED_MANIFEST)
    moving = _read_manifest(MOVING_MANIFEST)
    piece_name = fixed['pieces'][0]['filename'].replace('.stl', '')
    dup_sdf = f'''<sdf version="1.11">
      <model name="so101"><link name="gripper">
        <collision name="{piece_name}"><geometry><mesh><uri>x.stl</uri></mesh></geometry></collision>
        <collision name="{piece_name}"><geometry><mesh><uri>x.stl</uri></mesh></geometry></collision>
      </link></model>
    </sdf>'''
    with pytest.raises(ValueError, match='duplicate'):
        module.enable_fingertip_convex_hulls(dup_sdf, [fixed])


def test_fingertip_convex_hulls_rejects_total_over_24():
    module = load_module()
    fake_manifest = {
        'prefix': 'fake_convex',
        'pieces': [{'filename': f'fake_convex_{i:03d}.stl', 'sha256': 'a' * 64}
                   for i in range(25)],
    }
    collisions = ''.join(
        f'<collision name="fake_convex_{i:03d}"><geometry><mesh><uri>x.stl</uri></mesh></geometry></collision>'
        for i in range(25)
    )
    sdf = f'<sdf version="1.11"><model name="so101"><link name="g">{collisions}</link></model></sdf>'
    with pytest.raises(ValueError, match='24|twenty'):
        module.enable_fingertip_convex_hulls(sdf, [fake_manifest])


def test_fingertip_convex_hulls_matches_gz_sdf_joint_lump_prefix():
    module = load_module()
    piece_name = 'fixed_finger_contact_convex_000'
    lumped_name = f'gripper_fixed_joint_lump__{piece_name}_collision'
    manifest = {
        'prefix': 'fixed_finger_contact_convex',
        'pieces': [{'filename': f'{piece_name}.stl', 'sha256': 'a' * 64}],
    }
    sdf = f'''<sdf version="1.11"><model name="so101"><link name="gripper">
      <collision name="{lumped_name}"><geometry><mesh><uri>x.stl</uri></mesh></geometry></collision>
    </link></model></sdf>'''

    result = module.enable_fingertip_convex_hulls(sdf, [manifest])
    root = ET.fromstring(result)
    mesh = root.find('.//collision/geometry/mesh')
    assert mesh is not None
    assert mesh.attrib.get('optimization') == 'convex_hull'


def test_fingertip_convex_hulls_rejects_near_miss_collision_name():
    module = load_module()
    manifest = {
        'prefix': 'fixed_finger_contact_convex',
        'pieces': [{'filename': 'fixed_finger_contact_convex_000.stl', 'sha256': 'a' * 64}],
    }
    near_misses = [
        'fixed_finger_contact_convex_000_extra',
        'prefix_fixed_finger_contact_convex_000_suffix',
        'gripper_fixed_joint_lump__fixed_finger_contact_convex_000',
        'gripper_fixed_joint_lump__fixed_finger_contact_convex_000_collision_trailing',
    ]
    for bad_name in near_misses:
        sdf = f'''<sdf version="1.11"><model name="so101"><link name="gripper">
          <collision name="{bad_name}"><geometry><mesh><uri>x.stl</uri></mesh></geometry></collision>
        </link></model></sdf>'''
        with pytest.raises(ValueError, match='not found in SDF'):
            module.enable_fingertip_convex_hulls(sdf, [manifest])


def test_fingertip_convex_hulls_rejects_prefixed_duplicate_collision():
    module = load_module()
    piece_name = 'fixed_finger_contact_convex_000'
    lumped_name = f'gripper_fixed_joint_lump__{piece_name}_collision'
    manifest = {
        'prefix': 'fixed_finger_contact_convex',
        'pieces': [{'filename': f'{piece_name}.stl', 'sha256': 'a' * 64}],
    }
    sdf = f'''<sdf version="1.11"><model name="so101"><link name="gripper">
      <collision name="{lumped_name}"><geometry><mesh><uri>x.stl</uri></mesh></geometry></collision>
      <collision name="{lumped_name}"><geometry><mesh><uri>x.stl</uri></mesh></geometry></collision>
    </link></model></sdf>'''
    with pytest.raises(ValueError, match='duplicate'):
        module.enable_fingertip_convex_hulls(sdf, [manifest])


# ---------------------------------------------------------------------------
# model_cache_key
# ---------------------------------------------------------------------------

def test_cache_key_changes_with_base_height():
    module = load_module()
    key_a = module.model_cache_key(
        xacro_bytes=b'<robot/>', manifests_bytes=[b'{}', b'{}'],
        base_height='0.19', collision_mode='primitives',
    )
    key_b = module.model_cache_key(
        xacro_bytes=b'<robot/>', manifests_bytes=[b'{}', b'{}'],
        base_height='0.20', collision_mode='primitives',
    )
    assert key_a != key_b


def test_cache_key_changes_with_xacro_content():
    module = load_module()
    key_a = module.model_cache_key(
        xacro_bytes=b'<robot version="1"/>', manifests_bytes=[b'{}'],
        base_height='0.19', collision_mode='primitives',
    )
    key_b = module.model_cache_key(
        xacro_bytes=b'<robot version="2"/>', manifests_bytes=[b'{}'],
        base_height='0.19', collision_mode='primitives',
    )
    assert key_a != key_b


def test_cache_key_changes_with_manifest_content():
    module = load_module()
    key_a = module.model_cache_key(
        xacro_bytes=b'<robot/>', manifests_bytes=[b'{"v":1}'],
        base_height='0.19', collision_mode='primitives',
    )
    key_b = module.model_cache_key(
        xacro_bytes=b'<robot/>', manifests_bytes=[b'{"v":2}'],
        base_height='0.19', collision_mode='primitives',
    )
    assert key_a != key_b


def test_cache_key_is_deterministic():
    module = load_module()
    kwargs = dict(
        xacro_bytes=b'<robot/>', manifests_bytes=[b'{}', b'{}'],
        base_height='0.19', collision_mode='primitives',
    )
    assert module.model_cache_key(**kwargs) == module.model_cache_key(**kwargs)


def test_prepared_sdf_cache_invalidates_when_included_xacro_changes(tmp_path, monkeypatch):
    module = load_module()
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    included = tmp_path / 'included.xacro'
    model = tmp_path / 'model.urdf.xacro'
    output = tmp_path / 'prepared.sdf'
    model.write_text('''<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="cache_test">
  <xacro:include filename="included.xacro"/>
  <xacro:cache_test_link/>
</robot>''')
    included.write_text('''<robot xmlns:xacro="http://www.ros.org/wiki/xacro">
  <xacro:macro name="cache_test_link" params="">
    <link name="body">
      <inertial><mass value="1"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial>
      <visual><geometry><box size="1 1 1"/></geometry></visual>
      <collision><geometry><box size="1 1 1"/></geometry></collision>
    </link>
  </xacro:macro>
</robot>''')

    module.prepare_simulation_model(
        model, output, base_height='0.19', manifest_paths=[]
    )
    first = output.read_text()
    included.write_text(included.read_text().replace('1 1 1', '2 2 2'))
    module.prepare_simulation_model(
        model, output, base_height='0.19', manifest_paths=[]
    )

    assert output.read_text() != first
    assert '<size>2 2 2</size>' in output.read_text()


def test_prepared_sdf_cache_invalidates_when_object_config_changes(tmp_path, monkeypatch):
    module = load_module()
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    config = tmp_path / 'object.yaml'
    model = tmp_path / 'model.urdf.xacro'
    output = tmp_path / 'prepared.sdf'
    model.write_text('''<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="cache_test">
  <xacro:arg name="object_config" default=""/>
  <xacro:property name="object" value="${xacro.load_yaml('$(arg object_config)')}"/>
  <link name="body">
    <inertial><mass value="1"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial>
    <visual><geometry><box size="${object['size']} 1 1"/></geometry></visual>
    <collision><geometry><box size="${object['size']} 1 1"/></geometry></collision>
  </link>
</robot>''')
    config.write_text('size: 1\n')

    module.prepare_simulation_model(
        model, output, base_height='0.19', manifest_paths=[], object_config=config
    )
    first = output.read_text()
    config.write_text('size: 2\n')
    module.prepare_simulation_model(
        model, output, base_height='0.19', manifest_paths=[], object_config=config
    )

    assert output.read_text() != first
    assert '<size>2 1 1</size>' in output.read_text()


def test_prepared_sdf_cache_key_tracks_mesh_content_and_writes_audit(tmp_path, monkeypatch):
    module = load_module()
    cache_home = tmp_path / 'cache'
    monkeypatch.setenv('XDG_CACHE_HOME', str(cache_home))
    mesh = tmp_path / 'body.stl'
    model = tmp_path / 'model.urdf.xacro'
    output = tmp_path / 'prepared.sdf'
    model.write_text(f'''<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="cache_test">
  <link name="body">
    <inertial><mass value="1"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial>
    <visual><geometry><mesh filename="{mesh}"/></geometry></visual>
    <collision><geometry><mesh filename="{mesh}"/></geometry></collision>
  </link>
</robot>''')
    mesh.write_text('''solid body
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 1 0
  endloop
endfacet
endsolid body
''')

    module.prepare_simulation_model(
        model, output, base_height='0.19', manifest_paths=[]
    )
    cache_root = cache_home / 'so101_gazebo_demo' / 'prepared_sdf'
    first_entries = sorted(cache_root.iterdir())
    assert len(first_entries) == 1
    audit = json.loads((first_entries[0] / 'dependencies.json').read_text())
    mesh_records = [item for item in audit['dependencies'] if item['path'] == str(mesh)]
    assert len(mesh_records) == 1
    first_mesh_sha = mesh_records[0]['sha256']

    mesh.write_text(mesh.read_text().replace('vertex 1 0 0', 'vertex 2 0 0'))
    module.prepare_simulation_model(
        model, output, base_height='0.19', manifest_paths=[]
    )
    second_entries = sorted(cache_root.iterdir())
    assert len(second_entries) == 2
    second_audit = next(
        json.loads((entry / 'dependencies.json').read_text())
        for entry in second_entries
        if entry != first_entries[0]
    )
    second_mesh_sha = next(
        item['sha256'] for item in second_audit['dependencies']
        if item['path'] == str(mesh)
    )
    assert second_mesh_sha != first_mesh_sha
