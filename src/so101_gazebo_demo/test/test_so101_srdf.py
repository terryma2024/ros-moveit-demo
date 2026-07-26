from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


def test_every_srdf_joint_exists_in_generated_urdf():
    package_dir = Path(__file__).resolve().parents[1]
    description_xacro = package_dir / 'urdf' / 'so101.urdf.xacro'
    generated_urdf = subprocess.run(
        ['xacro', str(description_xacro)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    urdf_joint_names = {
        element.attrib['name']
        for element in ET.fromstring(generated_urdf).findall('joint')
    }
    srdf_joint_names = {
        element.attrib['name']
        for element in ET.parse(package_dir / 'config' / 'so101.srdf').findall(
            './/joint'
        )
    }

    unknown_joint_names = srdf_joint_names - urdf_joint_names
    assert not unknown_joint_names, (
        f'SRDF references joints missing from URDF: {sorted(unknown_joint_names)}'
    )
