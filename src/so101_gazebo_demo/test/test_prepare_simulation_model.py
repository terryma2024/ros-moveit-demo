"""Behavior contract for the URDF-to-SDF VHACD preparation boundary."""

import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest


PACKAGE_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE_DIR / 'scripts' / 'prepare_simulation_model.py'


def load_module():
    assert SCRIPT.exists(), 'simulation model preparation boundary is missing'
    spec = importlib.util.spec_from_file_location('prepare_simulation_model', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sample_sdf():
    jaw_collisions = ''.join(
        f'''<collision name="moving_jaw_convex_{index:03d}"><geometry>
          <mesh><scale>1 1 1</scale><uri>piece_{index:03d}.stl</uri></mesh>
        </geometry></collision>'''
        for index in range(64)
    )
    return f'''
<sdf version="1.11">
  <model name="so101">
    <link name="gripper">
      <collision name="fixed_finger_contact">
        <geometry><box><size>0.016 0.020 0.042</size></box></geometry>
      </collision>
    </link>
    <link name="jaw">
      {jaw_collisions}
    </link>
  </model>
</sdf>
'''


def test_all_offline_jaw_pieces_are_loaded_as_convex_hulls():
    module = load_module()

    prepared = module.enable_jaw_convex_decomposition(
        sample_sdf(), max_convex_hulls=12, voxel_resolution=200000
    )
    root = ET.fromstring(prepared)
    jaw_meshes = root.findall("./model/link[@name='jaw']/collision/geometry/mesh")
    fixed_box = root.find(
        "./model/link[@name='gripper']/collision/geometry/box"
    )

    assert len(jaw_meshes) == 64
    assert {mesh.attrib['optimization'] for mesh in jaw_meshes} == {'convex_hull'}
    assert all(mesh.find('convex_decomposition') is None for mesh in jaw_meshes)
    assert fixed_box is not None


@pytest.mark.parametrize(
    'broken_sdf',
    [
        '<sdf version="1.11"><model name="so101"/></sdf>',
        '''<sdf version="1.11"><model name="so101"><link name="jaw">
             <collision name="moving_jaw_contact"><geometry><box/></geometry></collision>
           </link></model></sdf>''',
    ],
)
def test_missing_unique_jaw_mesh_fails_closed(broken_sdf):
    module = load_module()

    with pytest.raises(ValueError, match='jaw'):
        module.enable_jaw_convex_decomposition(
            broken_sdf, max_convex_hulls=12, voxel_resolution=200000
        )


def test_vhacd_parameters_reject_zero_values():
    module = load_module()

    with pytest.raises(ValueError, match='positive'):
        module.enable_jaw_convex_decomposition(
            sample_sdf(), max_convex_hulls=0, voxel_resolution=200000
        )
