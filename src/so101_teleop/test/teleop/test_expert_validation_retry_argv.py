"""The admitted retry must reach the v5 route with its binding named in the argv.

The macOS service launches the campaign adapter with one fixed argv. A ``FULL_RESTART_RETRY`` run
cannot bind itself from that argv: the v5 route refuses ``RETRY_ROOT_REQUIRED`` unless it is told
which original chain it executes, and it accepts either the prior root - whose committed document it
re-reads and hashes - or an already-admitted chain named by the original selection/result/catalog
digests and the original batch. The service sends the admitted chain, because those are the very
digests its own retry admission verified in the store. These tests pin the caller side:

* a first-pass argv is unchanged - it never carries a retry binding;
* an admitted retry names the admitted chain, its one point and the retry profile's own document;
* a retry whose binding cannot be named refuses *before* the one-time admission is consumed and
  before any process exists, with a typed reason.
"""

from dataclasses import replace
import asyncio
from pathlib import Path

import pytest

from so101_teleop.expert_validation.supervisor import (
    RETRY_BATCH_FLAG,
    RETRY_CATALOG_FLAG,
    RETRY_COORDINATOR_FLAGS,
    RETRY_RESULT_FLAG,
    RETRY_SELECTION_FLAG,
    fixed_coordinator_argv,
)

from test_expert_validation_supervisor import _retry_supervisor


def _request_argv(tmp_path, **overrides):
    """The argv the supervisor builds, with every value the adapter requires."""

    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    grounded = tmp_path / "grounded"
    grounded.mkdir()
    (grounded / "manifest.json").write_text("{}")
    values = dict(
        executable_path=tmp_path / "macos_service_campaign.py",
        points_path=tmp_path / "points.yaml",
        config_path=tmp_path / "config.yaml",
        batch_id="b001",
        worker_count=2,
        evidence_root=tmp_path / "batch",
        broker_image_id="sha256:" + "a" * 64,
        yolo_weights_path=weights,
        yolo_weights_sha256="b" * 64,
        grounded_root=grounded,
        grounded_manifest_sha256="c" * 64,
        selected_point_ids=("p1", "p2"),
        provenance_binding_path=None,
    )
    values.update(overrides)
    return fixed_coordinator_argv(**values)


def _value_after(argv, flag):
    return argv[argv.index(flag) + 1]


def test_a_first_pass_argv_never_carries_a_retry_binding(tmp_path):
    argv = _request_argv(tmp_path)

    assert not set(RETRY_COORDINATOR_FLAGS) & set(argv)
    assert argv[-2:] == ["--point-id", "p2"]


def test_a_retry_argv_names_the_admitted_chain_and_the_one_point(tmp_path):
    supervisor, store, request, context = _retry_supervisor(tmp_path)
    owner = supervisor.process_owner
    try:
        asyncio.run(supervisor.start_candidate_retry(request=request, context=context))
    finally:
        store.close()
    argv = owner.requests[-1].argv

    assert _value_after(argv, RETRY_SELECTION_FLAG) == request.original_selection_sha256
    assert _value_after(argv, RETRY_RESULT_FLAG) == request.original_result_sha256
    assert _value_after(argv, RETRY_CATALOG_FLAG) == request.original_catalog_sha256
    assert _value_after(argv, RETRY_BATCH_FLAG) == request.original_batch_id
    assert [value for flag, value in zip(argv, argv[1:]) if flag == "--point-id"] == [
        request.point_id
    ]
    assert _value_after(argv, "--batch-id") == request.batch_id
    # The retry executes the retry profile's own document, not the first pass's.
    assert Path(_value_after(argv, "--config")).name == "parallel_batch_v5_macos_mps_w1_retry.yaml"
    assert _value_after(argv, "--config") != str(
        supervisor._requests[request.campaign_id].parallel_config_path
    )


def test_a_retry_that_cannot_name_its_prior_batch_refuses_before_the_admission(tmp_path):
    supervisor, store, request, context = _retry_supervisor(tmp_path)
    owner = supervisor.process_owner
    try:
        # A retry that names itself as its own original has no prior chain to bind.
        with pytest.raises(RuntimeError, match="RETRY_ORIGINAL_BATCH_SELF"):
            asyncio.run(
                supervisor.start_candidate_retry(
                    request=replace(request, original_batch_id=request.batch_id),
                    context=context,
                )
            )
        assert owner.requests == [], "a refused binding must never spawn"
        consumed = store._connection.execute(
            "SELECT count(*) FROM commands WHERE command_id = ?", (request.command_id,)
        ).fetchone()[0]
        assert consumed == 0, "a refused binding must not consume the one-time command"
        assert store.next_retry("campaign-1").state == "QUEUED"
    finally:
        store.close()


def test_a_retry_for_a_profile_the_route_does_not_execute_is_refused(tmp_path):
    """Only the v5 macOS retry profile carries this chain; anything else is a contract error."""

    supervisor, store, request, context = _retry_supervisor(tmp_path)
    owner = supervisor.process_owner
    try:
        with pytest.raises(RuntimeError, match="RETRY_PROFILE_MISMATCH"):
            asyncio.run(
                supervisor.start_candidate_retry(
                    request=replace(request, execution_profile="MPS_W2_FIRST_PASS"),
                    context=context,
                )
            )
        assert owner.requests == []
    finally:
        store.close()


def test_the_retry_flags_are_the_v5_routes_own_flags():
    """The retry argv speaks the v5 parser's vocabulary, never a parallel one.

    ``so101_demo.cli.macos_w2_campaign`` is imported as a *module* by the macOS campaign entry
    points; the executable this service launches is the ``macos_service_campaign`` adapter in front
    of it. The adapter must parse and forward these same flags before a service-driven retry can be
    delivered, so the names are pinned against the route that consumes them.
    """

    from so101_demo.cli import macos_w2_campaign as campaign
    from so101_demo.parallel_batch.contracts import ExecutionProfile

    parser = campaign.build_w1_parser(str(ExecutionProfile.MPS_W1_FULL_RESTART_RETRY))
    accepted = {option for action in parser._actions for option in action.option_strings}

    assert set(RETRY_COORDINATOR_FLAGS) <= accepted


def test_the_route_reads_the_admitted_chain_without_the_prior_root():
    """The admitted chain is complete on its own, and it is what the route records.

    ``--retry-root`` would make the route re-read and re-hash the prior committed document, whose
    definition of the original result digest is that document's own file bytes, while the admitted
    digest is the journal terminal hash of the same commit; the two are measured to differ, so
    naming both would ask the route to confirm a digest its own definition does not produce.
    """

    from so101_demo.parallel_batch import point_drain

    source = point_drain.retry_source_from_hashes(
        point_id="task_start",
        original_selection_sha256="5" * 64,
        original_result_sha256="a" * 64,
        original_catalog_sha256="c" * 64,
        original_batch_id="batch-1",
    )
    assert source["original_result_sha256"] == "a" * 64
    assert source["original_selection_sha256"] == "5" * 64
    assert source["original_catalog_sha256"] == "c" * 64
    assert source["original_outcome"] == "FAILED"
    assert source["original_result_source"] == "declared"
