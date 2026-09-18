from dataclasses import asdict
from pathlib import Path

import pytest
import yaml


PACKAGE = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE / "config/mujoco/parallel_adaptive_workers_v1.yaml"


def test_default_options_form_the_frozen_fallback_ladder():
    """Changing reviewed defaults must require a new adaptive config artifact."""

    from so101_demo.parallel_batch.adaptive_contracts import load_adaptive_worker_options

    options = load_adaptive_worker_options(CONFIG)
    assert options.worker_count == 8
    assert options.levels == (8, 6, 4, 2, 1)
    assert options.initial_points_per_worker == 3
    assert options.worker_start_timeout_s == 120.0
    assert options.max_infra_attempts_per_point == 5
    assert options.ros_domain_ids == tuple(range(215, 231))
    assert options.yolo_executor_count == 2


def test_initial_chunk_is_not_a_capacity_gate(tmp_path):
    """Twenty points remain valid even though W8 receives only 24 initial hints."""

    from so101_demo.parallel_batch.adaptive_contracts import (
        AdaptiveBatchRequest,
        load_adaptive_worker_options,
    )
    from so101_demo.parallel_batch.contracts import RunMode

    request = AdaptiveBatchRequest(
        batch_id="at01",
        run_mode=RunMode.EXECUTE,
        selected_point_ids=tuple(f"p{number:02d}" for number in range(20)),
        options=load_adaptive_worker_options(CONFIG),
        evidence_root=tmp_path,
    )

    assert request.point_count == 20
    assert request.options.worker_count * request.options.initial_points_per_worker == 24
    assert request.runtime_root == tmp_path / "r" / "at01"


@pytest.mark.parametrize("value", [True, 0])
def test_options_reject_boolean_and_zero_worker_counts(value):
    """Boolean or zero worker counts could admit a pool without a real worker."""

    from so101_demo.parallel_batch.adaptive_contracts import (
        AdaptiveWorkerOptions,
        ContractError,
    )

    with pytest.raises(ContractError, match="POSITIVE_INTEGER"):
        AdaptiveWorkerOptions(
            worker_count=value,
            fallback_worker_counts=(),
            initial_points_per_worker=3,
            worker_start_timeout_s=120.0,
            max_infra_attempts_per_point=1,
            ros_domain_ids=(215,),
        )


@pytest.mark.parametrize("fallbacks", [(6, 6), (6, 7)])
def test_options_reject_duplicate_or_ascending_fallbacks(fallbacks):
    """A non-descending fallback ladder could loop or scale up after a failure."""

    from so101_demo.parallel_batch.adaptive_contracts import (
        AdaptiveWorkerOptions,
        ContractError,
    )

    with pytest.raises(ContractError, match="FALLBACK_WORKER_COUNTS"):
        AdaptiveWorkerOptions(
            worker_count=8,
            fallback_worker_counts=fallbacks,
            initial_points_per_worker=3,
            worker_start_timeout_s=120.0,
            max_infra_attempts_per_point=3,
            ros_domain_ids=tuple(range(215, 223)),
        )


def test_options_accept_w16_reject_w17_and_require_enough_domains():
    """The optional ceiling is W16 and every admitted worker needs one Domain."""

    from so101_demo.parallel_batch.adaptive_contracts import (
        AdaptiveWorkerOptions,
        ContractError,
    )

    options = AdaptiveWorkerOptions(16, (), 3, 120.0, 1, tuple(range(215, 231)))
    assert options.worker_count == 16
    assert options.ros_domain_ids == tuple(range(215, 231))
    with pytest.raises(ContractError, match="MAX_WORKER_COUNT"):
        AdaptiveWorkerOptions(17, (), 3, 120.0, 1, tuple(range(215, 232)))
    with pytest.raises(ContractError, match="ROS_DOMAIN_IDS"):
        AdaptiveWorkerOptions(16, (), 3, 120.0, 1, tuple(range(215, 230)))


def test_options_allow_w1_without_a_fallback():
    """The terminal W1 level remains a valid nonempty adaptive ladder."""

    from so101_demo.parallel_batch.adaptive_contracts import AdaptiveWorkerOptions

    options = AdaptiveWorkerOptions(1, (), 3, 120.0, 1, (215,))
    assert options.levels == (1,)


@pytest.mark.parametrize("value", [True, 0, 3, 8])
def test_options_reject_invalid_yolo_executor_count(value):
    from so101_demo.parallel_batch.adaptive_contracts import (
        AdaptiveWorkerOptions,
        ContractError,
    )

    with pytest.raises(ContractError, match="YOLO_EXECUTOR_COUNT"):
        AdaptiveWorkerOptions(
            8,
            (6, 4, 2, 1),
            3,
            120.0,
            5,
            tuple(range(215, 223)),
            yolo_executor_count=value,
        )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("fallback_worker_counts", (True,), "POSITIVE_INTEGER"),
        ("fallback_worker_counts", (0,), "POSITIVE_INTEGER"),
        ("initial_points_per_worker", True, "POSITIVE_INTEGER"),
        ("initial_points_per_worker", 0, "POSITIVE_INTEGER"),
        ("worker_start_timeout_s", True, "FINITE"),
        ("worker_start_timeout_s", 0.0, "FINITE"),
        ("max_infra_attempts_per_point", True, "POSITIVE_INTEGER"),
        ("max_infra_attempts_per_point", 0, "POSITIVE_INTEGER"),
        ("ros_domain_ids", (True,) + tuple(range(216, 223)), "ROS_DOMAIN_IDS"),
    ],
)
def test_options_reject_boolean_and_zero_values_at_each_numeric_boundary(
    field, value, error
):
    """YAML booleans and zeroes must not satisfy numeric pool boundaries."""

    from so101_demo.parallel_batch.adaptive_contracts import (
        AdaptiveWorkerOptions,
        ContractError,
    )

    values = {
        "worker_count": 8,
        "fallback_worker_counts": (6, 4, 2, 1),
        "initial_points_per_worker": 3,
        "worker_start_timeout_s": 120.0,
        "max_infra_attempts_per_point": 5,
        "ros_domain_ids": tuple(range(215, 223)),
        "yolo_executor_count": 2,
    }
    values[field] = value

    with pytest.raises(ContractError, match=error):
        AdaptiveWorkerOptions(**values)


@pytest.mark.parametrize(
    ("key", "value", "error"),
    [
        ("unexpected", 1, "UNKNOWN_CONFIG_FIELD"),
        ("worker_start_timeout_s", float("inf"), "FINITE"),
        ("worker_count", True, "POSITIVE_INTEGER"),
    ],
)
def test_config_rejects_unknown_nonfinite_and_boolean_values(tmp_path, key, value, error):
    """YAML coercion or schema drift must not silently alter pool safety limits."""

    from so101_demo.parallel_batch.adaptive_contracts import (
        ContractError,
        load_adaptive_worker_options,
    )

    document = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    document[key] = value
    path = tmp_path / "adaptive.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(ContractError, match=error):
        load_adaptive_worker_options(path)


def test_adaptive_request_rejects_relative_evidence_root(tmp_path):
    """A relative evidence root could let a batch escape its owned runtime tree."""

    from so101_demo.parallel_batch.adaptive_contracts import (
        AdaptiveBatchRequest,
        ContractError,
        load_adaptive_worker_options,
    )
    from so101_demo.parallel_batch.contracts import RunMode

    with pytest.raises(ContractError, match="ABSOLUTE_EVIDENCE_ROOT"):
        AdaptiveBatchRequest(
            batch_id="at01",
            run_mode=RunMode.EXECUTE,
            selected_point_ids=("p01",),
            options=load_adaptive_worker_options(CONFIG),
            evidence_root=Path("relative/evidence"),
        )


def test_adaptive_config_path_must_be_absolute():
    """Config lookup must not depend on the caller's working directory."""

    from so101_demo.parallel_batch.adaptive_contracts import (
        ContractError,
        load_adaptive_worker_options,
    )

    with pytest.raises(ContractError, match="ABSOLUTE_EVIDENCE_ROOT"):
        load_adaptive_worker_options(Path("parallel_adaptive_workers_v1.yaml"))


@pytest.mark.parametrize(
    ("batch_id", "error"),
    [
        ("abcdef", "BATCH_ID_LENGTH"),
        ("é", "INVALID_IDENTIFIER"),
        ("a.b", "INVALID_IDENTIFIER"),
    ],
)
def test_adaptive_batch_id_is_a_short_ascii_identifier(tmp_path, batch_id, error):
    """The user-facing run ID must keep every derived runtime path bounded."""

    from so101_demo.parallel_batch.adaptive_contracts import (
        AdaptiveBatchRequest,
        ContractError,
        load_adaptive_worker_options,
    )
    from so101_demo.parallel_batch.contracts import RunMode

    with pytest.raises(ContractError, match=error):
        AdaptiveBatchRequest(
            batch_id=batch_id,
            run_mode=RunMode.EXECUTE,
            selected_point_ids=("p01",),
            options=load_adaptive_worker_options(CONFIG),
            evidence_root=tmp_path,
        )


def test_pool_request_accepts_the_generation_scoped_internal_batch_id(tmp_path):
    """A production pool generation must keep its descriptive internal identity."""

    from so101_demo.parallel_batch.adaptive_contracts import (
        _new_pool_request_for_production_factory,
    )
    from so101_demo.parallel_batch.contracts import RunMode

    request = _new_pool_request_for_production_factory(
        batch_id="abcde-g01-w08",
        run_mode=RunMode.EXECUTE,
        selected_point_ids=("p01",),
        worker_count=8,
        evidence_root=tmp_path,
    )

    assert asdict(request) == {
        "batch_id": "abcde-g01-w08",
        "run_mode": RunMode.EXECUTE,
        "selected_point_ids": ("p01",),
        "worker_count": 8,
        "evidence_root": tmp_path,
        # The generation request carries the guard this run prepared; without it the allocator
        # refuses every level (START_GUARD_UNAVAILABLE).
        "start_guard": None,
    }

    guard = object()
    guarded = _new_pool_request_for_production_factory(
        batch_id="abcde-g02-w06",
        run_mode=RunMode.EXECUTE,
        selected_point_ids=("p01",),
        worker_count=6,
        evidence_root=tmp_path,
        start_guard=guard,
    )
    assert guarded.start_guard is guard


def test_pool_contract_has_no_lifetime_quota(tmp_path):
    """The adaptive pool request keeps affinity/fallback but has no lifetime K."""

    from so101_demo.parallel_batch.adaptive_contracts import (
        _new_pool_request_for_production_factory,
    )
    from so101_demo.parallel_batch.contracts import RunMode
    request = _new_pool_request_for_production_factory(
        batch_id='pool-a', run_mode=RunMode.EXECUTE, selected_point_ids=('p1', 'p2'),
        worker_count=2, evidence_root=tmp_path)
    assert not hasattr(request, 'max_points_per_worker')


