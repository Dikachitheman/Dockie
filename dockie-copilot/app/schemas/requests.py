from __future__ import annotations

from pydantic import BaseModel, Field


class ManualShipmentCreateRequest(BaseModel):
    shipment_label: str = Field(min_length=3, max_length=80)
    vessel_name: str = Field(min_length=2, max_length=256)
    mmsi: str = Field(min_length=5, max_length=20)
    imo: str | None = Field(default=None, max_length=20)
    carrier: str = Field(default="manual_tracking", min_length=2, max_length=64)
    service_lane: str | None = Field(default="Manual live tracking")
    load_port: str | None = Field(default=None, max_length=16)
    discharge_port: str | None = Field(default=None, max_length=16)
    cargo_type: str | None = Field(default="tracked vessel")
    units: int | None = Field(default=1, ge=1)
    declared_departure_date: str | None = None
    declared_eta_date: str | None = None


class StandbyAgentCreateRequest(BaseModel):
    condition_text: str = Field(min_length=3, max_length=2000)
    action: str = Field(default="notify", pattern="^(notify|email|digest|log|report|spreadsheet|document)$")
    interval_seconds: int = Field(default=3600, ge=10, le=86400)
    shipment_id: str | None = Field(default=None, max_length=64)


class StandbyAgentUpdateRequest(BaseModel):
    condition_text: str | None = Field(default=None, min_length=3, max_length=2000)
    action: str | None = Field(default=None, pattern="^(notify|email|digest|log|report|spreadsheet|document)$")
    interval_seconds: int | None = Field(default=None, ge=10, le=86400)
    status: str | None = Field(default=None, pattern="^(active|paused|fired)$")


class NotificationReadRequest(BaseModel):
    notification_ids: list[str] = Field(default_factory=list)
