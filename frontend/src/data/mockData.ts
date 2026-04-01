export interface Vessel {
  name: string;
  imo: string;
  mmsi: string;
}

export interface VesselPosition {
  source: string;
  observedAt: string;
  mmsi: string;
  imo: string;
  vesselName: string;
  latitude: number;
  longitude: number;
  speedKnots: number;
  courseDegrees: number | null;
  headingDegrees: number | null;
  navStatus: string;
  destination: string;
}

export interface HistoryPoint {
  observedAt: string;
  latitude: number;
  longitude: number;
  speedKnots: number;
  source: string;
}

export interface ShipmentEvent {
  eventType: string;
  eventAt: string;
  details: string;
}

export interface Evidence {
  source: string;
  capturedAt: string;
  claim: string;
}

export interface Shipment {
  shipmentId: string;
  bookingReference: string;
  carrier: string;
  serviceLane: string;
  loadPort: string;
  loadPortCode: string;
  dischargePort: string;
  dischargePortCode: string;
  cargoType: string;
  units: number;
  declaredDepartureDate: string;
  declaredEtaDate: string;
  status: "booked" | "assigned" | "in_transit" | "delivered" | "delayed";
  candidateVessels: Vessel[];
  evidence: Evidence[];
  currentPosition: VesselPosition | null;
  historyPoints: HistoryPoint[];
  events: ShipmentEvent[];
}

export interface SourceHealth {
  source: string;
  sourceClass: string;
  sourceStatus: string;
  lastSuccessAt: string;
  staleAfterSeconds: number;
  parserVersion: number;
  degradedReason: string | null;
}

export const vessels: Vessel[] = [
  { name: "GREAT TEMA", imo: "9919876", mmsi: "311000222" },
  { name: "GREAT ABIDJAN", imo: "9935040", mmsi: "357123000" },
  { name: "GREAT COTONOU", imo: "9922345", mmsi: "311000111" },
];

export const shipments: Shipment[] = [
  {
    shipmentId: "ship-001",
    bookingReference: "SAL-LAG-24001",
    carrier: "sallaum",
    serviceLane: "US → West Africa → Lagos",
    loadPort: "Baltimore, US",
    loadPortCode: "USBAL",
    dischargePort: "Lagos, Nigeria",
    dischargePortCode: "NGLOS",
    cargoType: "ro-ro vehicles",
    units: 42,
    declaredDepartureDate: "2026-03-18",
    declaredEtaDate: "2026-04-02",
    status: "in_transit",
    candidateVessels: [{ name: "GREAT ABIDJAN", imo: "9935040", mmsi: "357123000" }],
    evidence: [
      { source: "carrier_schedule", capturedAt: "2026-03-18T08:12:00Z", claim: "Lagos discharge expected early April" },
    ],
    currentPosition: {
      source: "aisstream",
      observedAt: "2026-03-20T12:00:00Z",
      mmsi: "357123000",
      imo: "9935040",
      vesselName: "GREAT ABIDJAN",
      latitude: 5.25,
      longitude: 3.85,
      speedKnots: 14.2,
      courseDegrees: 92.5,
      headingDegrees: 91,
      navStatus: "under_way_using_engine",
      destination: "LAGOS",
    },
    historyPoints: [
      { observedAt: "2026-03-19T00:00:00Z", latitude: 4.1, longitude: -8.9, speedKnots: 15.1, source: "historical_ais" },
      { observedAt: "2026-03-19T12:00:00Z", latitude: 4.62, longitude: -2.1, speedKnots: 14.7, source: "historical_ais" },
      { observedAt: "2026-03-20T00:00:00Z", latitude: 4.97, longitude: 1.3, speedKnots: 14.4, source: "historical_ais" },
      { observedAt: "2026-03-20T12:00:00Z", latitude: 5.25, longitude: 3.85, speedKnots: 14.2, source: "aisstream" },
    ],
    events: [
      { eventType: "schedule_eta_recorded", eventAt: "2026-03-18T08:12:00Z", details: "Carrier schedule declared 2026-04-02 Lagos ETA" },
      { eventType: "departure_detected", eventAt: "2026-03-18T14:00:00Z", details: "Vessel departed Baltimore" },
      { eventType: "lagos_expected_detected", eventAt: "2026-03-20T12:00:00Z", details: "Destination text set to LAGOS" },
    ],
  },
  {
    shipmentId: "ship-002",
    bookingReference: "GRI-LAG-24007",
    carrier: "grimaldi",
    serviceLane: "US → West Africa → Lagos",
    loadPort: "Savannah, US",
    loadPortCode: "USSAV",
    dischargePort: "Apapa, Nigeria",
    dischargePortCode: "NGAPP",
    cargoType: "rolling equipment",
    units: 11,
    declaredDepartureDate: "2026-03-16",
    declaredEtaDate: "2026-03-31",
    status: "in_transit",
    candidateVessels: [{ name: "GREAT COTONOU", imo: "9922345", mmsi: "311000111" }],
    evidence: [
      { source: "carrier_fleet_context", capturedAt: "2026-03-17T10:05:00Z", claim: "Service rotation may swap hulls late in voyage planning" },
    ],
    currentPosition: {
      source: "orbcomm",
      observedAt: "2026-03-20T12:06:00Z",
      mmsi: "311000111",
      imo: "9922345",
      vesselName: "GREAT COTONOU",
      latitude: 4.91,
      longitude: 2.44,
      speedKnots: 12.8,
      courseDegrees: null,
      headingDegrees: null,
      navStatus: "under_way_using_engine",
      destination: "APAPA",
    },
    historyPoints: [
      { observedAt: "2026-03-17T00:00:00Z", latitude: 32.08, longitude: -81.09, speedKnots: 0, source: "historical_ais" },
      { observedAt: "2026-03-17T18:00:00Z", latitude: 30.5, longitude: -79.5, speedKnots: 13.2, source: "historical_ais" },
      { observedAt: "2026-03-18T12:00:00Z", latitude: 27.2, longitude: -75.1, speedKnots: 14.1, source: "historical_ais" },
      { observedAt: "2026-03-19T12:00:00Z", latitude: 18.5, longitude: -55.3, speedKnots: 13.9, source: "historical_ais" },
      { observedAt: "2026-03-20T12:06:00Z", latitude: 4.91, longitude: 2.44, speedKnots: 12.8, source: "orbcomm" },
    ],
    events: [
      { eventType: "schedule_eta_recorded", eventAt: "2026-03-16T06:00:00Z", details: "Carrier schedule declared 2026-03-31 Apapa ETA" },
      { eventType: "departure_detected", eventAt: "2026-03-17T08:00:00Z", details: "Vessel departed Savannah" },
    ],
  },
  {
    shipmentId: "ship-003",
    bookingReference: "SAL-LAG-24012",
    carrier: "sallaum",
    serviceLane: "US → West Africa → Lagos",
    loadPort: "Houston, US",
    loadPortCode: "USHOU",
    dischargePort: "Lagos, Nigeria",
    dischargePortCode: "NGLOS",
    cargoType: "ro-ro vehicles",
    units: 28,
    declaredDepartureDate: "2026-04-05",
    declaredEtaDate: "2026-04-22",
    status: "booked",
    candidateVessels: [{ name: "GREAT TEMA", imo: "9919876", mmsi: "311000222" }],
    evidence: [],
    currentPosition: null,
    historyPoints: [],
    events: [
      { eventType: "booking_confirmed", eventAt: "2026-03-22T09:00:00Z", details: "Booking confirmed for 28 units" },
    ],
  },
];

export const sourceHealth: SourceHealth[] = [
  { source: "aisstream", sourceClass: "public_api_terms", sourceStatus: "healthy", lastSuccessAt: "2026-03-22T18:34:07Z", staleAfterSeconds: 3600, parserVersion: 2, degradedReason: null },
  { source: "orbcomm", sourceClass: "noncommercial_or_license_limited", sourceStatus: "healthy", lastSuccessAt: "2026-03-22T16:32:37Z", staleAfterSeconds: 7200, parserVersion: 1, degradedReason: null },
  { source: "grimaldi", sourceClass: "public_api_terms", sourceStatus: "healthy", lastSuccessAt: "2026-03-24T11:06:09Z", staleAfterSeconds: 86400, parserVersion: 1, degradedReason: null },
  { source: "sallaum", sourceClass: "public_api_terms", sourceStatus: "healthy", lastSuccessAt: "2026-03-24T11:10:12Z", staleAfterSeconds: 86400, parserVersion: 1, degradedReason: null },
  { source: "nigerian_ports", sourceClass: "analyst_reference_only", sourceStatus: "manual", lastSuccessAt: "2026-03-20T11:55:43Z", staleAfterSeconds: 172800, parserVersion: 1, degradedReason: null },
  { source: "official_sanctions", sourceClass: "open_data", sourceStatus: "healthy", lastSuccessAt: "2026-03-20T11:56:01Z", staleAfterSeconds: 604800, parserVersion: 1, degradedReason: null },
];

export function getShipmentById(id: string): Shipment | undefined {
  return shipments.find(s => s.shipmentId === id);
}

export function formatStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

export function getStatusColor(status: string): string {
  switch (status) {
    case "in_transit": return "status-transit";
    case "booked": return "status-booked";
    case "assigned": return "status-assigned";
    case "delivered": return "status-delivered";
    case "delayed": return "status-delayed";
    default: return "muted-foreground";
  }
}

export function getDaysRemaining(etaDate: string): number {
  const now = new Date("2026-03-24");
  const eta = new Date(etaDate);
  return Math.max(0, Math.ceil((eta.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)));
}

export function getProgressPercent(departureDate: string, etaDate: string): number {
  const now = new Date("2026-03-24");
  const dep = new Date(departureDate);
  const eta = new Date(etaDate);
  const total = eta.getTime() - dep.getTime();
  const elapsed = now.getTime() - dep.getTime();
  return Math.min(100, Math.max(0, Math.round((elapsed / total) * 100)));
}
