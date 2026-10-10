import pytest


def test_canonical_sha256_is_key_order_independent():
    from so101_demo.parallel_batch.canonical_json import canonical_sha256

    assert canonical_sha256({"b": 1, "a": 2}) == canonical_sha256({"a": 2, "b": 1})


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_canonical_sha256_rejects_nonfinite_input(value):
    from so101_demo.parallel_batch.canonical_json import canonical_sha256
    from so101_demo.parallel_batch.contracts import ContractError

    with pytest.raises(ContractError):
        canonical_sha256({"a": value})


def test_canonical_sha256_rejects_non_string_keys_and_foreign_types():
    from so101_demo.parallel_batch.canonical_json import canonical_sha256
    from so101_demo.parallel_batch.contracts import ContractError

    with pytest.raises(ContractError):
        canonical_sha256({1: "a"})
    with pytest.raises(ContractError):
        canonical_sha256({"a": object()})
