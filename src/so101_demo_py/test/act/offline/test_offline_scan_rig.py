"""The raw-bag scan judges the cameras (and the neck) of the rig it is given: rig v1 as before, rig v2 with a side camera and no neck.

The synthetic bag is the one `test_topic_loss_gate.py` scans; `build_bag(rig=...)` writes the rig's own camera topics and, for a rig
without a neck, no neck controller state at all.
"""

from offline_synthetic_bag import build_bag
from so101_demo.act.offline.scan import scan_bag
from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_RIG


def scan(tmp_path, rig):
    return scan_bag(build_bag(tmp_path / "raw", rig=rig), transport_lost=0, scene_reads_expected=1, rig=rig)


def test_a_complete_side_wrist_rig_bag_scans_clean_and_judges_no_head_and_no_neck(tmp_path):
    report = scan(tmp_path, SIDE_WRIST_RIG)
    assert report["reasons"] == [], report["reasons"]
    assert report["camera_grid"]["side_wrist_equal"] is True and "head_wrist_equal" not in report["camera_grid"]
    topics = set(report["topic_loss"]["topics"])
    assert {"/side_camera/color", "/side_camera/camera_info", "/wrist_camera/color", "/wrist_camera/camera_info"} <= topics
    assert not any("head" in topic or "neck" in topic for topic in set(report["continuity"]) | set(report["counts"]) | topics)


def test_the_head_wrist_scan_of_a_head_wrist_bag_still_has_the_head_wrist_grid_and_the_neck_topic(tmp_path):
    report = scan(tmp_path, HEAD_WRIST_RIG)
    assert report["reasons"] == [], report["reasons"]
    assert report["camera_grid"]["head_wrist_equal"] is True
    assert "/neck_controller/controller_state" in report["continuity"]


def test_a_head_wrist_scan_of_a_side_wrist_bag_names_the_missing_head_and_neck_topics(tmp_path):
    """The rig is the reader's: a v2 bag read as v1 is refused, not silently accepted."""
    bag = build_bag(tmp_path / "raw", rig=SIDE_WRIST_RIG)
    report = scan_bag(bag, transport_lost=0, scene_reads_expected=1)
    assert "OFFLINE_BAG_TOPIC_MISSING: /head_camera/color" in report["reasons"]
    assert "OFFLINE_BAG_TOPIC_MISSING: /neck_controller/controller_state" in report["reasons"]


def test_a_missing_side_image_makes_the_pair_differ_and_is_a_topic_loss(tmp_path):
    bag = build_bag(tmp_path / "raw", rig=SIDE_WRIST_RIG, drop=[("/side_camera/color", 2)], transport_lost=1)
    report = scan_bag(bag, transport_lost=1, scene_reads_expected=1, rig=SIDE_WRIST_RIG)
    assert "OFFLINE_CAMERA_PAIR_STAMPS_DIFFER" in report["reasons"], report["reasons"]
    assert report["camera_grid"]["side_wrist_equal"] is False
    assert any(reason.startswith("OFFLINE_TOPIC_LOSS:/side_camera/color ") for reason in report["reasons"]), report["reasons"]


def test_a_side_camera_info_lost_with_both_images_present_is_diagnostic_only(tmp_path):
    bag = build_bag(tmp_path / "raw", rig=SIDE_WRIST_RIG, drop=[("/side_camera/camera_info", 2)], transport_lost=1)
    report = scan_bag(bag, transport_lost=1, scene_reads_expected=1, rig=SIDE_WRIST_RIG)
    assert "OFFLINE_CAMERA_PAIR_STAMPS_DIFFER" not in report["reasons"], report["reasons"]
    grid = report["camera_grid"]
    assert grid["side_wrist_equal"] is True and grid["paired_on"] == "images" and grid["camera_info_pair_equal"] is False
