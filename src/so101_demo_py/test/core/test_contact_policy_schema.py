"""The contact policy has one schema; the diagnostic proposal is a different kind with its own header."""

import pytest

from so101_demo.core import contact_policy


def test_a_contact_policy_of_another_schema_is_refused():
    for version in (1, 2, 4, "3", True):
        with pytest.raises(ValueError, match="contact policy schema_version must be 3"):
            contact_policy._validate_proposal_content({"schema_version": version})


def _diagnostic_header(**change):
    document = {key: None for key in contact_policy._DIAGNOSTIC_PROPOSAL_KEYS}
    document.update(dict(schema_version=1, kind="diagnostic_contact_proposal"), **change)
    return document


def test_the_diagnostic_proposal_is_its_own_kind_not_a_contact_policy_schema():
    assert contact_policy.DIAGNOSTIC_CONTACT_PROPOSAL_KIND == "diagnostic_contact_proposal"
    with pytest.raises(ValueError, match="kind must be diagnostic_contact_proposal"):
        contact_policy.validate_dynamic_diagnostic_proposal(_diagnostic_header(kind="contact_policy"))
    for version in (4, 2, True):
        with pytest.raises(ValueError, match="schema_version must be 1"):
            contact_policy.validate_dynamic_diagnostic_proposal(_diagnostic_header(schema_version=version))
    with pytest.raises(ValueError, match="unsupported diagnostic proposal_kind"):
        contact_policy.validate_dynamic_diagnostic_proposal(_diagnostic_header())
