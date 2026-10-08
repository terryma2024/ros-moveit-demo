"""Phase C: the per-topic transport-loss gate.

A message lost inside the episode window on a topic the episode uses makes the data INVALID (`OFFLINE_TOPIC_LOSS:<topic>`). A loss
outside the window, or on a topic the episode does not use, is recorded and never fatal. The recorder's aggregate "messages lost on
the transport layer" must be accounted for by what the topics show (otherwise it fails closed), and the gate result is part of the QC
verdict (rule version `act_data_qc_v4`, check `topic_loss_gate`).

The synthetic bag has its Teacher timeline at 1.05 s (first command) to 1.5 s (terminal), the verified reset at 1.0 s, and every topic
from 0.9 s to 1.75 s: a message lost before 1.0 s is outside the window.
"""

import copy
import json
from pathlib import Path

import pytest

from offline_synthetic_bag import build_bag
from so101_demo.act import episode_qc, qc_memo, topic_loss
from so101_demo.act.offline.scan import scan_bag

JOINT = "/joint_states"
SCENE = "/so101/simulation/scene_state"
CLOCK = "/clock"
HEAD = "/head_camera/color"
IN_WINDOW, BEFORE_WINDOW = 15, 3          # joint_states: 1.05 s and 0.93 s


def scan(tmp_path, name="raw", *, transport_lost=0, drop=(), omit=()):
    bag = build_bag(tmp_path / name, drop=drop, omit_topics=omit, transport_lost=transport_lost)
    return scan_bag(bag, transport_lost=transport_lost, scene_reads_expected=1)


def loss_reasons(report):
    return [r for r in report["reasons"] if r.startswith(("OFFLINE_TOPIC_LOSS", "OFFLINE_TRANSPORT_LOSS"))]


def test_a_complete_bag_has_no_loss_and_the_gate_document_passes(tmp_path):
    report = scan(tmp_path)
    assert report["reasons"] == [], report["reasons"]
    facts = report["topic_loss"]
    assert facts["transport_lost"] == {"reported": 0, "attributed": 0, "unattributed": 0}
    assert all(item["missing_in_window"] == 0 and item["missing_outside_window"] == 0 for item in facts["topics"].values())
    assert {JOINT, SCENE, CLOCK, HEAD, "/wrist_camera/color", "/so101/raw/planning_scene_reads"} <= set(facts["topics"])


def test_a_joint_state_lost_inside_the_window_is_a_topic_loss(tmp_path):
    report = scan(tmp_path, drop=[(JOINT, IN_WINDOW)], transport_lost=1)
    assert any(r.startswith(f"OFFLINE_TOPIC_LOSS:{JOINT} ") for r in report["reasons"]), report["reasons"]
    item = report["topic_loss"]["topics"][JOINT]
    assert item["missing_in_window"] == 1 and item["first_missing"] == [[1_040_000_000, 1_060_000_000]]


def test_a_scene_state_transition_lost_inside_the_window_is_a_topic_loss(tmp_path):
    report = scan(tmp_path, drop=[(SCENE, 10)], transport_lost=1)         # the world record at 1.020 s has no scene state
    assert any(r.startswith(f"OFFLINE_TOPIC_LOSS:{SCENE} ") for r in report["reasons"]), report["reasons"]
    assert report["topic_loss"]["topics"][SCENE]["first_missing"] == [[510, 1_020_000_000]]


def test_a_clock_message_lost_inside_the_window_is_a_topic_loss(tmp_path):
    report = scan(tmp_path, drop=[(CLOCK, 100)], transport_lost=1)         # 1.100 s
    assert any(r.startswith(f"OFFLINE_TOPIC_LOSS:{CLOCK} ") for r in report["reasons"]), report["reasons"]


def test_an_image_lost_while_its_camera_info_arrived_is_a_topic_loss(tmp_path):
    report = scan(tmp_path, drop=[(HEAD, 2)], transport_lost=1)           # 1.200 s: between the reset and the normal stop
    assert any(r.startswith(f"OFFLINE_TOPIC_LOSS:{HEAD} ") for r in report["reasons"]), report["reasons"]


def test_planning_scene_reads_fewer_in_the_bag_than_the_sidecar_made_are_a_topic_loss(tmp_path):
    bag = build_bag(tmp_path / "raw")
    report = scan_bag(bag, transport_lost=0, scene_reads_expected=2)
    assert any(r.startswith("OFFLINE_TOPIC_LOSS:/so101/raw/planning_scene_reads") for r in report["reasons"])


def test_a_loss_outside_the_window_is_recorded_not_fatal(tmp_path):
    report = scan(tmp_path, drop=[(JOINT, BEFORE_WINDOW), (SCENE, 1)], transport_lost=2)
    assert loss_reasons(report) == [], report["reasons"]
    facts = report["topic_loss"]
    assert facts["topics"][JOINT]["missing_outside_window"] == 1 and facts["topics"][JOINT]["missing_in_window"] == 0
    assert facts["topics"][SCENE]["missing_outside_window"] == 1
    assert facts["transport_lost"] == {"reported": 2, "attributed": 2, "unattributed": 0}


def test_a_transport_loss_that_no_topic_accounts_for_fails_closed(tmp_path):
    report = scan(tmp_path, transport_lost=3)
    assert "OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED: 3 of 3" in report["reasons"], report["reasons"]
    partial = scan(tmp_path, name="partial", transport_lost=3, drop=[(JOINT, BEFORE_WINDOW)])
    assert "OFFLINE_TRANSPORT_LOSS_UNATTRIBUTED: 2 of 3" in partial["reasons"], partial["reasons"]


def test_an_unknown_transport_loss_count_fails_closed(tmp_path):
    bag = build_bag(tmp_path / "raw")
    report = scan_bag(bag, transport_lost=None, scene_reads_expected=1)
    assert "OFFLINE_TRANSPORT_LOSS_UNKNOWN" in report["reasons"]


def test_a_gap_that_overlaps_a_clock_gap_is_a_producer_stall_not_a_message_loss(tmp_path):
    # the clock itself skipped 1.100 s: nothing was published at that cycle, so the joint state of that instant is a stall too. The
    # stall is judged once, on the clock (it is the clock rule's verdict); it is not counted as a lost joint state
    report = scan(tmp_path, drop=[(CLOCK, 100), (JOINT, 20)], transport_lost=0)
    topics = report["topic_loss"]["topics"]
    assert topics[CLOCK]["missing_in_window"] == 1
    assert topics[JOINT]["stalls"] == 1 and topics[JOINT]["missing_in_window"] == 0
    assert any(r.startswith(f"OFFLINE_TOPIC_LOSS:{CLOCK}") for r in report["reasons"])
    assert not any(r.startswith(f"OFFLINE_TOPIC_LOSS:{JOINT}") for r in report["reasons"])


# ---- the processor: the verdict and the document -----------------------------------------------------------------------------

def test_the_processor_makes_the_data_invalid_and_writes_the_gate_document(tmp_path):
    from test_p2_offline_processor import run

    bag = build_bag(tmp_path / "raw", drop=[(JOINT, IN_WINDOW)], transport_lost=1)
    report, out = run(tmp_path, bag)
    assert report["verdict"] == "INVALID" and any(r.startswith(f"OFFLINE_TOPIC_LOSS:{JOINT}") for r in report["reasons"])
    document = json.loads((out / topic_loss.DOCUMENT_NAME).read_bytes())
    assert document["status"] == "FAIL" and document["lost_in_window"] >= 1
    assert report["topic_loss"]["status"] == "FAIL" and report["qc"] == {"status": "NOT_RUN"}


def test_the_processor_keeps_a_valid_bag_valid_and_binds_the_gate_document(tmp_path):
    from test_p2_offline_processor import run

    bag = build_bag(tmp_path / "raw")
    report, out = run(tmp_path, bag)
    assert report["verdict"] == "VALID", report["reasons"]
    document = json.loads((out / topic_loss.DOCUMENT_NAME).read_bytes())
    assert document["status"] == "PASS" and report["topic_loss"]["sha256"] == __import__("hashlib").sha256(
        (out / topic_loss.DOCUMENT_NAME).read_bytes()).hexdigest()


def test_the_loss_facts_come_from_the_stats_or_from_the_recorders_log(tmp_path):
    from so101_demo.act.offline.processor import load_loss_facts

    (tmp_path / "raw").mkdir()
    stats = tmp_path / "raw" / "record-stats.json"
    stats.write_text(json.dumps({"transport_lost": 7, "scene_reads": {"count": 5, "errors": 0}}))
    assert load_loss_facts(tmp_path / "raw" / "bag", stats_file=stats) == {"transport_lost": 7, "scene_reads_expected": 5}
    stats.write_text(json.dumps({"scene_reads": {"count": 5, "errors": 0}}))
    assert load_loss_facts(tmp_path / "raw" / "bag", stats_file=stats)["transport_lost"] is None
    (tmp_path / "raw" / "bag-record.log").write_text(
        "[WARN] [so101_raw_recorder]: Recording stopped\n[WARN] [so101_raw_recorder]: Number of messages lost on the transport layer: 6\n")
    assert load_loss_facts(tmp_path / "raw" / "bag", stats_file=stats)["transport_lost"] == 6
    (tmp_path / "raw" / "bag-record.log").write_text("[INFO] [so101_raw_recorder]: Recording stopped\n")
    assert load_loss_facts(tmp_path / "raw" / "bag", stats_file=stats)["transport_lost"] == 0


# ---- the QC check and the rule version ---------------------------------------------------------------------------------------

IDENTITY = {"session_id": "session-1", "reset_epoch": 2, "attempt_id": "attempt-1", "lease": {}}


def write_document(root, **changes):
    topics = {JOINT: {"rule": "x", "used": True, "messages": 1, "gaps": 0, "stalls": 0, "missing_in_window": 0,
                      "missing_outside_window": 0, "diagnostic_in_window": 0, "first_missing": []}}
    document = topic_loss.build_document(identity={k: IDENTITY[k] for k in ("session_id", "reset_epoch", "attempt_id")},
                                         window={}, transport_lost={"reported": 0, "attributed": 0, "unattributed": 0},
                                         topics=topics, reasons=[])
    document.update(changes)
    path = topic_loss.document_path(root / "episode")
    path.write_bytes(topic_loss.canonical(document))
    return path


def test_the_qc_check_passes_a_clean_document_and_names_it_by_digest(tmp_path):
    path = write_document(tmp_path)
    check = topic_loss.qc_check(tmp_path / "episode", identity=IDENTITY)
    assert check["status"] == "PASS" and check["rule_version"] == "topic_loss_v1" and check["lost_in_window"] == 0
    assert check["document_sha256"] == __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    topic_loss.validate_check(check)


@pytest.mark.parametrize("change", ["missing", "garbage", "other_attempt", "old_rule", "noncanonical"])
def test_the_qc_check_refuses_an_absent_foreign_or_old_document(tmp_path, change):
    path = write_document(tmp_path)
    if change == "missing":
        path.unlink()
    elif change == "garbage":
        path.write_text("{")
    elif change == "other_attempt":
        write_document(tmp_path, identity={"session_id": "session-1", "reset_epoch": 2, "attempt_id": "other"})
    elif change == "old_rule":
        write_document(tmp_path, rule_version="topic_loss_v0")
    else:
        path.write_text(json.dumps(json.loads(path.read_text()), indent=2))
    with pytest.raises(ValueError, match="NATIVE_QC_TOPIC_LOSS"):
        topic_loss.qc_check(tmp_path / "episode", identity=IDENTITY)


def test_a_failed_document_fails_the_check_with_its_first_reason(tmp_path):
    write_document(tmp_path, status="FAIL", lost_in_window=1, reasons=["OFFLINE_TOPIC_LOSS:/joint_states missing=1"])
    check = topic_loss.qc_check(tmp_path / "episode", identity=IDENTITY)
    assert check["status"] == "FAIL" and check["reason"].startswith("OFFLINE_TOPIC_LOSS:/joint_states")


def test_the_qc_rule_version_changed_so_older_reports_and_memos_are_refused():
    assert episode_qc.QC_RULE_VERSION == "act_data_qc_v4" and episode_qc.TOPIC_LOSS_CHECK == "topic_loss_gate"
    from test_act_qc_report_publication import report

    document = report()
    assert episode_qc.validate_qc_report(document) == document
    old = copy.deepcopy(document)
    old["rule_version"] = "act_data_qc_v3"
    del old["checks"]["topic_loss_gate"]
    with pytest.raises(ValueError, match="QC_REPORT_INVALID"):
        episode_qc.validate_qc_report(old)
    missing = copy.deepcopy(document)
    del missing["checks"]["topic_loss_gate"]
    with pytest.raises(ValueError, match="QC_REPORT_INVALID"):
        episode_qc.validate_qc_report(missing)
    failing = copy.deepcopy(document)
    failing["checks"]["topic_loss_gate"].update(status="FAIL", reason="OFFLINE_TOPIC_LOSS:/joint_states", lost_in_window=1)
    with pytest.raises(ValueError, match="QC_REPORT_INVALID"):
        episode_qc.validate_qc_report(failing)           # a failed gate with a PASS verdict is inconsistent
    failing.update(status="FAIL", reason="OFFLINE_TOPIC_LOSS:/joint_states")
    assert episode_qc.validate_qc_report(failing)["status"] == "FAIL"


def test_the_memo_fingerprint_covers_the_gate_document(tmp_path):
    root = tmp_path / "attempt"
    (root / "episode").mkdir(parents=True)
    (root / "episode" / "seal.json").write_text("{}")
    scope, inputs = root / "scope.json", root / "inputs.json"
    scope.write_text("s")
    inputs.write_text("i")
    write_document(root)
    one = qc_memo.fingerprint(episode_root=root / "episode", scope=scope, inputs_manifest=inputs)
    write_document(root, lost_in_window=0, reasons=[], window={"changed": 1})
    assert qc_memo.fingerprint(episode_root=root / "episode", scope=scope, inputs_manifest=inputs) != one
    assert "topic_loss" in qc_memo.CODE_MODULES
