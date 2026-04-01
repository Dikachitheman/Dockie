"""
SQLAlchemy ORM models.

These map directly to database tables.
Kept separate from domain dataclasses to avoid coupling DB concerns to business logic.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2.types import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.config import get_settings


settings = get_settings()


def _embedding_column_type():
    if settings.knowledge_vector_backend.lower() == "pgvector":
        return Vector(settings.knowledge_embedding_dimensions)
    return ARRAY(Float)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Raw / quarantine tables
# ---------------------------------------------------------------------------

class RawEvent(Base):
    __tablename__ = "raw_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_payload_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class QuarantinedEvent(Base):
    __tablename__ = "quarantined_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    raw_event_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("raw_events.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_payload_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    quarantined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Vessels
# ---------------------------------------------------------------------------

class Vessel(Base):
    __tablename__ = "vessels"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    imo: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    mmsi: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    flag: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    positions: Mapped[list[Position]] = relationship(
        "Position", back_populates="vessel", lazy="select"
    )


# ---------------------------------------------------------------------------
# Positions (with PostGIS geometry)
# ---------------------------------------------------------------------------

class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        Index("ix_positions_mmsi_observed_at", "mmsi", "observed_at"),
        Index("ix_positions_imo_observed_at", "imo", "observed_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    vessel_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("vessels.id", ondelete="SET NULL"), nullable=True
    )
    mmsi: Mapped[str] = mapped_column(String(20), nullable=False)
    imo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vessel_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    # PostGIS geometry point (SRID 4326 = WGS84)
    geom = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    sog_knots: Mapped[float | None] = mapped_column(Float, nullable=True)
    cog_degrees: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_degrees: Mapped[float | None] = mapped_column(Float, nullable=True)
    navigation_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination_text: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_event_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("raw_events.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    vessel: Mapped[Vessel | None] = relationship("Vessel", back_populates="positions")


class LatestPosition(Base):
    __tablename__ = "latest_positions"
    __table_args__ = (
        Index("ix_latest_positions_imo_observed_at", "imo", "observed_at"),
    )

    mmsi: Mapped[str] = mapped_column(String(20), primary_key=True)
    imo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vessel_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    sog_knots: Mapped[float | None] = mapped_column(Float, nullable=True)
    cog_degrees: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_degrees: Mapped[float | None] = mapped_column(Float, nullable=True)
    navigation_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination_text: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_event_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("raw_events.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Shipments
# ---------------------------------------------------------------------------

class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. ship-001
    booking_ref: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    carrier: Mapped[str] = mapped_column(String(64), nullable=False)
    service_lane: Mapped[str | None] = mapped_column(String(256), nullable=True)
    load_port: Mapped[str | None] = mapped_column(String(8), nullable=True)
    discharge_port: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cargo_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    declared_departure_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    declared_eta_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    raw_event_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("raw_events.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    candidate_vessels: Mapped[list[ShipmentVessel]] = relationship(
        "ShipmentVessel", back_populates="shipment", lazy="select"
    )
    evidence_items: Mapped[list[Evidence]] = relationship(
        "Evidence", back_populates="shipment", lazy="select"
    )


class ShipmentVessel(Base):
    """Many-to-many link — a shipment may have candidate vessels."""
    __tablename__ = "shipment_vessels"
    __table_args__ = (UniqueConstraint("shipment_id", "vessel_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    shipment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False
    )
    vessel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("vessels.id", ondelete="CASCADE"), nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    shipment: Mapped[Shipment] = relationship("Shipment", back_populates="candidate_vessels")
    vessel: Mapped[Vessel] = relationship("Vessel")


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    shipment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)  # safe URLs only

    shipment: Mapped[Shipment] = relationship("Shipment", back_populates="evidence_items")


# ---------------------------------------------------------------------------
# Voyage signals
# ---------------------------------------------------------------------------

class VoyageSignal(Base):
    __tablename__ = "voyage_signals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    vessel_imo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vessel_mmsi: Mapped[str | None] = mapped_column(String(20), nullable=True)
    service_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination_text: Mapped[str | None] = mapped_column(String(256), nullable=True)
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    raw_event_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("raw_events.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Voyage events
# ---------------------------------------------------------------------------

class VoyageEvent(Base):
    __tablename__ = "voyage_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    shipment_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("shipments.id", ondelete="SET NULL"), nullable=True
    )
    vessel_imo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(128), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Carrier schedules / ETA revisions / port observations
# ---------------------------------------------------------------------------

class CarrierSchedule(Base):
    __tablename__ = "carrier_schedules"
    __table_args__ = (
        Index("ix_carrier_schedules_carrier_scraped_at", "carrier", "scraped_at"),
        Index("ix_carrier_schedules_vessel_imo_eta", "vessel_imo", "eta"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    carrier: Mapped[str] = mapped_column(String(64), nullable=False)
    voyage_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vessel_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    vessel_imo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    port_locode: Mapped[str] = mapped_column(String(10), nullable=False)
    etd: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_event_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("raw_events.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ETARevisionLog(Base):
    __tablename__ = "eta_revision_log"
    __table_args__ = (
        Index("ix_eta_revision_log_shipment_revision_at", "shipment_id", "revision_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    shipment_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("shipments.id", ondelete="CASCADE"), nullable=True
    )
    carrier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revision_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    previous_eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delta_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PortObservation(Base):
    __tablename__ = "port_observations"
    __table_args__ = (
        Index("ix_port_observations_port_observed_at", "port_locode", "observed_at"),
        Index("ix_port_observations_vessel_imo_observed_at", "vessel_imo", "observed_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    port_locode: Mapped[str] = mapped_column(String(10), nullable=False)
    terminal_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    vessel_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    vessel_imo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vessel_mmsi: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, default="observed")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_event_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("raw_events.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Tracking cases
# ---------------------------------------------------------------------------

class TrackingCase(Base):
    __tablename__ = "tracking_cases"

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    tracked_service_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tracked_voyage_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracked_imo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tracked_mmsi: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Source health
# ---------------------------------------------------------------------------

class SourceHealth(Base):
    __tablename__ = "source_health"
    __table_args__ = (UniqueConstraint("source"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_class: Mapped[str] = mapped_column(String(64), nullable=False)
    automation_safety: Mapped[str] = mapped_column(String(32), nullable=False)
    business_safe_default: Mapped[bool] = mapped_column(Boolean, default=True)
    source_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stale_after_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    degraded_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Reference ports (with PostGIS geometry for spatial queries)
# ---------------------------------------------------------------------------

class ReferencePort(Base):
    """Known ports with geographic coordinates for PostGIS spatial queries."""
    __tablename__ = "reference_ports"
    __table_args__ = (
        UniqueConstraint("locode"),
        Index("ix_reference_ports_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    locode: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    country: Mapped[str] = mapped_column(String(64), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geom = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    port_type: Mapped[str] = mapped_column(String(64), nullable=False, default="seaport")
    geofence_radius_nm: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Simulated intelligence tables
# ---------------------------------------------------------------------------

class PortCongestionReading(Base):
    __tablename__ = "port_congestion_readings"
    __table_args__ = (
        Index("ix_port_congestion_readings_port_observed", "port_locode", "observed_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    port_locode: Mapped[str] = mapped_column(String(10), nullable=False)
    delay_days: Mapped[float] = mapped_column(Float, nullable=False)
    queue_vessels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortCongestionSeasonality(Base):
    __tablename__ = "port_congestion_seasonality"
    __table_args__ = (
        UniqueConstraint("port_locode", "month"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    port_locode: Mapped[str] = mapped_column(String(10), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    median_wait_days: Mapped[float] = mapped_column(Float, nullable=False)
    p75_wait_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    p90_wait_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="simulated_seed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CarrierPerformanceMetric(Base):
    __tablename__ = "carrier_performance_metrics"
    __table_args__ = (
        UniqueConstraint("carrier", "service_lane", "year_month"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    carrier: Mapped[str] = mapped_column(String(64), nullable=False)
    service_lane: Mapped[str] = mapped_column(String(256), nullable=False)
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    median_delay_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    on_time_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ClearanceChecklist(Base):
    __tablename__ = "clearance_checklists"

    shipment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("shipments.id", ondelete="CASCADE"), primary_key=True
    )
    form_m_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bl_received: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paar_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paar_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customs_duty_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trucking_booked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DemurrageTariff(Base):
    __tablename__ = "demurrage_tariffs"
    __table_args__ = (
        UniqueConstraint("terminal_locode", "vehicle_type", "effective_from"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    terminal_locode: Mapped[str] = mapped_column(String(10), nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    free_days: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_rate_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_rate_ngn: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FXRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (
        Index("ix_fx_rates_pair_observed_at", "currency_pair", "observed_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    currency_pair: Mapped[str] = mapped_column(String(32), nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_source_type_ingested", "source_type", "ingested_at"),
        Index("ix_document_chunks_embedding_model_embedded_at", "embedding_model", "embedded_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    source_name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    shipment_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("shipments.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(_embedding_column_type(), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Standby agents
# ---------------------------------------------------------------------------

class StandbyAgent(Base):
    __tablename__ = "standby_agents"
    __table_args__ = (
        Index("ix_standby_agents_user_created", "user_id", "created_at"),
        Index("ix_standby_agents_status_next_run", "status", "next_run_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    shipment_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("shipments.id", ondelete="CASCADE"), nullable=True
    )
    condition_text: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False, default="general_watch")
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="notify")
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    rule_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fire_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_match_state: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StandbyAgentRun(Base):
    __tablename__ = "standby_agent_runs"
    __table_args__ = (
        Index("ix_standby_agent_runs_agent_started", "agent_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("standby_agents.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_executed: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentOutput(Base):
    __tablename__ = "agent_outputs"
    __table_args__ = (
        Index("ix_agent_outputs_user_created", "user_id", "created_at"),
        Index("ix_agent_outputs_type_created", "output_type", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("standby_agents.id", ondelete="SET NULL"), nullable=True
    )
    shipment_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("shipments.id", ondelete="SET NULL"), nullable=True
    )
    output_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    preview_text: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserNotification(Base):
    __tablename__ = "user_notifications"
    __table_args__ = (
        Index("ix_user_notifications_user_created", "user_id", "created_at"),
        Index("ix_user_notifications_user_unread", "user_id", "unread"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("standby_agents.id", ondelete="SET NULL"), nullable=True
    )
    output_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("agent_outputs.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="in_app")
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StandbyDigestQueue(Base):
    __tablename__ = "standby_digest_queue"
    __table_args__ = (
        Index("ix_standby_digest_queue_status_due", "status", "digest_due_at"),
        Index("ix_standby_digest_queue_user_due", "user_id", "digest_due_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("standby_agents.id", ondelete="SET NULL"), nullable=True
    )
    shipment_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("shipments.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    digest_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
