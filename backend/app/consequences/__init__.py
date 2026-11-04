"""Consequences & Change-Impact Analysis module (Sprint 0).

Provides schemas and data structures for impact analysis reports, check results,
and consequence assessment prior to requirement modification (US-11, FR-24, FR-25).
"""

from app.consequences.schemas import (
    CheckResult,
    CheckStatus,
    CheckType,
    ImpactItem,
    ImpactReport,
    ImpactStatus,
    ImpactType,
)

__all__ = [
    "CheckResult",
    "CheckStatus",
    "CheckType",
    "ImpactItem",
    "ImpactReport",
    "ImpactStatus",
    "ImpactType",
]
