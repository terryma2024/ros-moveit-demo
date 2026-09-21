"""The durable owner-record writer: an intent before every spawn, a readback after it.

Task 6 of the macOS service campaign closure plan. The service's recovery path reclaims
``adapter -> campaign -> worker -> station`` leaf first, and it may only signal a process whose
live kernel identity still matches a durable record. That only works if the records exist and are
written in the right order, so these tests drive the real writer against the real filesystem:
the exact documents, their keys, their mode, their durability, and the refusal to write anywhere
but inside the owner-record root.

``so101_teleop`` consumes these records and must never be a dependency of them (teleop depends on
demo, never the reverse), so the fingerprint agreement test imports the teleop function here, in
the test only, and the layering test reads this module's own imports.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import time

import pytest

import so101_demo.runtime.owner_records as owner_records
from so101_demo.runtime.owner_records import (
    ROLES,
    OwnerContext,
    OwnerRecordError,
    OwnerSpawnRecorder,
    command_fingerprint,
    owner_context_from_environment,
)

CAMPAIGN = "campaign-1"
BATCH = "batch-1"


def _environment(tmp_path: Path, **overrides: str) -> dict[str, str]:
    environment = {
        "SO101_OWNER_TREE_ROOT": str(tmp_path / "owner-tree"),
        "SO101_OWNER_CAMPAIGN_ID": CAMPAIGN,
        "SO101_OWNER_BATCH_ID": BATCH,
        "SO101_OWNER_GENERATION": "1",
    }
    environment.update(overrides)
    return environment


def _context(tmp_path: Path, **overrides: str) -> OwnerContext:
    context = owner_context_from_environment(_environment(tmp_path, **overrides))
    assert context is not None
    return context


def _directory(tmp_path: Path) -> Path:
    return tmp_path / "owner-tree" / CAMPAIGN / BATCH


def _documents(directory: Path, suffix: str) -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob(f"*{suffix}"))
    ]


# --------------------------------------------------------------------------------------
# context from the environment
# --------------------------------------------------------------------------------------


def test_without_the_root_variable_there_is_no_context_and_no_tree(tmp_path):
    """The whole feature hangs off one variable: unset means inert, not a default location."""

    environment = _environment(tmp_path)
    environment.pop("SO101_OWNER_TREE_ROOT")
    assert owner_context_from_environment(environment) is None
    assert owner_context_from_environment({}) is None
    assert not (tmp_path / "owner-tree").exists()


@pytest.mark.parametrize(
    "missing",
    ["SO101_OWNER_CAMPAIGN_ID", "SO101_OWNER_BATCH_ID", "SO101_OWNER_GENERATION"],
)
def test_a_missing_required_field_is_not_a_context(tmp_path, missing):
    environment = _environment(tmp_path)
    environment.pop(missing)
    assert owner_context_from_environment(environment) is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SO101_OWNER_CAMPAIGN_ID", ""),
        ("SO101_OWNER_CAMPAIGN_ID", "   "),
        ("SO101_OWNER_CAMPAIGN_ID", "with/slash"),
        ("SO101_OWNER_CAMPAIGN_ID", ".."),
        ("SO101_OWNER_BATCH_ID", ""),
        ("SO101_OWNER_BATCH_ID", "../escape"),
        ("SO101_OWNER_BATCH_ID", "with/slash"),
        ("SO101_OWNER_GENERATION", "0"),
        ("SO101_OWNER_GENERATION", "-1"),
        ("SO101_OWNER_GENERATION", "1.5"),
        ("SO101_OWNER_GENERATION", "one"),
        ("SO101_OWNER_GENERATION", ""),
        ("SO101_OWNER_TREE_ROOT", "relative/owner-tree"),
        ("SO101_OWNER_TREE_ROOT", ""),
        ("SO101_OWNER_PARENT_TOKEN", "../escape"),
    ],
)
def test_an_invalid_required_field_is_not_a_context(tmp_path, name, value):
    """A context that cannot be written inside the root is no context at all."""

    environment = _environment(tmp_path)
    environment[name] = value
    assert owner_context_from_environment(environment) is None


def test_the_context_carries_the_optional_parent_token(tmp_path):
    context = _context(tmp_path, **{"SO101_OWNER_PARENT_TOKEN": "adapter-abc"})
    assert context.root == tmp_path / "owner-tree"
    assert context.campaign_id == CAMPAIGN
    assert context.batch_id == BATCH
    assert context.generation == 1
    assert context.parent_spawn_token == "adapter-abc"

    without = _context(tmp_path)
    assert without.parent_spawn_token is None
    assert _context(tmp_path, **{"SO101_OWNER_PARENT_TOKEN": ""}).parent_spawn_token is None


# --------------------------------------------------------------------------------------
# the frozen command fingerprint
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["/usr/bin/python3", "-m", "so101_demo.cli.macos_w2_worker", "ack.json", "--slot", "0"],
        ["launcher"],
        [],
        ["/opt/venv/bin/python", "π", "--flag=1", "value with spaces"],
    ],
)
def test_command_fingerprint_is_byte_identical_to_the_teleop_fingerprint(argv):
    """Teleop recovery re-proves the live command with its own hash; both must agree exactly."""

    from so101_teleop.process_identity import command_fingerprint as teleop_fingerprint

    assert command_fingerprint(argv) == teleop_fingerprint(argv)


def test_command_fingerprint_excludes_the_launcher():
    """argv[0] is not preserved by every launcher, so it is not part of the fingerprint."""

    assert command_fingerprint(["a", "b", "c"]) == command_fingerprint(["zzz", "b", "c"])
    assert command_fingerprint(["a", "b", "c"]) != command_fingerprint(["a", "b", "d"])


# --------------------------------------------------------------------------------------
# the intent
# --------------------------------------------------------------------------------------


def test_begin_writes_the_exact_intent_document_before_it_returns(tmp_path):
    argv = ["/usr/bin/python3", "-m", "so101_demo.cli.macos_w2_campaign", "--batch-id", BATCH]
    recorder = OwnerSpawnRecorder.begin(
        context=_context(tmp_path),
        role="CAMPAIGN",
        argv=argv,
        parent_spawn_token="adapter-abc",
        clock=lambda: 1_700_000_000_000_000_000,
    )

    assert recorder.spawn_token.startswith("campaign-")
    assert len(recorder.spawn_token) == len("campaign-") + 32
    directory = _directory(tmp_path)
    assert recorder.intent_path == directory / f"{recorder.spawn_token}.intent.json"
    assert recorder.confirmation_path == directory / f"{recorder.spawn_token}.confirmed.json"
    assert recorder.abandoned_path == directory / f"{recorder.spawn_token}.abandoned.json"
    assert recorder.argv_sha256 == command_fingerprint(argv)
    assert recorder.expected_executable == argv[0]
    assert recorder.own_session is True
    assert recorder.parent_spawn_token == "adapter-abc"
    assert recorder.created_at_ns == 1_700_000_000_000_000_000

    assert _documents(directory, ".intent.json") == [
        {
            "schema": "so101.owner-intent/1",
            "campaign_id": CAMPAIGN,
            "batch_id": BATCH,
            "role": "CAMPAIGN",
            "generation": 1,
            "spawn_token": recorder.spawn_token,
            "parent_spawn_token": "adapter-abc",
            "expected_executable": argv[0],
            "argv_sha256": command_fingerprint(argv),
            "own_session": True,
            "created_at_ns": 1_700_000_000_000_000_000,
        }
    ]
    assert not list(directory.glob("*.part"))


def test_the_intent_is_fsynced_and_atomic_before_begin_returns(tmp_path, monkeypatch):
    """The writer returns only after the payload and its directory reached the disk."""

    synced: list[int] = []
    real_fsync = os.fsync
    def observing_fsync(descriptor):
        synced.append(descriptor)
        return real_fsync(descriptor)

    monkeypatch.setattr(owner_records.os, "fsync", observing_fsync)

    OwnerSpawnRecorder.begin(context=_context(tmp_path), role="WORKER", argv=["/bin/worker"])

    assert len(synced) >= 2, "the payload and the directory are both fsynced"
    assert not list(_directory(tmp_path).glob("*.part"))


def test_the_intent_file_is_owner_only(tmp_path):
    recorder = OwnerSpawnRecorder.begin(
        context=_context(tmp_path), role="WORKER", argv=["/bin/worker"]
    )
    assert (recorder.intent_path.stat().st_mode & 0o777) == 0o600


def test_begin_generates_a_distinct_role_prefixed_token_per_call(tmp_path):
    context = _context(tmp_path)
    first = OwnerSpawnRecorder.begin(context=context, role="BROKER", argv=["/bin/broker"])
    second = OwnerSpawnRecorder.begin(context=context, role="BROKER", argv=["/bin/broker"])

    assert first.spawn_token.startswith("broker-")
    assert second.spawn_token.startswith("broker-")
    assert first.spawn_token != second.spawn_token
    assert first.intent_path != second.intent_path


def test_the_role_vocabulary_is_frozen_and_an_unknown_role_is_refused(tmp_path):
    assert ROLES == ("ADAPTER", "CAMPAIGN", "BROKER", "WORKER", "STATION")
    for role in ROLES:
        recorder = OwnerSpawnRecorder.begin(
            context=_context(tmp_path), role=role, argv=["/bin/owner"], spawn_token=f"{role}-fixed"
        )
        document = json.loads(recorder.intent_path.read_text(encoding="utf-8"))
        assert document["role"] == role
        assert recorder.intent_path.name == f"{role}-fixed.intent.json"

    with pytest.raises(OwnerRecordError) as refused:
        OwnerSpawnRecorder.begin(
            context=_context(tmp_path), role="coordinator", argv=["/bin/owner"]
        )
    assert refused.value.code == "OWNER_ROLE_INVALID"


def test_an_empty_argv_is_refused(tmp_path):
    with pytest.raises(OwnerRecordError) as refused:
        OwnerSpawnRecorder.begin(context=_context(tmp_path), role="WORKER", argv=[])
    assert refused.value.code == "OWNER_ARGV_INVALID"


# --------------------------------------------------------------------------------------
# path safety
# --------------------------------------------------------------------------------------


def test_a_symlinked_record_file_is_refused_and_its_target_is_untouched(tmp_path):
    context = _context(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("untouched", encoding="utf-8")
    directory = _directory(tmp_path)
    directory.mkdir(parents=True)
    token = "campaign-symlinked"
    (directory / f"{token}.intent.json").symlink_to(outside)

    with pytest.raises(OwnerRecordError) as refused:
        OwnerSpawnRecorder.begin(
            context=context, role="CAMPAIGN", argv=["/bin/campaign"], spawn_token=token
        )
    assert refused.value.code == "OWNER_RECORD_UNSAFE_PATH"
    assert outside.read_text(encoding="utf-8") == "untouched"


def test_a_symlinked_batch_directory_cannot_redirect_writes_outside_the_root(tmp_path):
    root = tmp_path / "owner-tree"
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / CAMPAIGN).mkdir(parents=True)
    (root / CAMPAIGN / BATCH).symlink_to(outside, target_is_directory=True)

    with pytest.raises(OwnerRecordError) as refused:
        OwnerSpawnRecorder.begin(context=_context(tmp_path), role="WORKER", argv=["/bin/worker"])
    assert refused.value.code == "OWNER_RECORD_UNSAFE_PATH"
    assert list(outside.iterdir()) == []


def test_an_unsafe_spawn_token_is_refused(tmp_path):
    with pytest.raises(OwnerRecordError) as refused:
        OwnerSpawnRecorder.begin(
            context=_context(tmp_path), role="WORKER", argv=["/bin/worker"], spawn_token="../escape"
        )
    assert refused.value.code == "OWNER_RECORD_UNSAFE_PATH"
    assert not (tmp_path / "escape.intent.json").exists()


# --------------------------------------------------------------------------------------
# the confirmation
# --------------------------------------------------------------------------------------


def test_confirm_records_the_kernel_readback(tmp_path):
    recorder = OwnerSpawnRecorder.begin(
        context=_context(tmp_path),
        role="WORKER",
        argv=["/bin/worker", "--slot", "0"],
        parent_spawn_token="campaign-abc",
    )
    reads: list[int] = []

    def identity_reader(pid: int):
        reads.append(pid)
        return (4321, 987_654_321)

    document = recorder.confirm(4321, identity_reader=identity_reader, clock=lambda: 2_000)

    assert reads == [4321]
    assert document == {
        "schema": "so101.owner-confirmation/1",
        "spawn_token": recorder.spawn_token,
        "pid": 4321,
        "pgid": 4321,
        "started_ticks": 987_654_321,
        "command_sha256": recorder.argv_sha256,
        "confirmed_at_ns": 2_000,
    }
    assert _documents(_directory(tmp_path), ".confirmed.json") == [document]
    assert recorder.argv_sha256 == command_fingerprint(["/bin/worker", "--slot", "0"])
    assert not list(_directory(tmp_path).glob("*.part"))


def test_confirm_retries_until_the_kernel_reports_the_child(tmp_path):
    recorder = OwnerSpawnRecorder.begin(
        context=_context(tmp_path), role="STATION", argv=["/bin/station"]
    )
    reads: list[int] = []

    def slow_reader(pid: int):
        reads.append(pid)
        return None if len(reads) < 3 else (6001, 424_242)

    document = recorder.confirm(777, identity_reader=slow_reader, deadline_s=5.0)

    assert len(reads) == 3, "the read is retried until the deadline"
    assert (document["pid"], document["pgid"], document["started_ticks"]) == (777, 6001, 424_242)


def test_confirm_raises_the_frozen_code_when_the_kernel_never_reports_the_child(tmp_path):
    recorder = OwnerSpawnRecorder.begin(
        context=_context(tmp_path), role="WORKER", argv=["/bin/worker"]
    )
    with pytest.raises(OwnerRecordError) as refused:
        recorder.confirm(1234, identity_reader=lambda _pid: None, deadline_s=0.0)

    assert refused.value.code == "OWNER_CONFIRMATION_UNREADABLE"
    assert not recorder.confirmation_path.exists()
    assert not list(_directory(tmp_path).glob("*.part"))


# --------------------------------------------------------------------------------------
# abandonment
# --------------------------------------------------------------------------------------


def test_abandon_marks_the_record_and_leaves_the_intent_alone(tmp_path):
    recorder = OwnerSpawnRecorder.begin(
        context=_context(tmp_path), role="WORKER", argv=["/bin/worker"]
    )
    recorder.abandon("CHILD_ACK_TIMEOUT")

    markers = _documents(_directory(tmp_path), ".abandoned.json")
    assert len(markers) == 1
    marker = markers[0]
    assert set(marker) == {"spawn_token", "reason", "recorded_at_ns"}
    assert marker["reason"] == "CHILD_ACK_TIMEOUT"
    assert marker["spawn_token"] == recorder.spawn_token
    assert type(marker["recorded_at_ns"]) is int and marker["recorded_at_ns"] > 0
    assert recorder.intent_path.exists()
    assert not list(_directory(tmp_path).glob("*.part"))


# --------------------------------------------------------------------------------------
# the child environment
# --------------------------------------------------------------------------------------


def test_the_child_environment_carries_its_own_token_and_its_parent_token(tmp_path):
    recorder = OwnerSpawnRecorder.begin(
        context=_context(tmp_path), role="WORKER", argv=["/bin/worker"],
        parent_spawn_token="campaign-abc",
    )
    environment = recorder.child_environment(
        {"KEEP": "1", "SO101_OWNER_TOKEN": "stale", "SO101_OWNER_PARENT_TOKEN": "stale"}
    )

    assert environment["KEEP"] == "1"
    assert environment["SO101_OWNER_TOKEN"] == recorder.spawn_token
    assert environment["SO101_OWNER_PARENT_TOKEN"] == "campaign-abc"
    assert environment["SO101_OWNER_TREE_ROOT"] == str(tmp_path / "owner-tree")
    assert environment["SO101_OWNER_CAMPAIGN_ID"] == CAMPAIGN
    assert environment["SO101_OWNER_BATCH_ID"] == BATCH
    assert environment["SO101_OWNER_GENERATION"] == "1"


def test_a_root_spawn_does_not_leave_an_inherited_parent_token_in_the_child(tmp_path):
    """The child's parent is this spawner. An inherited grandparent token must not be claimed."""

    recorder = OwnerSpawnRecorder.begin(
        context=_context(tmp_path), role="CAMPAIGN", argv=["/bin/campaign"]
    )
    environment = recorder.child_environment({"SO101_OWNER_PARENT_TOKEN": "grandparent"})

    assert "SO101_OWNER_PARENT_TOKEN" not in environment
    assert environment["SO101_OWNER_TOKEN"] == recorder.spawn_token


# --------------------------------------------------------------------------------------
# the adapter boundary: the CAMPAIGN intent is written before its own Popen
# --------------------------------------------------------------------------------------

#: The child prints the owner context it really inherited, then stays alive to be read back.
CHILD_REPORT = (
    "import json, os, time;"
    "print(json.dumps({name: value for name, value in os.environ.items()"
    " if name.startswith('SO101_OWNER_')}), flush=True);"
    "time.sleep(30)"
)


class _FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    def poll(self) -> None:
        return None


def test_the_adapter_takes_its_identity_from_the_fixed_control_environment(tmp_path):
    import types

    from so101_demo.cli.macos_service_campaign import adapter_owner_context

    arguments = types.SimpleNamespace(batch_id="svc-batch")
    context = adapter_owner_context(
        arguments,
        environment={
            "SO101_OWNER_TREE_ROOT": str(tmp_path / "owner-tree"),
            "SO101_FIXED_CONTROL_CAMPAIGN_ID": "svc-campaign",
            "SO101_FIXED_CONTROL_EPOCH": "3",
        },
    )
    assert context is not None
    assert (context.campaign_id, context.batch_id, context.generation) == (
        "svc-campaign",
        "svc-batch",
        3,
    )
    assert context.parent_spawn_token is None

    # The root is the switch: without it the adapter owns no tree, whatever else is set.
    assert (
        adapter_owner_context(
            arguments, environment={"SO101_FIXED_CONTROL_CAMPAIGN_ID": "svc-campaign"}
        )
        is None
    )

    # A complete SO101_OWNER_* context is the adapter's own identity and wins over the service's.
    complete = adapter_owner_context(arguments, environment=_environment(tmp_path))
    assert complete is not None
    assert (complete.campaign_id, complete.batch_id) == (CAMPAIGN, BATCH)


def test_the_adapter_records_the_campaign_intent_before_popen_and_confirms_the_child(
    tmp_path, monkeypatch
):
    import subprocess
    import sys

    import so101_demo.cli.macos_service_campaign as adapter

    monkeypatch.setenv("SO101_OWNER_TOKEN", "service-token")
    directory = _directory(tmp_path)
    observed = {}
    real_popen = subprocess.Popen

    def observing_popen(argv, **kwargs):
        observed["argv"] = list(argv)
        observed["env"] = dict(kwargs["env"])
        observed["intents"] = sorted(path.name for path in directory.glob("*.intent.json"))
        observed["confirmed"] = sorted(path.name for path in directory.glob("*.confirmed.json"))
        observed["parts"] = sorted(path.name for path in directory.glob("*.part"))
        return real_popen(argv, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", observing_popen)
    campaign = adapter.OwnedCampaign(
        [sys.executable, "-c", CHILD_REPORT],
        log_path=tmp_path / "campaign.log",
        owner_context=_context(tmp_path),
    )
    try:
        assert len(observed["intents"]) == 1, "the intent is durable before Popen"
        assert observed["confirmed"] == [], "the confirmation is written after Popen"
        assert observed["parts"] == []
        intent = json.loads((directory / observed["intents"][0]).read_text(encoding="utf-8"))
        assert intent["role"] == "CAMPAIGN"
        assert intent["expected_executable"] == sys.executable
        assert intent["parent_spawn_token"] == "service-token"
        assert observed["env"]["SO101_OWNER_TOKEN"] == intent["spawn_token"]
        assert observed["env"]["SO101_OWNER_PARENT_TOKEN"] == "service-token"
        assert observed["env"]["PYTORCH_ENABLE_MPS_FALLBACK"] == "0"

        document = json.loads(
            (directory / f"{intent['spawn_token']}.confirmed.json").read_text(encoding="utf-8")
        )
        assert document["pid"] == campaign.process.pid
        assert document["pgid"] == campaign.process.pid, "start_new_session makes its own group"
        assert document["started_ticks"] > 0
        assert document["command_sha256"] == intent["argv_sha256"]

        # The campaign child itself reports what it really inherited, not what the adapter meant.
        # It prints as soon as it starts, so the wait for its first line is bounded and explicit.
        deadline = time.monotonic() + 10.0
        report: dict = {}
        while time.monotonic() < deadline:
            content = (tmp_path / "campaign.log").read_text(encoding="utf-8").strip()
            if content:
                report = json.loads(content)
                break
            time.sleep(0.05)
        assert report, "the campaign child reported the environment it was spawned with"
        assert report["SO101_OWNER_TOKEN"] == intent["spawn_token"]
        assert report["SO101_OWNER_PARENT_TOKEN"] == "service-token"
        assert report["SO101_OWNER_TREE_ROOT"] == str(tmp_path / "owner-tree")
        assert report["SO101_OWNER_CAMPAIGN_ID"] == CAMPAIGN
        assert report["SO101_OWNER_BATCH_ID"] == BATCH
        assert report["SO101_OWNER_GENERATION"] == "1"
    finally:
        campaign.stop()
        campaign.close()


def test_an_adapter_without_an_owner_context_spawns_exactly_as_before(tmp_path, monkeypatch):
    import subprocess

    import so101_demo.cli.macos_service_campaign as adapter

    observed = {}

    def fake_popen(argv, **kwargs):
        observed["argv"] = list(argv)
        observed["env"] = dict(kwargs["env"])
        return _FakeProcess(424242)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    campaign = adapter.OwnedCampaign(
        ["/bin/true"], log_path=tmp_path / "campaign.log", owner_context=None
    )
    try:
        assert campaign.record is None
        assert observed["argv"] == ["/bin/true"]
        assert observed["env"]["PYTORCH_ENABLE_MPS_FALLBACK"] == "0"
        assert [name for name in observed["env"] if name.startswith("SO101_OWNER_")] == []
        assert not (tmp_path / "owner-tree").exists()
    finally:
        campaign.close()


def test_the_adapter_abandons_its_record_when_the_spawn_fails(tmp_path, monkeypatch):
    import subprocess

    import so101_demo.cli.macos_service_campaign as adapter

    def failing_popen(_argv, **_kwargs):
        raise OSError("cannot spawn the campaign")

    monkeypatch.setattr(subprocess, "Popen", failing_popen)
    with pytest.raises(OSError, match="cannot spawn the campaign"):
        adapter.OwnedCampaign(
            ["/bin/true"], log_path=tmp_path / "campaign.log", owner_context=_context(tmp_path)
        )

    markers = _documents(_directory(tmp_path), ".abandoned.json")
    assert [marker["reason"] for marker in markers] == ["SPAWN_FAILED"]
    assert len(_documents(_directory(tmp_path), ".intent.json")) == 1
    assert not list(_directory(tmp_path).glob("*.part"))


def test_the_adapter_abandons_its_record_when_the_child_identity_is_unreadable(
    tmp_path, monkeypatch
):
    import subprocess

    import so101_demo.cli.macos_service_campaign as adapter

    def missing_process(_pid):
        raise ProcessLookupError("no such process")

    monkeypatch.setattr(subprocess, "Popen", lambda _argv, **_kwargs: _FakeProcess(424242))
    monkeypatch.setattr(os, "getpgid", missing_process)

    with pytest.raises(OwnerRecordError) as refused:
        adapter.OwnedCampaign(
            ["/bin/true"],
            log_path=tmp_path / "campaign.log",
            owner_context=_context(tmp_path),
            owner_confirm_deadline_s=0.0,
        )

    assert refused.value.code == "OWNER_CONFIRMATION_UNREADABLE"
    markers = _documents(_directory(tmp_path), ".abandoned.json")
    assert [marker["reason"] for marker in markers] == ["OWNER_CONFIRMATION_UNREADABLE"]
    assert not list(_directory(tmp_path).glob("*.confirmed.json"))


def test_the_adapter_entry_point_refuses_by_name_when_the_record_cannot_be_written(
    tmp_path, monkeypatch, capsys
):
    """The refusal is a named document on stdout, not a traceback out of the service's launcher."""

    import types

    import so101_demo.cli.macos_service_campaign as adapter

    arguments = types.SimpleNamespace(
        evidence_root=tmp_path,
        config=tmp_path / "config.yaml",
        batch_id="batch-1",
        yolo_weights=tmp_path / "yolo.pt",
        grounded_root=tmp_path / "grounded",
        point_id=[],
    )
    monkeypatch.setenv("SO101_FIXED_CONTROL_CAMPAIGN_ID", "svc-campaign")
    monkeypatch.setattr(
        adapter,
        "build_parser",
        lambda: types.SimpleNamespace(parse_args=lambda _argv: arguments),
    )
    # The route is resolved from the document and the fresh start guard runs before any campaign
    # child exists (Task 7), so both are stubbed here: this test is about the owner record that
    # cannot be written, not about the admission.
    monkeypatch.setattr(
        adapter,
        "resolve_request",
        lambda *_args, **_kwargs: adapter.AdapterRoute(
            config=types.SimpleNamespace(start_guard=object()),
            route=types.SimpleNamespace(worker_count=1),
            module=adapter.CAMPAIGN_MODULE,
            record={"campaign_id": "svc-campaign"},
        ),
    )

    def admitted_guard(**kwargs):
        from so101_demo.parallel_batch.start_guard import PASS, GuardCheck, GuardResult
        from so101_demo.parallel_batch.start_guard_probe import darwin_guard_scope

        return GuardResult(
            scope=darwin_guard_scope(batch_id=kwargs["batch_id"],
                                     worker_count=kwargs["worker_count"]),
            status=PASS, started_monotonic_s=0.0, completed_monotonic_s=0.0,
            checks={"probe": GuardCheck(PASS, "PROBE_OK", None, None, "state")},
            snapshot=None, cleanup_state="CLEAR")

    def failing_campaign(*_args, **_kwargs):
        raise OwnerRecordError("OWNER_RECORD_UNWRITABLE", "the owner root is not writable")

    monkeypatch.setattr(adapter, "OwnedCampaign", failing_campaign)

    assert adapter.main(["ignored"], guard=admitted_guard) == 1
    document = json.loads(capsys.readouterr().out)
    assert document["status"] == "REFUSED"
    assert document["stage"] == "campaign_spawn"
    assert document["refusal"] == "OWNER_RECORD_UNWRITABLE"
    assert document["detail"] == "the owner root is not writable"


# --------------------------------------------------------------------------------------
# layering
# --------------------------------------------------------------------------------------


def test_the_module_imports_only_the_standard_library_and_demo_modules():
    """Teleop depends on demo. The writer is stdlib + demo, never the other direction."""

    source = Path(owner_records.__file__).read_text(encoding="utf-8")
    assert "import so101_teleop" not in source
    assert "from so101_teleop" not in source
    allowed = {
        "__future__",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "time",
        "typing",
        "uuid",
        "dataclasses",
    }
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".", 1)[0])
    assert roots <= allowed, roots - allowed
