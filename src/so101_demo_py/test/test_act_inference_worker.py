"""Task 13 CLI: one reply per request, from a bundle that verifies, into a file that does not exist."""

import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.cli.act_inference_worker import main


class _Model:
    def __init__(self, chunk=None):
        self.resets = 0
        self._chunk = chunk or tuple((0.25,) * 6 for _ in range(10))

    def reset(self):
        self.resets += 1

    def infer(self, _observation):
        return self._chunk


def _bundle(tmp_path, *, prefix=2):
    (tmp_path / "policy.bin").write_bytes(b"model")
    document = {"schema_version": 1, "kind": "act_bundle",
                "model_source": {"name": "act-v1", "sha256": "a" * 64},
                "dataset_sha256": "b" * 64, "config_sha256": "c" * 64,
                "policy_path": "policy.bin",
                "policy_sha256": hashlib.sha256(b"model").hexdigest(),
                "normalization": {"split": "train", "mean": [0.0] * 6},
                "action": {"chunk_size": 10, "execution_prefix": prefix,
                           "temporal_ensembling": False, "tail_padding_mask": True}}
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(document))
    return path


def _requests(tmp_path, count=2):
    path = tmp_path / "requests.jsonl"
    path.write_text("".join(json.dumps({"sequence": index,
                                        "observation": {"sim_time_s": float(index),
                                                        "head": "h", "wrist": "w",
                                                        "state": [0.0] * 8}}) + chr(10)
                           for index in range(count)))
    return path


def test_the_worker_serves_one_reply_per_request_with_the_frozen_prefix(tmp_path, capsys):
    bundle = _bundle(tmp_path, prefix=2)
    replies = tmp_path / "replies.jsonl"
    model = _Model()
    assert main(["--bundle", str(bundle), "--requests", str(_requests(tmp_path)),
                 "--replies", str(replies), "--session-id", "s", "--attempt-id", "a"],
                loader=lambda _bundle: model) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["replies"] == 2 and printed["execution_prefix"] == 2
    served = [json.loads(line) for line in replies.read_text().splitlines()]
    assert [reply["sequence"] for reply in served] == [0, 1]
    assert all(len(reply["actions"]) == 2 for reply in served)   # the frozen prefix, not the chunk
    assert all(reply["session_id"] == "s" and reply["attempt_id"] == "a" for reply in served)
    assert model.resets == 1


def test_the_worker_refuses_before_serving_anything(tmp_path):
    bundle = _bundle(tmp_path)
    replies = tmp_path / "replies.jsonl"
    # an existing replies file is never appended to: a previous attempt's answers are not this attempt's
    replies.write_text("{}\n")
    with pytest.raises(ValueError, match="INFERENCE_REPLIES_EXIST"):
        main(["--bundle", str(bundle), "--requests", str(_requests(tmp_path)),
              "--replies", str(replies), "--session-id", "s", "--attempt-id", "a"],
             loader=lambda _bundle: _Model())
    replies.unlink()
    with pytest.raises(ValueError, match="INFERENCE_REQUESTS_MISSING"):
        main(["--bundle", str(bundle), "--requests", str(tmp_path / "absent.jsonl"),
              "--replies", str(replies), "--session-id", "s", "--attempt-id", "a"],
             loader=lambda _bundle: _Model())
    assert not replies.exists()
    with pytest.raises(ValueError, match="BUNDLE_MISSING"):
        main(["--bundle", str(tmp_path / "absent-bundle.json"),
              "--requests", str(_requests(tmp_path)), "--replies", str(replies),
              "--session-id", "s", "--attempt-id", "a"], loader=lambda _bundle: _Model())
    assert not replies.exists()


def test_the_production_loader_fails_closed(tmp_path):
    from so101_demo.cli.act_inference_worker import _policy_loader

    with pytest.raises(ValueError, match="INFERENCE_(INTERPRETER_REQUIRED|ADAPTER_UNAVAILABLE)"):
        _policy_loader({})
