"""Where this service is allowed to listen.

A leaf module on purpose: both the legacy Teleop factory and the unified factory need this rule,
and putting it here is what lets either of them import it without an import cycle between them.
"""

from __future__ import annotations

import ipaddress

#: Tailscale's CGNAT range, which this deployment treats as a private, approved network.
APPROVED_SHARED_RANGE = "100.64.0.0/10"


def validate_bind_address(address: str) -> str:
    """Accept loopback and the approved shared range; refuse anything else."""
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as error:
        raise ValueError("BIND_ADDRESS_UNSAFE") from error
    if not (
        parsed.is_loopback
        or (isinstance(parsed, ipaddress.IPv4Address) and parsed in ipaddress.ip_network(APPROVED_SHARED_RANGE))
    ):
        raise ValueError("BIND_ADDRESS_UNSAFE")
    return address
