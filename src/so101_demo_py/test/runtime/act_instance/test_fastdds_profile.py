"""The Fast DDS collection profile: the file sets exactly the two writer times and the environment entry names its install path."""

from pathlib import Path
import xml.etree.ElementTree as ElementTree

from so101_demo.runtime.act_instance import identity

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
PROFILE = PACKAGE_ROOT / 'config/dds/fastdds-collection.xml'
NAMESPACE = '{http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles}'


def test_the_profile_is_one_default_publisher_with_exactly_the_two_times():
    root = ElementTree.parse(PROFILE).getroot()
    assert root.tag == NAMESPACE + 'profiles' and len(root) == 1
    publisher = root[0]
    assert publisher.tag == NAMESPACE + 'publisher' and publisher.get('is_default_profile') == 'true'
    assert [child.tag for child in publisher] == [NAMESPACE + 'times']
    times = {child.tag.removeprefix(NAMESPACE): {part.tag.removeprefix(NAMESPACE): part.text for part in child}
             for child in publisher[0]}
    assert times == {'heartbeatPeriod': {'sec': '0', 'nanosec': '20000000'},
                     'nackResponseDelay': {'sec': '0', 'nanosec': '1000000'}}


def test_the_environment_entry_is_the_installed_path_and_nothing_else():
    assert identity.fastdds_profile_environment('/act/install') == [
        'FASTRTPS_DEFAULT_PROFILES_FILE=/act/install/share/so101_demo_py/config/dds/fastdds-collection.xml']
    # setup.py installs every file under config/ to share/so101_demo_py/config/...
    assert identity.FASTDDS_PROFILE_RELATIVE == 'share/so101_demo_py/' + PROFILE.relative_to(PACKAGE_ROOT).as_posix()
