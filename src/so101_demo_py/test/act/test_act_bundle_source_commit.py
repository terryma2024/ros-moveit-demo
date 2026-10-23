"""The bundle's `model_source` may name the commit of the code that trained it; a bundle without one stays valid."""

import subprocess

import pytest

from test_act_bundle import _write_bundle

COMMIT = "0123456789abcdef0123456789abcdef01234567"


def test_a_bundle_with_and_without_a_source_commit_loads(tmp_path):
    from so101_demo.act.bundle import load_bundle

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    old, _ = _write_bundle(tmp_path / "a")
    assert "source_commit" not in load_bundle(old)["model_source"]
    new, _ = _write_bundle(tmp_path / "b", model_source={"name": "act-v1", "sha256": "a" * 64, "source_commit": COMMIT})
    assert load_bundle(new)["model_source"]["source_commit"] == COMMIT


@pytest.mark.parametrize("commit", ["", "abc", COMMIT.upper(), COMMIT + "0", None, 7, "g" * 40])
def test_a_malformed_source_commit_is_refused(tmp_path, commit):
    from so101_demo.act.bundle import load_bundle

    path, _ = _write_bundle(tmp_path, model_source={"name": "act-v1", "sha256": "a" * 64, "source_commit": commit})
    with pytest.raises(ValueError, match="BUNDLE_INVALID"):
        load_bundle(path)


def test_the_trainer_records_the_commit_and_refuses_a_malformed_one(tmp_path):
    from so101_demo.adapters.act.lerobot import train_with_lerobot

    def train(config, dataset, target):
        (target / "policy.safetensors").write_bytes(b"w")
        return {}

    action = {"chunk_size": 10, "execution_prefix": 1, "temporal_ensembling": False, "tail_padding_mask": True}
    dataset = tmp_path / "ds"
    dataset.mkdir()
    (dataset / "export-manifest.json").write_text("{}")
    document = train_with_lerobot(action, dataset, tmp_path / "out", requirement_sha256="a" * 64, train=train,
                                  source_commit=COMMIT)
    assert document["model_source"]["source_commit"] == COMMIT
    plain = train_with_lerobot(action, dataset, tmp_path / "out2", requirement_sha256="a" * 64, train=train)
    assert set(plain["model_source"]) == {"name", "sha256"}
    with pytest.raises(ValueError, match="LEROBOT_SOURCE_COMMIT_INVALID"):
        train_with_lerobot(action, dataset, tmp_path / "out3", requirement_sha256="a" * 64, train=train, source_commit="x")


def _repo(path):
    git = lambda *a: subprocess.run(["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True,
                                    capture_output=True, text=True).stdout.strip()
    path.mkdir()
    git("init", "-q")
    (path / "src").mkdir()
    (path / "src" / "a.py").write_text("x = 1\n")
    git("add", ".")
    git("commit", "-q", "-m", "c")
    return git


def test_a_clean_checkout_gives_its_head_and_a_dirty_src_tree_is_refused(tmp_path):
    from so101_demo.cli.act_train import source_commit_of

    git = _repo(tmp_path / "repo")
    assert source_commit_of(tmp_path / "repo") == git("rev-parse", "HEAD")
    (tmp_path / "repo" / "other.txt").write_text("outside src")
    assert source_commit_of(tmp_path / "repo") == git("rev-parse", "HEAD")        # only src counts
    (tmp_path / "repo" / "src" / "a.py").write_text("x = 2\n")
    with pytest.raises(ValueError, match="TRAINING_SOURCE_TREE_DIRTY"):
        source_commit_of(tmp_path / "repo")
    (tmp_path / "repo" / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "repo" / "src" / "new.py").write_text("untracked")
    with pytest.raises(ValueError, match="TRAINING_SOURCE_TREE_DIRTY"):
        source_commit_of(tmp_path / "repo")


def test_a_path_that_is_not_a_checkout_is_refused(tmp_path):
    from so101_demo.cli.act_train import source_commit_of

    with pytest.raises(ValueError, match="TRAINING_SOURCE_CHECKOUT_UNREADABLE"):
        source_commit_of(tmp_path)
