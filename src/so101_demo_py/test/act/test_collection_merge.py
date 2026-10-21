"""`act_merge_collections`: the sealed frozen indexes of several formal campaigns become one index and one export manifest.

Real: the merge, the seal readback, the real `bundle._index` and the real export resolution. Controlled: the sealed run roots are
small fixture directories sealed here in the format of the evidence seal tool (`SEALED.json` plus a manifest of path, bytes, sha256);
the committed episodes come from the export fixtures of `test_act_bundle_processed`, whose two verifier readbacks are replaced."""

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from so101_demo.act.collection_merge import MergeRefused, MergeSource, merge_collections, sha256_file
from so101_demo.cli import act_merge_collections as cli

IDENTITY = dict(source_sha256="1" * 64, runtime_config_sha256="2" * 64, collection_config_sha256="3" * 64,
                contact_policy_fingerprint="4" * 64, image_source_install=dict(shard="s", inference="i"))


def scene_list(path, ids, splits=None):
    rows = [dict(scene_id=scene, split=(splits or {}).get(scene, "train")) for scene in ids]
    path.write_text(json.dumps(dict(kind="ACT_CONTAINER_SCENE_MANIFEST", scenarios=rows)))
    return path


def seal(root: Path):
    """Seal a run root like the evidence tool: a manifest outside the root and SEALED.json inside."""
    entries = []
    for directory, _, names in os.walk(root):
        for name in sorted(names):
            path = Path(directory, name)
            if name != "SEALED.json":
                entries.append(dict(path=str(path.relative_to(root)), bytes=path.stat().st_size, sha256=sha256_file(path)))
    manifest = root.parent / (root.name + ".seal-manifest.jsonl")
    manifest.write_text("\n".join(json.dumps(entry, sort_keys=True) for entry in sorted(entries, key=lambda e: e["path"])) + "\n")
    (root / "SEALED.json").write_text(json.dumps(dict(manifest=str(manifest), manifest_sha256=sha256_file(manifest),
                                                      bytes=sum(e["bytes"] for e in entries))))


def report(path, *, identity=None, status="QUALIFIED", gpu="GPU-a", model="RTX 5080", reasons=()):
    document = dict(kind="ACT_PARALLEL_COLLECTION_QUALIFICATION", status=status, reasons=list(reasons),
                    controlled_identity=dict(identity or IDENTITY), environment=dict(gpu_uuid=gpu, gpu_model=model))
    path.write_text(json.dumps(document, sort_keys=True))
    return path


def make_source(tmp_path, name, scenes, committed=None, *, host=None, report_edit=None, extra_task=None, seal_it=True,
                attempts=None, without_evidence=()):
    """A sealed run root holding collection-index.json: `scenes` were collected, `committed` of them became episodes."""
    root = tmp_path / name
    root.mkdir()
    committed = list(scenes if committed is None else committed)
    episodes = [dict(kind="ACT_COMMITTED_EPISODE", schema_version=4, scene_id=scene, marker=name + scene) for scene in committed]
    tasks = [dict(scene_id=scene, task_id="task-" + scene, **(attempts or {}).get(scene, {})) for scene in scenes]
    if extra_task:
        tasks.append(dict(scene_id=extra_task, task_id="task-extra"))
    (root / "collection-index.json").write_text(json.dumps(dict(
        schema_version=4, kind="act_collection_frozen_index", qualification=False, campaign_id=name, scene_count=len(scenes),
        collected_tasks=tasks, committed_episodes=episodes, scenes_without_evidence=list(without_evidence))))
    (root / "host").mkdir()
    (root / "host/other.json").write_text(json.dumps(dict(name=name)))
    if seal_it:
        seal(root)
    kwargs = dict(report_edit or {})
    return MergeSource(index=root / "collection-index.json", qualification_report=report(tmp_path / (name + "-report.json"), **kwargs),
                       host=host or name)


@pytest.fixture
def two(tmp_path):
    ids = [f"s{n:02d}" for n in range(6)]
    formal = scene_list(tmp_path / "formal.scenes.json", ids, {"s04": "validation", "s05": "offline_test"})
    a = make_source(tmp_path, "a", ids[:3], ids[:2], report_edit=dict(gpu="GPU-a"))
    b = make_source(tmp_path, "b", ids[2:], report_edit=dict(gpu="GPU-b", model="RTX 5060 Ti"))
    return tmp_path, formal, a, b


def refused(code, *args, **kwargs):
    with pytest.raises(MergeRefused) as error:
        merge_collections(*args, **kwargs)
    assert str(error.value).startswith(code), str(error.value)


def test_two_sealed_campaigns_merge_into_one_index_that_keeps_every_episode_as_it_was(two):
    tmp_path, formal, a, b = two
    index, manifest = merge_collections([a, b], formal, "20261021T120000Z")
    sources = [json.loads(Path(s.index).read_bytes()) for s in (a, b)]
    assert index["kind"] == "act_collection_frozen_index" and index["qualification"] is False
    assert index["campaign_id"] == "merged-20261021T120000Z" and index["scene_count"] == 6
    assert index["committed_episodes"] == sources[0]["committed_episodes"] + sources[1]["committed_episodes"]
    assert [row["scene_id"] for row in manifest["episodes"]] == ["s00", "s01", "s02", "s03", "s04", "s05"]
    assert {row["scene_id"]: row["split"] for row in manifest["episodes"]} == {
        "s00": "train", "s01": "train", "s02": "train", "s03": "train", "s04": "validation", "s05": "offline_test"}
    assert all(row["status"] == "PASSED" for row in manifest["episodes"])
    records = index["provenance"]["sources"]
    assert [(r["host"], r["gpu_uuid"], r["gpu_model"]) for r in records] == [("a", "GPU-a", "RTX 5080"), ("b", "GPU-b", "RTX 5060 Ti")]
    for record, source in zip(records, (a, b)):
        assert record["index_sha256"] == sha256_file(source.index)
        assert record["qualification_report_sha256"] == sha256_file(source.qualification_report)
        assert record["seal_manifest_sha256"] and record["sealed_files"] == 2
    assert [r["scenes"] for r in records] == [3, 4] and [r["committed"] for r in records] == [2, 4]
    assert index["provenance"]["formal_list_sha256"] == sha256_file(formal)


def test_the_gpu_is_the_environment_so_it_does_not_make_the_identities_differ(two):
    tmp_path, formal, a, b = two
    document = json.loads(Path(a.qualification_report).read_bytes())
    document["controlled_identity"]["gpu_uuid"] = "GPU-a"              # identity version 1 keeps the uuid in the identity
    Path(a.qualification_report).write_text(json.dumps(document))
    merge_collections([a, b], formal, "20261021T120000Z")


def test_fewer_than_two_sources_are_refused(two):
    tmp_path, formal, a, b = two
    refused("MERGE_SOURCES_TOO_FEW", [a], formal, "20261021T120000Z")


def test_an_identity_that_differs_is_refused(tmp_path):
    ids = ["s0", "s1"]
    formal = scene_list(tmp_path / "f.json", ids)
    a = make_source(tmp_path, "a", ["s0"])
    for key, value in (("source_sha256", "9" * 64), ("contact_policy_fingerprint", "8" * 64),
                       ("image_source_install", dict(shard="x", inference="i"))):
        other = dict(IDENTITY, **{key: value})
        b = make_source(tmp_path, "b" + key[:4], ["s1"], report_edit=dict(identity=other))
        refused("MERGE_IDENTITY_MISMATCH", [a, b], formal, "20261021T120000Z")


def test_scene_sets_that_overlap_are_refused(tmp_path):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1", "s2"])
    a = make_source(tmp_path, "a", ["s0", "s1"])
    b = make_source(tmp_path, "b", ["s1", "s2"])
    refused("MERGE_SCENE_OVERLAP", [a, b], formal, "20261021T120000Z")


def test_a_scene_collected_but_not_committed_does_not_claim_the_scene(tmp_path):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1", "s2"])
    a = make_source(tmp_path, "a", ["s0", "s1"], committed=["s0"])
    b = make_source(tmp_path, "b", ["s1", "s2"])                    # the supplement commits the scene a did not
    index, manifest = merge_collections([a, b], formal, "20261021T120000Z")
    assert [row["scene_id"] for row in manifest["episodes"]] == ["s0", "s1", "s2"]


def test_a_scene_committed_by_two_sources_is_refused_even_when_one_also_has_an_invalid_attempt(tmp_path):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1", "s2"])
    a = make_source(tmp_path, "a", ["s0", "s1"])
    b = make_source(tmp_path, "b", ["s1", "s2"])
    refused("MERGE_SCENE_OVERLAP", [a, b], formal, "20261021T120000Z")


def test_a_hundred_plus_three_merge_passes_when_the_first_source_collected_the_three_as_invalid(tmp_path):
    ids = [f"frm-{n:03d}" for n in range(103)]
    bad = ["frm-018", "frm-062", "frm-094"]
    formal = scene_list(tmp_path / "f.json", ids)
    attempts = {"frm-018": dict(result_status="INVALID", act_data_status="INVALID", act_data_reason="QC_RATE"),
                "frm-062": dict(result_status="INVALID", act_data_status="INVALID", act_data_reason="CONTACT"),
                "frm-094": dict(result_status="FAILED", act_data_status="INVALID", act_data_reason="TIMEOUT")}
    a = make_source(tmp_path, "a", ids, committed=[s for s in ids if s not in bad], attempts=attempts,
                    without_evidence=[dict(scene_id="frm-094", state="FAULT", reason="PROCESSING")], report_edit=dict(gpu="GPU-a"))
    b = make_source(tmp_path, "b", bad, report_edit=dict(gpu="GPU-b"))
    index, manifest = merge_collections([a, b], formal, "20261021T120000Z")
    assert len(index["committed_episodes"]) == 103 and sorted(r["scene_id"] for r in manifest["episodes"]) == sorted(ids)
    records = index["provenance"]["sources"]
    assert [r["committed"] for r in records] == [100, 3]
    skipped = {entry["host"]: entry for entry in manifest["non_committed_attempts"]}
    assert skipped["b"]["attempts"] == []
    rows = skipped["a"]["attempts"]
    assert [(r["scene_id"], r["status"], r["reason"]) for r in rows if r["from"] == "collected_tasks"] == [
        ("frm-018", "INVALID", "QC_RATE"), ("frm-062", "INVALID", "CONTACT"), ("frm-094", "INVALID", "TIMEOUT")]
    assert [(r["scene_id"], r["status"], r["reason"]) for r in rows if r["from"] == "scenes_without_evidence"] == [
        ("frm-094", "FAULT", "PROCESSING")]
    assert skipped["a"]["index_sha256"] == sha256_file(a.index)


def test_the_merged_index_format_is_the_one_it_was(two):
    tmp_path, formal, a, b = two
    index, manifest = merge_collections([a, b], formal, "20261021T120000Z")
    assert sorted(index) == ["campaign_id", "committed_episodes", "kind", "provenance", "qualification", "scene_count", "schema_version"]
    assert sorted(index["provenance"]) == ["controlled_identity_sha256", "created", "formal_list", "formal_list_sha256", "sources"]
    assert sorted(index["provenance"]["sources"][0]) == sorted([
        "index", "index_sha256", "campaign_id", "index_schema_version", "run_root", "seal_manifest_sha256", "sealed_files", "host",
        "gpu_uuid", "gpu_model", "qualification_report", "qualification_report_sha256", "scenes", "committed"])
    assert sorted(manifest) == ["episodes", "non_committed_attempts"]
    assert all(sorted(row) == ["scene_id", "split", "status"] for row in manifest["episodes"])


def test_a_gap_after_the_committed_only_rule_is_refused(tmp_path):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1", "s2"])
    a = make_source(tmp_path, "a", ["s0", "s1"], committed=["s0"])      # s1 was collected but never committed anywhere
    b = make_source(tmp_path, "b", ["s2"])
    refused("MERGE_UNION_NOT_FORMAL_LIST", [a, b], formal, "20261021T120000Z")


def test_an_extra_committed_scene_after_the_committed_only_rule_is_refused(tmp_path):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1"])
    a = make_source(tmp_path, "a", ["s0"])
    b = make_source(tmp_path, "b", ["s1", "stranger"], committed=["s1", "stranger"])
    refused("MERGE_SCENE_NOT_IN_FORMAL_LIST", [a, b], formal, "20261021T120000Z")


def test_a_scene_outside_the_formal_list_that_was_only_collected_does_not_matter(tmp_path):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1"])
    a = make_source(tmp_path, "a", ["s0"])
    b = make_source(tmp_path, "b", ["s1"], extra_task="stranger")
    merge_collections([a, b], formal, "20261021T120000Z")


def test_a_source_that_committed_nothing_is_refused(tmp_path):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1"])
    a = make_source(tmp_path, "a", ["s0", "s1"])
    b = make_source(tmp_path, "b", ["s1"], committed=[])
    refused("MERGE_INDEX_INVALID", [a, b], formal, "20261021T120000Z")


def test_the_supplement_with_a_different_identity_is_refused(tmp_path):
    ids = ["s0", "s1", "s2"]
    formal = scene_list(tmp_path / "f.json", ids)
    a = make_source(tmp_path, "a", ids, committed=["s0", "s1"])
    b = make_source(tmp_path, "b", ["s2"], report_edit=dict(identity=dict(IDENTITY, source_sha256="9" * 64)))
    refused("MERGE_IDENTITY_MISMATCH", [a, b], formal, "20261021T120000Z")


def test_a_union_that_is_not_the_formal_list_is_refused(tmp_path):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1", "s2", "s3"])
    a = make_source(tmp_path, "a", ["s0"])
    b = make_source(tmp_path, "b", ["s1", "s2"])
    refused("MERGE_UNION_NOT_FORMAL_LIST", [a, b], formal, "20261021T120000Z")          # s3 is in no source


def test_a_scene_the_formal_list_does_not_name_is_refused(tmp_path):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1"])
    a = make_source(tmp_path, "a", ["s0"])
    b = make_source(tmp_path, "b", ["s1", "stranger"])
    refused("MERGE_SCENE_NOT_IN_FORMAL_LIST", [a, b], formal, "20261021T120000Z")


def test_a_source_without_a_seal_is_refused(tmp_path):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1"])
    a = make_source(tmp_path, "a", ["s0"])
    b = make_source(tmp_path, "b", ["s1"], seal_it=False)
    refused("MERGE_SOURCE_UNSEALED", [a, b], formal, "20261021T120000Z")


def test_a_damaged_seal_manifest_counts_as_unsealed(tmp_path):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1"])
    a = make_source(tmp_path, "a", ["s0"])
    b = make_source(tmp_path, "b", ["s1"])
    (tmp_path / "b.seal-manifest.jsonl").write_text("tampered\n")
    refused("MERGE_SOURCE_UNSEALED", [a, b], formal, "20261021T120000Z")


@pytest.mark.parametrize("damage", ["changed", "extra", "missing", "index"])
def test_a_sealed_root_that_fails_its_readback_is_refused(tmp_path, damage):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1"])
    a = make_source(tmp_path, "a", ["s0"])
    b = make_source(tmp_path, "b", ["s1"])
    root = tmp_path / "b"
    if damage == "changed":
        (root / "host/other.json").write_text("changed bytes")
    elif damage == "extra":
        (root / "host/new.json").write_text("{}")
    elif damage == "missing":
        (root / "host/other.json").unlink()
    else:
        (root / "collection-index.json").write_text((root / "collection-index.json").read_text().replace("s1", "s9"))
    refused("MERGE_INDEX_NOT_SEALED" if damage == "index" else "MERGE_SOURCE_READBACK_FAILED", [a, b], formal, "20261021T120000Z")


def test_an_index_outside_its_sealed_run_root_is_refused(tmp_path):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1"])
    a = make_source(tmp_path, "a", ["s0"])
    b = make_source(tmp_path, "b", ["s1"])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "collection-index.json").write_bytes((tmp_path / "b/collection-index.json").read_bytes())
    refused("MERGE_INDEX_NOT_SEALED", [a, MergeSource(index=elsewhere / "collection-index.json", qualification_report=b.qualification_report,
                                                       host="b", run_root=tmp_path / "b")], formal, "20261021T120000Z")


@pytest.mark.parametrize("edit,code", [
    (dict(status="NOT_QUALIFIED", reasons=["QC_RATE"]), "MERGE_QUALIFICATION_NOT_QUALIFIED"),
    (dict(status="QUALIFIED", reasons=["QC_RATE"]), "MERGE_QUALIFICATION_NOT_QUALIFIED"),
])
def test_a_report_that_is_not_qualified_is_refused(tmp_path, edit, code):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1"])
    a = make_source(tmp_path, "a", ["s0"])
    b = make_source(tmp_path, "b", ["s1"], report_edit=edit)
    refused(code, [a, b], formal, "20261021T120000Z")


def test_a_file_that_is_not_a_report_is_refused(tmp_path):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1"])
    a = make_source(tmp_path, "a", ["s0"])
    b = make_source(tmp_path, "b", ["s1"])
    Path(b.qualification_report).write_text(json.dumps(dict(kind="something else")))
    refused("MERGE_QUALIFICATION_INVALID", [a, b], formal, "20261021T120000Z")


@pytest.mark.parametrize("edit", ["qualification", "kind", "duplicate", "no_scene_id", "not_a_list"])
def test_an_index_that_is_not_a_frozen_non_qualification_index_is_refused(tmp_path, edit):
    formal = scene_list(tmp_path / "f.json", ["s0", "s1"])
    a = make_source(tmp_path, "a", ["s0"])
    b = make_source(tmp_path, "b", ["s1"])
    path = tmp_path / "b/collection-index.json"
    document = json.loads(path.read_text())
    if edit == "qualification":
        document["qualification"] = True
    elif edit == "kind":
        document["kind"] = "act_collection_campaign_index"
    elif edit == "duplicate":
        document["committed_episodes"] = document["committed_episodes"] * 2
    elif edit == "no_scene_id":
        document["committed_episodes"] = [dict(kind="x")]
    else:
        document["committed_episodes"] = {}
    path.write_text(json.dumps(document))
    seal(tmp_path / "b")
    code = {"qualification": "MERGE_INDEX_NOT_FROZEN", "kind": "MERGE_INDEX_NOT_FROZEN", "duplicate": "MERGE_EPISODE_DUPLICATE"}.get(
        edit, "MERGE_INDEX_INVALID")
    refused(code, [a, b], formal, "20261021T120000Z")


@pytest.mark.parametrize("content", ["{}", '{"scenarios": []}', '{"scenarios": [{"scene_id": "a"}]}',
                                     '{"scenarios": [{"scene_id": "a", "split": "train"}, {"scene_id": "a", "split": "train"}]}', "nope"])
def test_a_formal_list_that_is_not_one_is_refused(tmp_path, content):
    a = make_source(tmp_path, "a", ["s0"])
    b = make_source(tmp_path, "b", ["s1"])
    (tmp_path / "f.json").write_text(content)
    refused("MERGE_FORMAL_LIST_INVALID", [a, b], tmp_path / "f.json", "20261021T120000Z")


def test_a_source_without_a_host_label_is_refused(two):
    tmp_path, formal, a, b = two
    refused("MERGE_SOURCE_INVALID", [a, MergeSource(index=b.index, qualification_report=b.qualification_report, host="")],
            formal, "20261021T120000Z")


# ---- the command ---------------------------------------------------------------------------------------------------------------

def argv_for(tmp_path, formal, a, b, out, *extra):
    return ["--out-dir", str(out), "--formal-list", str(formal), "--stamp", "20261021T120000Z", *extra,
            "--index", str(a.index), "--qualification-report", str(a.qualification_report), "--host", a.host,
            "--index", str(b.index), "--qualification-report", str(b.qualification_report), "--host", b.host]


def test_the_command_writes_the_index_and_the_manifest_once_and_changes_no_source(two, capsys):
    tmp_path, formal, a, b = two
    before = [(p, p.read_bytes()) for s in (a, b) for p in Path(s.index).parent.rglob("*") if p.is_file()]
    out = tmp_path / "merged"
    assert cli.main(argv_for(tmp_path, formal, a, b, out)) == 0
    assert sorted(p.name for p in out.iterdir()) == ["collection-index.json", "manifest.json"]
    index = json.loads((out / "collection-index.json").read_text())
    assert index["campaign_id"] == "merged-20261021T120000Z" and len(index["committed_episodes"]) == 6
    assert [(p, p.read_bytes()) for s in (a, b) for p in Path(s.index).parent.rglob("*") if p.is_file()] == before
    assert "merged 6 episodes of 6 scenes" in capsys.readouterr().out
    assert cli.main(argv_for(tmp_path, formal, a, b, out)) == 2                  # the output exists
    assert "MERGE_OUTPUT_EXISTS" in capsys.readouterr().err


def test_a_refusal_writes_nothing(two, capsys):
    tmp_path, formal, a, b = two
    (tmp_path / "b/host/other.json").write_text("changed bytes")
    out = tmp_path / "merged"
    assert cli.main(argv_for(tmp_path, formal, a, b, out)) == 2
    assert "REFUSED: MERGE_SOURCE_READBACK_FAILED" in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize("drop", ["--qualification-report", "--host"])
def test_a_source_missing_an_option_is_refused(two, capsys, drop):
    tmp_path, formal, a, b = two
    argv = argv_for(tmp_path, formal, a, b, tmp_path / "merged")
    at = argv.index(drop)
    del argv[at:at + 2]
    assert cli.main(argv) == 2 and "MERGE_SOURCE_INVALID" in capsys.readouterr().err


def test_the_readback_workers_do_not_change_the_result(two):
    tmp_path, formal, a, b = two
    one = merge_collections([a, b], formal, "20261021T120000Z", readback_workers=1)
    many = merge_collections([a, b], formal, "20261021T120000Z", readback_workers=8)
    assert one == many


# ---- export reads the merged index unchanged -------------------------------------------------------------------------------------

def test_export_resolves_the_merged_index_exactly_as_it_resolves_the_campaigns_separately(tmp_path, monkeypatch):
    from so101_demo.act.bundle import _index, resolve_committed_episodes
    from test_act_bundle_processed import schema4_entries

    (tmp_path / "fx").mkdir()
    entries, calls, _ = schema4_entries(tmp_path / "fx", monkeypatch, scene_ids=("001", "002", "003"))
    by_scene = {entry["scene_id"]: entry for entry in entries}
    formal = scene_list(tmp_path / "formal.scenes.json", ["001", "002", "003"], {entry["scene_id"]: entry["split"] for entry in entries})

    def source(name, scenes):
        root = tmp_path / name
        root.mkdir()
        (root / "collection-index.json").write_text(json.dumps(dict(
            schema_version=4, kind="act_collection_frozen_index", qualification=False, campaign_id=name, scene_count=len(scenes),
            collected_tasks=[dict(scene_id=s) for s in scenes], committed_episodes=[by_scene[s] for s in scenes],
            scenes_without_evidence=[])))
        seal(root)
        return MergeSource(index=root / "collection-index.json", qualification_report=report(tmp_path / (name + ".report.json")), host=name)

    a, b = source("host-a", ["001", "003"]), source("host-b", ["002"])
    out = tmp_path / "merged"
    assert cli.main(["--out-dir", str(out), "--formal-list", str(formal), "--stamp", "20261021T120000Z",
                     "--index", str(a.index), "--qualification-report", str(a.qualification_report), "--host", "a",
                     "--index", str(b.index), "--qualification-report", str(b.qualification_report), "--host", "b"]) == 0
    assert sorted(_index(out / "collection-index.json")) == ["001", "002", "003"]       # the real index reader accepts it
    manifest = json.loads((out / "manifest.json").read_text())
    merged = resolve_committed_episodes(manifest=manifest, campaign_index=out / "collection-index.json")
    separate = []
    for src in (a, b):
        own = {entry["scene_id"] for entry in json.loads(Path(src.index).read_text())["committed_episodes"]}
        separate += resolve_committed_episodes(manifest={"episodes": [row for row in manifest["episodes"] if row["scene_id"] in own]},
                                               campaign_index=src.index)
    assert len(merged) == 3 and list(merged) == separate               # same episodes, same order, same content
