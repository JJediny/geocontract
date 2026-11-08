"""Tests for contract_utils shared module."""

from geocontract_tools.contract_utils import (
    extract_custom_property,
    is_citizen_proposal,
)


def test_is_citizen_proposal_true() -> None:
    """Contract with isCitizenInitiated=true is detected."""
    contract = {
        "customProperties": [
            {"property": "isCitizenInitiated", "value": True},
            {"property": "jurisdiction", "value": "Groton, CT"},
        ]
    }
    assert is_citizen_proposal(contract) is True


def test_is_citizen_proposal_false() -> None:
    """Contract without isCitizenInitiated is not detected."""
    contract = {
        "customProperties": [
            {"property": "jurisdiction", "value": "Groton, CT"},
        ]
    }
    assert is_citizen_proposal(contract) is False


def test_is_citizen_proposal_missing_custom_properties() -> None:
    """Contract without customProperties is not detected."""
    contract = {}
    assert is_citizen_proposal(contract) is False


def test_is_citizen_proposal_false_value() -> None:
    """Contract with isCitizenInitiated=false is not detected."""
    contract = {
        "customProperties": [
            {"property": "isCitizenInitiated", "value": False},
        ]
    }
    assert is_citizen_proposal(contract) is False


def test_extract_custom_property_found() -> None:
    """Extract existing custom property."""
    contract = {
        "customProperties": [
            {"property": "jurisdiction", "value": "Groton, CT"},
            {"property": "accessClass", "value": "public"},
        ]
    }
    assert extract_custom_property(contract, "jurisdiction") == "Groton, CT"
    assert extract_custom_property(contract, "accessClass") == "public"


def test_extract_custom_property_not_found() -> None:
    """Missing property returns None."""
    contract = {
        "customProperties": [
            {"property": "jurisdiction", "value": "Groton, CT"},
        ]
    }
    assert extract_custom_property(contract, "accessClass") is None


def test_extract_custom_property_none_value() -> None:
    """Property with null value returns None."""
    contract = {
        "customProperties": [
            {"property": "jurisdiction", "value": None},
        ]
    }
    assert extract_custom_property(contract, "jurisdiction") is None


def test_extract_custom_property_missing_custom_properties() -> None:
    """Contract without customProperties returns None."""
    contract = {}
    assert extract_custom_property(contract, "jurisdiction") is None
