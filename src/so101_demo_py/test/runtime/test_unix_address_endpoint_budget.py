"""The endpoint names of one campaign directory fit the Darwin ``sun_path`` budget (pure string arithmetic, any host)."""

from so101_demo.runtime.unix_address import (
    DARWIN_SUN_PATH_CAPACITY_BYTES,
    ENDPOINT_NAMES,
    require_encoded_length,
)


def test_every_endpoint_name_fits_the_darwin_budget_for_the_longest_campaign_directory():
    base = "/private/tmp/so101-ipc-4294967295"  # the longest uid a 32-bit id can print
    campaign = f"{base}/b-" + "f" * (2 * 6)  # six random bytes, hex encoded
    for name in ENDPOINT_NAMES.values():
        require_encoded_length(f"{campaign}/{name}", capacity_bytes=DARWIN_SUN_PATH_CAPACITY_BYTES)


def test_the_worker_endpoints_are_named_after_their_worker_slots():
    assert ENDPOINT_NAMES["worker-0"] == "worker-0.sock"
    assert ENDPOINT_NAMES["worker-1"] == "worker-1.sock"
