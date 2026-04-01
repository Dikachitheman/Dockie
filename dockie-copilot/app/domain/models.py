"""
Domain models — pure Python dataclasses.

No SQLAlchemy, no HTTP, no side effects.
These are the canonical business entities the rest of the system reasons about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ShipmentStatus(str, Enum):
    OPEN = "open"
    IN_TRANSIT = "in_transit"
    ARRIVED = "arrived"
    CANCELLED = "cancelled"


class FreshnessLevel(str, Enum):
    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    UNKNOWN = "unknown"


class SourceClass(str, Enum):
    OPEN_DATA = "open_data"
    PUBLIC_API_TERMS = "public_api_terms"
    NONCOMMERCIAL_OR_LICENSE_LIMITED = "noncommercial_or_license_limited"
    ANALYST_REFERENCE_ONLY = "analyst_reference_only"


class AutomationSafety(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    FRAGILE_SCRAPER = "fragile_scraper"
    VALIDATION_REQUIRED = "validation_required"
    HUMAN_IN_LOOP = "human_in_loop"


@dataclass
class Position:
    mmsi: str
    latitude: float
    longitude: float
    observed_at: datetime
    source: str
    imo: Optional[str] = None
    vessel_name: Optional[str] = None
    sog_knots: Optional[float] = None
    cog_degrees: Optional[float] = None
    heading_degrees: Optional[float] = None
    navigation_status: Optional[str] = None
    destination_text: Optional[str] = None


@dataclass
class Vessel:
    imo: str
    name: str
    mmsi: Optional[str] = None
    flag: Optional[str] = None


@dataclass
class Evidence:
    source: str
    captured_at: datetime
    claim: str
    url: Optional[str] = None  # validated safe URL only


@dataclass
class Shipment:
    shipment_id: str
    booking_ref: str
    carrier: str
    service_lane: str
    load_port: str
    discharge_port: str
    cargo_type: str
    units: int
    status: ShipmentStatus = ShipmentStatus.OPEN
    declared_departure_date: Optional[datetime] = None
    declared_eta_date: Optional[datetime] = None
    candidate_vessel_imos: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    latest_position: Optional[Position] = None


@dataclass
class SourceHealth:
    source: str
    source_class: SourceClass
    automation_safety: AutomationSafety
    business_safe_default: bool
    source_status: str  # healthy / degraded / stale / manual
    last_success_at: Optional[datetime]
    stale_after_seconds: int
    degraded_reason: Optional[str] = None


@dataclass
class VoyageEvent:
    event_type: str
    event_at: datetime
    details: str
    source: str = "system"


@dataclass
class ETAConfidence:
    confidence: float          # 0.0 – 1.0
    freshness: FreshnessLevel
    explanation: str
    declared_eta: Optional[datetime] = None
    estimated_eta: Optional[datetime] = None
