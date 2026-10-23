"""The rollout and inference configs bind their logic keys into the run identity, not their file bytes.

Real: the shipped config files and their loaders. Nothing else is needed."""


import pytest
import yaml

from paths import PACKAGE_ROOT
from so101_demo.act import rollout_config, runtime_config

ROLLOUT = PACKAGE_ROOT / "config/act/rollout.yaml"
RUNTIME = PACKAGE_ROOT / "config/act/runtime.yaml"


def edited(tmp_path, source, change):
    document = yaml.safe_load(source.read_bytes())
    change(document)
    target = tmp_path / source.name
    target.write_text(yaml.safe_dump(document))
    return target


def test_comments_and_key_order_of_the_rollout_file_do_not_change_its_logic_hash(tmp_path):
    document = yaml.safe_load(ROLLOUT.read_bytes())
    reordered = tmp_path / "rollout.yaml"
    reordered.write_text("# another comment\n" + yaml.safe_dump(dict(reversed(list(document.items())))))
    assert reordered.read_bytes() != ROLLOUT.read_bytes()
    assert (rollout_config.logic_sha256(rollout_config.load_rollout_config(reordered))
            == rollout_config.logic_sha256(rollout_config.load_rollout_config(ROLLOUT)))


@pytest.mark.parametrize("change", [
    lambda d: d.update(no_motion_threshold_rad=0.006),
    lambda d: d.update(world_max_age_s=2.0),
    lambda d: d.update(session_ready_wait_s=11.0),
    lambda d: d.update(joint_limit_clamp_tolerance_rad=0.02),
    lambda d: d["camera_topics"].update(side="/side_camera/other"),
    lambda d: d["controller_actions"].update(arm="/other/follow_joint_trajectory"),
    lambda d: d.pop("joint_limit_clamp_tolerance_rad"),
    lambda d: d.update(undeclared_bundle_cameras=["head"]),
])
def test_a_logic_key_of_the_rollout_file_changes_the_hash(tmp_path, change):
    other = edited(tmp_path, ROLLOUT, change)
    assert (rollout_config.logic_sha256(rollout_config.load_rollout_config(other))
            != rollout_config.logic_sha256(rollout_config.load_rollout_config(ROLLOUT)))


@pytest.mark.parametrize("submit_lead_s,accept_timeout_s", [(0.04, 0.02), (0.03, 0.01), (0.05, 0.03)])
def test_the_controller_timing_is_outcome_risk_recorded_not_bound(tmp_path, submit_lead_s, accept_timeout_s):
    other = edited(tmp_path, ROLLOUT, lambda d: d["control"].update(submit_lead_s=submit_lead_s,
                                                                    accept_timeout_s=accept_timeout_s))
    config = rollout_config.load_rollout_config(other)
    assert rollout_config.logic_sha256(config) == rollout_config.logic_sha256(rollout_config.load_rollout_config(ROLLOUT))
    assert rollout_config.runtime_values(config) == {"control": {"submit_lead_s": submit_lead_s,
                                                                 "accept_timeout_s": accept_timeout_s}}


def test_the_inference_timeouts_are_outcome_risk_recorded_not_bound(tmp_path):
    base = runtime_config.load_runtime_config(RUNTIME)
    other = runtime_config.load_runtime_config(edited(tmp_path, RUNTIME, lambda d: d["inference"].update(
        request_timeout_s=0.8, max_reply_age_s=0.5)))
    assert runtime_config.logic_sha256(other) == runtime_config.logic_sha256(base)
    assert runtime_config.runtime_values(other)["outcome_risk"] == {"request_timeout_s": 0.8, "max_reply_age_s": 0.5}
    assert runtime_config.runtime_values(base)["runtime_only"] == {"device": "cuda", "queue_depth": 1}


def test_the_loader_still_refuses_what_it_refused(tmp_path):
    with pytest.raises(ValueError, match="RUNTIME_DEVICE_NOT_CUDA"):
        runtime_config.load_runtime_config(edited(tmp_path, RUNTIME, lambda d: d["inference"].update(device="cpu")))
    with pytest.raises(ValueError, match="ROLLOUT_CONFIG_INVALID"):
        rollout_config.load_rollout_config(edited(tmp_path, ROLLOUT, lambda d: d["control"].update(accept_timeout_s=0.5)))


# ---- the offline evaluation freeze --------------------------------------------------------------------------------------------

def logic_freeze(tmp_path, runtime_path):
    import hashlib
    import json

    from so101_demo.act.offline_evaluation import FREEZE_FIELDS_LOGIC

    paths, digests = {}, {}
    for field in FREEZE_FIELDS_LOGIC:
        if field == "runtime_logic_sha256":
            path = runtime_path
            digests[field] = runtime_config.logic_sha256(runtime_config.load_runtime_config(path))
        else:
            path = tmp_path / (field + ".json")
            path.write_text(json.dumps({"name": field}))
            digests[field] = hashlib.sha256(path.read_bytes()).hexdigest()
        paths[field] = str(path)
    (tmp_path / "freeze.json").write_text(json.dumps(digests))
    (tmp_path / "freeze-paths.json").write_text(json.dumps(paths))
    return tmp_path / "freeze.json"


def test_a_freeze_pinning_the_logic_keys_survives_a_change_of_the_timeouts(tmp_path):
    from so101_demo.act.offline_evaluation import load_freeze

    work = tmp_path / "work"
    work.mkdir()
    runtime = work / "runtime.yaml"
    shutil_copy(RUNTIME, runtime)
    freeze = logic_freeze(work, runtime)
    assert "runtime_logic_sha256" in load_freeze(freeze) and "runtime_config_sha256" not in load_freeze(freeze)
    runtime.write_text(runtime.read_text().replace("request_timeout_s: 0.5", "request_timeout_s: 0.9"))
    assert "runtime_logic_sha256" in load_freeze(freeze)          # the timeout is outcome-risk, not bound


def test_a_freeze_pinning_the_logic_keys_refuses_a_change_of_a_logic_key(tmp_path):
    from so101_demo.act.offline_evaluation import load_freeze

    work = tmp_path / "work"
    work.mkdir()
    runtime = work / "runtime.yaml"
    shutil_copy(RUNTIME, runtime)
    freeze = logic_freeze(work, runtime)
    runtime.write_text(runtime.read_text().replace("kind: act_runtime", "kind: act_other"))
    with pytest.raises(ValueError, match="FREEZE_DIGEST_MISMATCH"):
        load_freeze(freeze)


def test_a_freeze_naming_both_runtime_fields_is_invalid(tmp_path):
    import json

    from so101_demo.act.offline_evaluation import load_freeze

    work = tmp_path / "work"
    work.mkdir()
    runtime = work / "runtime.yaml"
    shutil_copy(RUNTIME, runtime)
    freeze = logic_freeze(work, runtime)
    document = json.loads(freeze.read_text())
    document["runtime_config_sha256"] = "a" * 64
    freeze.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="FREEZE_INVALID"):
        load_freeze(freeze)


def shutil_copy(source, target):
    target.write_bytes(source.read_bytes())
