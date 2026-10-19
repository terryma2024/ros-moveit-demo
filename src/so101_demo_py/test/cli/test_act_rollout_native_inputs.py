"""`load_inputs`: everything the native rollout takes from outside, bound and checked before any process starts.

Fixtures only: the frozen-inputs loader, the bundle loader, the recorder policy and the activation check are replaced by fakes
that return the documents the real ones return; the rollout config, the runtime config and the endpoint policy are the shipped
package files. Nothing is read from the evidence root or from a host path.
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.cli import act_rollout_native as native
from paths import PACKAGE_ROOT

from test_act_rollout_native import _scenes

BUNDLE_SIDE_WRIST = {"policy_sha256": "9" * 64, "normalization": {
    "observation": {"cameras": ["side", "wrist"], "state_dim": 6}, "image_shape": [3, 480, 640],
    "state_mean": [0.0] * 6}}
BUNDLE_LEGACY = {"policy_sha256": "8" * 64, "normalization": {"image_shape": [3, 480, 640], "state_mean": [0.0] * 8}}
SUBSTITUTION = {"substituted_by": "contact_activation_receipt", "path": "r", "sha256": "a" * 64,
                "policy_fingerprint": "b" * 64, "ruling": "x"}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Fixture:
    """Files on disk plus the patched loaders for one `load_inputs` call."""

    def __init__(self, tmp_path, monkeypatch, bundle=BUNDLE_SIDE_WRIST, endpoint_sha_matches=True):
        from so101_demo.act.teacher_endpoint import load_teacher_endpoint_policy

        self.root = tmp_path
        (tmp_path / "bundle").mkdir()
        (tmp_path / "bundle" / "bundle.json").write_bytes(json.dumps(bundle).encode())
        (tmp_path / "inputs-manifest.json").write_bytes(b'{"frozen": "inputs"}')
        (tmp_path / "snapshot" / "config" / "act").mkdir(parents=True)
        endpoint_text = (PACKAGE_ROOT / "config/act/teacher_endpoint.yaml").read_bytes()
        (tmp_path / "snapshot" / "config" / "act" / "teacher_endpoint.yaml").write_bytes(endpoint_text)
        self.endpoint = load_teacher_endpoint_policy(endpoint_text)
        (tmp_path / "scenes.json").write_text(json.dumps(_scenes("rollout_standard", 4)))
        (tmp_path / "receipt.json").write_bytes(b"{}")
        (tmp_path / "proposal.json").write_bytes(b"{}")
        self.frozen = {
            "source_commit": "abc123def456",
            "teacher_execution_policy": {"values": {
                "execution_deadline_s": 180.0, "state_unavailable_stop_s": 1.0, "state_max_age_s": 0.5,
                "arm_stop_wait_s": 1.0, "arm_stop_velocity_rad_s": 0.002}},
            "teacher_endpoint": {"policy_sha256": self.endpoint["policy_sha256"] if endpoint_sha_matches else "0" * 64,
                                 "values": self.endpoint},
            "runtime_policy": {"rgb_sync": {"max_age_s": 0.1, "max_skew_s": 0.1}},
            "roles": {"contact_activation": {"path": "receipt.json"}, "contact_proposal": {"path": "proposal.json"}}}
        self.snapshot = {"snapshot_sha256": "5" * 64, "targets": {"kind": "ACT_ENDPOINT_TARGETS"}}
        self.activation_calls = []
        self.recorder_policy = {"ready_timeout_s": 30.0}
        monkeypatch.setattr("so101_demo.act.frozen_runtime_inputs.load_teacher_frozen_inputs",
                            lambda path: (self.frozen, self.snapshot, tmp_path / "snapshot"))
        monkeypatch.setattr("so101_demo.act.frozen_runtime_inputs.load_recorder_frozen_policy",
                            lambda path: self.recorder_policy)
        monkeypatch.setattr("so101_demo.act.bundle.load_bundle", lambda path: json.loads(Path(path).read_bytes()))
        monkeypatch.setattr("so101_demo.act.rollout_activation.contact_activation_substitution",
                            lambda receipt, proposal: self.activation_calls.append((receipt, proposal)) or SUBSTITUTION)

    def args(self, **changes):
        values = dict(inputs_manifest=self.root / "inputs-manifest.json", rollout_config=PACKAGE_ROOT / "config/act/rollout.yaml",
                      bundle_dir=self.root / "bundle", scenes=self.root / "scenes.json",
                      contact_activation_receipt=None, contact_proposal=None,
                      runtime_config=PACKAGE_ROOT / "config/act/runtime.yaml", install_prefix=Path("/opt/gate-install"))
        values.update(changes)
        return SimpleNamespace(**values)


def test_a_side_wrist_bundle_gives_a_headless_neckless_observation_and_binds_every_input(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path, monkeypatch)
    inputs = native.load_inputs(fixture.args())
    assert inputs.observation == {"cameras": ("side", "wrist"), "state_dim": 6, "image_shape": [480, 640, 3],
                                  "source": "bundle"}
    assert "head" not in inputs.observation["cameras"]
    identity = inputs.identity
    assert identity["bundle_sha256"] == _sha(tmp_path / "bundle" / "bundle.json")
    assert identity["policy_sha256"] == BUNDLE_SIDE_WRIST["policy_sha256"]
    assert identity["inputs_manifest_sha256"] == _sha(tmp_path / "inputs-manifest.json")
    assert identity["runtime_yaml_sha256"] == _sha(PACKAGE_ROOT / "config/act/runtime.yaml")
    assert identity["rollout_yaml_sha256"] == _sha(PACKAGE_ROOT / "config/act/rollout.yaml")
    assert identity["snapshot_sha256"] == "5" * 64 and identity["source_commit"] == "abc123def456"
    assert identity["gate_install"] == "/opt/gate-install" and identity["scenes_sha256"] == inputs.scenes["manifest_sha256"]
    assert inputs.substitution == SUBSTITUTION and inputs.bundle is not None and inputs.bundle_dir == tmp_path / "bundle"
    assert inputs.recorder_policy == {"ready_timeout_s": 30.0} and inputs.snapshot_targets == fixture.snapshot["targets"]
    assert inputs.settings.execution_deadline_s == 180.0 and inputs.settings.ready_wait_s > 0
    assert inputs.timing["stop_timeout_s"] == 1.0 and inputs.endpoint_policy["policy_sha256"] == fixture.endpoint["policy_sha256"]


def test_the_activation_receipt_defaults_to_the_frozen_inputs_and_can_be_named(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path, monkeypatch)
    native.load_inputs(fixture.args())
    assert fixture.activation_calls == [(tmp_path / "receipt.json", tmp_path / "proposal.json")]
    other = tmp_path / "other-receipt.json"
    other.write_bytes(b"{}")
    native.load_inputs(fixture.args(contact_activation_receipt=other, contact_proposal=tmp_path / "proposal.json"))
    assert fixture.activation_calls[-1] == (other, tmp_path / "proposal.json")


def test_a_bundle_that_declares_no_observation_gets_the_configured_legacy_cameras(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path, monkeypatch, bundle=BUNDLE_LEGACY)
    inputs = native.load_inputs(fixture.args())
    assert inputs.observation["cameras"] == ("head", "wrist") and inputs.observation["state_dim"] == 8
    assert inputs.observation["source"] == "rollout_config.undeclared_bundle_cameras"


@pytest.mark.parametrize("shape", [[480, 640, 3], [3, 480], "x", [1, 480, 640]])
def test_a_bundle_image_shape_that_is_not_channels_first_rgb_is_refused(tmp_path, monkeypatch, shape):
    bundle = json.loads(json.dumps(BUNDLE_SIDE_WRIST))
    bundle["normalization"]["image_shape"] = shape
    with pytest.raises(ValueError, match="ROLLOUT_BUNDLE_IMAGE_SHAPE_INVALID"):
        native.load_inputs(Fixture(tmp_path, monkeypatch, bundle=bundle).args())


def test_a_snapshot_endpoint_policy_that_is_not_the_frozen_one_is_refused(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="ROLLOUT_ENDPOINT_POLICY_MISMATCH"):
        native.load_inputs(Fixture(tmp_path, monkeypatch, endpoint_sha_matches=False).args())


def test_a_camera_without_a_topic_is_refused_while_the_inputs_load_not_after_the_stack_started(tmp_path, monkeypatch):
    bundle = json.loads(json.dumps(BUNDLE_SIDE_WRIST))
    bundle["normalization"]["observation"]["cameras"] = ["side", "elbow"]
    with pytest.raises(ValueError, match="ROLLOUT_CAMERA_TOPIC_UNMAPPED: elbow"):
        native.load_inputs(Fixture(tmp_path, monkeypatch, bundle=bundle).args())


def test_a_damaged_scene_list_is_refused(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path, monkeypatch)
    document = json.loads((tmp_path / "scenes.json").read_text())
    document["groups"]["rollout_standard"][0]["xy"] = [9.0, 9.0]            # changes the content, not the recorded hash
    (tmp_path / "scenes.json").write_text(json.dumps(document))
    with pytest.raises(ValueError, match="ROLLOUT_SCENES"):
        native.load_inputs(fixture.args())


def test_a_bundle_whose_cameras_and_state_match_no_known_rig_is_refused_before_any_process_starts(tmp_path, monkeypatch):
    bundle = json.loads(json.dumps(BUNDLE_SIDE_WRIST))
    bundle["normalization"]["observation"]["state_dim"] = 8
    bundle["normalization"]["state_mean"] = [0.0] * 8
    with pytest.raises(ValueError, match="RIG_PROFILE_UNKNOWN"):
        native.load_inputs(Fixture(tmp_path, monkeypatch, bundle=bundle).args())
