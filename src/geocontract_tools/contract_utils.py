"""Shared utilities for working with ODCS contracts.

This module consolidates logic that was duplicated across harvester.py and
citizen_source_manifest.py to avoid silent drift.
"""

from __future__ import annotations


def is_citizen_proposal(contract: dict) -> bool:
    """Check if a contract is a citizen-initiated proposal.

    Citizen proposals carry customProperties: { property: isCitizenInitiated, value: true }.
    """
    custom_props = contract.get("customProperties") or []
    return any(
        prop.get("property") == "isCitizenInitiated" and prop.get("value") is True
        for prop in custom_props
    )


def extract_custom_property(contract: dict, property_name: str) -> str | None:
    """Extract a value from customProperties by property name."""
    custom_props = contract.get("customProperties") or []
    for prop in custom_props:
        if prop.get("property") == property_name:
            value = prop.get("value")
            return str(value) if value is not None else None
    return None
