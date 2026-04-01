"""
Pydantic schemas for API responses.

Separate from ORM models — used for serialization, validation, and agent tool output.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_serializer


class VesselSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    imo: Optional[str] = None
    mmsi: Optional[str] = None
    name: str


class PositionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    mmsi: str
    imo: Optional[str] = None
    vessel_name: Optional[str] = None
    latitude: float
    longitude: float
    sog_knots: Optional[float] = None
    cog_degrees: Optional[float] = None
    heading_degrees: Optional[float] = None
    navigation_status: Optional[str] = None
    destination_text: Optional[str] = None
    source: str
    observed_at: datetime


class EvidenceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    captured_at: datetime
    claim: str
    url: Optional[str] = None


class CandidateVesselSchema(BaseModel):
    vessel_id: str
    imo: Optional[str] = None
    mmsi: Optional[str] = None
    name: str
    is_primary: bool


class ShipmentSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    booking_ref: str
    carrier: str
    service_lane: Optional[str] = None
    load_port: Optional[str] = None
    discharge_port: Optional[str] = None
    cargo_type: Optional[str] = None
    units: Optional[int] = None
    status: str
    declared_departure_date: Optional[datetime] = None
    declared_eta_date: Optional[datetime] = None
    candidate_vessels: list[CandidateVesselSchema] = []


class ShipmentDetailSchema(ShipmentSummarySchema):
    candidate_vessels: list[CandidateVesselSchema] = []
    evidence: list[EvidenceSchema] = []


class ETAConfidenceSchema(BaseModel):
    confidence: float
    freshness: str
    explanation: str
    declared_eta: Optional[datetime] = None


class ShipmentStatusSchema(BaseModel):
    """Full copilot-friendly status for a shipment."""
    shipment_id: str
    booking_ref: str
    carrier: str
    status: str
    declared_eta: Optional[datetime] = None
    latest_position: Optional[PositionSchema] = None
    eta_confidence: ETAConfidenceSchema
    candidate_vessels: list[CandidateVesselSchema] = []
    evidence_count: int = 0
    freshness_warning: Optional[str] = None


class TrackPointSchema(BaseModel):
    latitude: float
    longitude: float
    sog_knots: Optional[float] = None
    cog_degrees: Optional[float] = None
    observed_at: datetime
    source: str


class ShipmentHistorySchema(BaseModel):
    shipment_id: str
    vessel_mmsi: Optional[str] = None
    vessel_name: Optional[str] = None
    track: list[TrackPointSchema] = []
    events: list[VoyageEventSchema] = []


class ShipmentBundleSchema(BaseModel):
    detail: ShipmentDetailSchema
    status: ShipmentStatusSchema
    history: ShipmentHistorySchema


class VoyageEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    event_at: datetime
    details: Optional[str] = None
    source: str


class SourceHealthSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    source_class: str
    automation_safety: str
    business_safe_default: bool
    source_status: str
    last_success_at: Optional[datetime] = None
    stale_after_seconds: int
    degraded_reason: Optional[str] = None
    updated_at: Optional[datetime] = None


class SourceReadinessSchema(BaseModel):
    source: str
    enabled: bool
    configured: bool
    mode: str
    role: str
    business_safe_default: bool
    detail: str


class KnowledgeSnippetSchema(BaseModel):
    source_name: str
    source_type: str
    content: str
    relevance_score: float
    metadata: dict[str, str | int | float | bool | None] = {}


class KnowledgeSearchResponseSchema(BaseModel):
    query: str
    shipment_id: Optional[str] = None
    snippets: list[KnowledgeSnippetSchema] = []
    retrieved_at: datetime


class FakeWebSourceSchema(BaseModel):
    id: str
    name: str
    base_url: str
    search_index_url: str
    source_class: str
    trust_level: str
    match_reason: Optional[str] = None


class FakeWebSearchResultSchema(BaseModel):
    id: str
    title: str
    url: str
    source: str
    source_id: str
    source_type: str
    source_class: str
    trust_level: str
    published: Optional[str] = None
    updated: Optional[str] = None
    summary: str
    snippet: str
    tags: list[str] = []
    relevance_score: float
    match_reason: str


class FakeWebSearchResponseSchema(BaseModel):
    query: str
    normalized_query: str
    topics: list[str] = []
    candidate_sources: list[FakeWebSourceSchema] = []
    results: list[FakeWebSearchResultSchema] = []
    retrieved_at: datetime
    search_mode: str = "remote_http"


class FakeWebSearchPlanResponseSchema(BaseModel):
    query: str
    normalized_query: str
    topics: list[str] = []
    candidate_sources: list[FakeWebSourceSchema] = []
    retrieved_at: datetime
    search_mode: str = "remote_http"


class ETARevisionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revision_at: datetime
    previous_eta: Optional[datetime] = None
    new_eta: Optional[datetime] = None
    delta_hours: Optional[float] = None
    source: str


class PortObservationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    port_locode: str
    terminal_name: Optional[str] = None
    vessel_name: Optional[str] = None
    vessel_imo: Optional[str] = None
    vessel_mmsi: Optional[str] = None
    status: Optional[str] = None
    event_type: str
    detail: Optional[str] = None
    source: str
    observed_at: datetime


class ClearanceChecklistSchema(BaseModel):
    shipment_id: str
    form_m_approved: bool
    bl_received: bool
    paar_submitted_at: Optional[datetime] = None
    paar_issued_at: Optional[datetime] = None
    customs_duty_paid: bool
    trucking_booked: bool
    notes: Optional[str] = None
    completion_ratio: float = 0.0
    missing_items: list[str] = []


class RealisticETASchema(BaseModel):
    shipment_id: str
    declared_eta: Optional[datetime] = None
    latest_position_source: Optional[str] = None
    latest_position_observed_at: Optional[datetime] = None
    estimated_anchor_arrival: Optional[datetime] = None
    realistic_berth_window_start: Optional[datetime] = None
    realistic_berth_window_end: Optional[datetime] = None
    realistic_release_window_start: Optional[datetime] = None
    realistic_release_window_end: Optional[datetime] = None
    congestion_level: str
    confidence_note: str
    supporting_factors: list[str] = []


class DemurrageExposureSchema(BaseModel):
    shipment_id: str
    terminal_locode: Optional[str] = None
    free_days: int
    daily_rate_ngn: float
    daily_rate_usd: Optional[float] = None
    projected_cost_ngn: float
    projected_cost_usd: Optional[float] = None
    clearance_risk_days: int
    risk_level: str
    free_days_end: Optional[datetime] = None
    notes: list[str] = []


class PortCongestionPointSchema(BaseModel):
    observed_at: datetime
    delay_days: float
    queue_vessels: Optional[int] = None
    source: str


class PortCongestionSummarySchema(BaseModel):
    shipment_id: str
    port_locode: Optional[str] = None
    current_wait_days: float = 0.0
    p75_wait_days: Optional[float] = None
    p90_wait_days: Optional[float] = None
    seasonal_median_days: Optional[float] = None
    above_seasonal_days: Optional[float] = None
    recent_readings: list[PortCongestionPointSchema] = []


class CarrierPerformanceSchema(BaseModel):
    carrier: str
    service_lane: str
    year_month: str
    median_delay_days: Optional[float] = None
    on_time_rate: Optional[float] = None
    sample_count: int
    notes: Optional[str] = None


class ShipmentComparisonItemSchema(BaseModel):
    shipment_id: str
    booking_ref: str
    carrier: str
    status: str
    risk_score: float
    summary: str
    freshness: str


class ShipmentComparisonSchema(BaseModel):
    compared_at: datetime
    shipments: list[ShipmentComparisonItemSchema] = []
    recommendation: Optional[str] = None


class VesselAnomalySchema(BaseModel):
    shipment_id: str
    severity: str
    summary: str
    indicators: list[str] = []
    recommended_action: Optional[str] = None


# ---------------------------------------------------------------------------
# PostGIS spatial query schemas
# ---------------------------------------------------------------------------

class NearbyVesselSchema(BaseModel):
    mmsi: str
    imo: Optional[str] = None
    vessel_name: Optional[str] = None
    latitude: float
    longitude: float
    sog_knots: Optional[float] = None
    cog_degrees: Optional[float] = None
    navigation_status: Optional[str] = None
    destination_text: Optional[str] = None
    source: str
    observed_at: Optional[str] = None
    distance_nm: Optional[float] = None


class NearbyVesselsResponseSchema(BaseModel):
    center_latitude: float
    center_longitude: float
    radius_nm: float
    vessel_count: int
    vessels: list[NearbyVesselSchema] = []


class NearestPortSchema(BaseModel):
    locode: str
    name: str
    country: str
    latitude: float
    longitude: float
    port_type: str
    geofence_radius_nm: float
    distance_nm: Optional[float] = None


class NearestPortResponseSchema(BaseModel):
    query_latitude: float
    query_longitude: float
    ports: list[NearestPortSchema] = []


class PortProximitySchema(BaseModel):
    within_geofence: bool
    locode: Optional[str] = None
    name: Optional[str] = None
    country: Optional[str] = None
    port_latitude: Optional[float] = None
    port_longitude: Optional[float] = None
    geofence_radius_nm: Optional[float] = None
    distance_nm: Optional[float] = None
    proximity_status: Optional[str] = None


class VesselPortProximitySchema(BaseModel):
    mmsi: str
    imo: Optional[str] = None
    vessel_name: Optional[str] = None
    latitude: float
    longitude: float
    observed_at: Optional[str] = None
    port_proximity: Optional[PortProximitySchema] = None
    nearest_port: Optional[NearestPortSchema] = None


class ReferencePortSchema(BaseModel):
    locode: str
    name: str
    country: str
    latitude: float
    longitude: float
    port_type: str
    geofence_radius_nm: float


class VesselSwapSchema(BaseModel):
    shipment_id: str
    confidence: float
    hypothesis: str
    primary_vessel: Optional[str] = None
    secondary_vessel: Optional[str] = None
    supporting_signals: list[str] = []
    recommended_action: Optional[str] = None


class StandbyAgentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    user_email: Optional[str] = None
    shipment_id: Optional[str] = None
    condition_text: str
    trigger_type: str
    action: str
    interval_seconds: int
    cooldown_seconds: int
    status: str
    last_checked_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    last_fired_at: Optional[datetime] = None
    fire_count: int
    last_result: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class StandbyAgentRunSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    matched: bool
    result_text: Optional[str] = None
    action_executed: Optional[str] = None
    created_at: Optional[datetime] = None


class UserNotificationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    agent_id: Optional[str] = None
    output_id: Optional[str] = None
    channel: str
    title: str
    detail: str
    unread: bool
    read_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class AgentOutputSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    agent_id: Optional[str] = None
    shipment_id: Optional[str] = None
    output_type: str
    title: str
    preview_text: str
    content: str
    metadata_: dict | None = None
    created_at: Optional[datetime] = None


class AppBootstrapSchema(BaseModel):
    shipments: list[ShipmentSummarySchema] = []
    source_health: list[SourceHealthSchema] = []
    standby_agents: list[StandbyAgentSchema] = []
    notifications: list[UserNotificationSchema] = []
    agent_outputs: list[AgentOutputSchema] = []


# Rebuild to resolve forward refs
ShipmentHistorySchema.model_rebuild()
