"""A test that talks over a real ROS graph never names a domain: it takes `isolated_ros_domain` (test/conftest.py).

Two tests on one domain at the same time see each other's publishers and services; xdist runs them at once, so a fixed number is a race
that only shows under load (ACT_STACK_SOURCE_REJECTED, a subscription count of 1 where 0 was expected). The fixture gives each worker its own.
"""

from pathlib import Path
import re

ROOTS = (Path(__file__).resolve().parents[1], Path(__file__).resolve().parents[2] / "so101_teleop" / "test")
FIXED = re.compile(
    r"""setenv\(\s*["']ROS_DOMAIN_ID["']\s*,\s*["']?\d"""           # monkeypatch.setenv("ROS_DOMAIN_ID", "231")
    r"""|rclpy\.init\([^)\n]*domain_id\s*=\s*\d"""                   # rclpy.init(context=c, domain_id=231)
    r"""|["']--ros-domain-id["']\s*,\s*["']?\d"""                     # the command line of a live check
    r"""|^\s*\w*DOMAIN\w*\s*=\s*["']?\d""",                          # DOMAIN = "231"
    re.MULTILINE)


def live_graph_tests():
    return sorted(path for root in ROOTS for path in root.rglob("test_*.py")
                  if path != Path(__file__).resolve() and "rclpy" in path.read_text(encoding="utf-8"))


def test_the_pattern_finds_each_way_of_naming_a_domain():
    for text in ('monkeypatch.setenv("ROS_DOMAIN_ID", "231")', "monkeypatch.setenv('ROS_DOMAIN_ID', 5)", "rclpy.init(context=c, domain_id=7)",
                 'DOMAIN = "227"', "DOMAIN_ID = 231", 'argv = ["--ros-domain-id", "230"]'):
        assert FIXED.search(text), text
    for text in ("rclpy.init(domain_id=isolated_ros_domain)", 'ros_domain_id=int(os.environ["ROS_DOMAIN_ID"])',
                 'monkeypatch.setenv("ROS_DOMAIN_ID", str(domain))', "REQUIRED_DOMAIN = [0.1]", 'env = {"ROS_DOMAIN_ID": "181"}', "StackReadinessSession(ros_domain_id=3)"):
        assert not FIXED.search(text), text


def test_no_test_that_uses_rclpy_names_a_ros_domain():
    found = [f"{path.relative_to(path.parents[3])}:{text.count(chr(10), 0, match.start()) + 1}: {match.group().strip()}"
             for path in live_graph_tests() for text in [path.read_text(encoding="utf-8")]
             for match in FIXED.finditer(text)]
    assert not found, "\n".join(found)
