"""Different filesystem endpoints cannot create two brokers for one ROS system."""
import os
import uuid
import pytest
from so101_demo.adapters.act.domain_authority import DomainAuthority


def test_same_domain_second_authority_is_rejected_until_owner_closes():
    domain=int(uuid.uuid4().hex[:12],16)
    first=DomainAuthority(domain).acquire()
    try:
        with pytest.raises(RuntimeError,match='CONTROL_BROKER_ALREADY_RUNNING'):
            DomainAuthority(domain).acquire()
        other=DomainAuthority(domain+1).acquire();other.close()
    finally:first.close()
    replacement=DomainAuthority(domain).acquire();replacement.close()


@pytest.mark.parametrize('domain',[-1,True,'193',None])
def test_domain_scope_is_closed(domain):
    with pytest.raises(ValueError):DomainAuthority(domain)
