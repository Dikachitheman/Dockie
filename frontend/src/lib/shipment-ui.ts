export interface Vessel {
  vesselId?: string;
  name: string;
  imo: string | null;
  mmsi: string | null;
  isPrimary?: boolean;
}

export interface VesselPosition {
  source: string;
  observedAt: string;
  mmsi: string;
  imo: string | null;
  vesselName: string | null;
  latitude: number;
  longitude: number;
  speedKnots: number | null;
  courseDegrees: number | null;
  headingDegrees: number | null;
  navStatus: string | null;
  destination: string | null;
}

export interface HistoryPoint {
  observedAt: string;
  latitude: number;
  longitude: number;
  speedKnots: number | null;
  courseDegrees: number | null;
  source: string;
}

export interface ShipmentEvent {
  eventType: string;
  eventAt: string;
  details: string | null;
  source?: string;
}

export interface Evidence {
  source: string;
  capturedAt: string;
  claim: string;
  url?: string | null;
}

export interface EtaConfidence {
  score: number;
  freshness: string;
  explanation: string;
  declaredEta?: string | null;
}

export interface Shipment {
  shipmentId: string;
  bookingReference: string;
  carrier: string;
  serviceLane: string | null;
  loadPort: string | null;
  loadPortCode?: string | null;
  dischargePort: string | null;
  dischargePortCode?: string | null;
  cargoType: string | null;
  units: number | null;
  declaredDepartureDate: string | null;
  declaredEtaDate: string | null;
  status: "booked" | "assigned" | "in_transit" | "delivered" | "delayed" | "open";
  candidateVessels: Vessel[];
  evidence: Evidence[];
  currentPosition: VesselPosition | null;
  historyPoints: HistoryPoint[];
  events: ShipmentEvent[];
  evidenceCount?: number;
  freshnessWarning?: string | null;
  etaConfidence?: EtaConfidence | null;
}

export interface SourceHealth {
  source: string;
  sourceClass: string;
  sourceStatus: string;
  lastSuccessAt: string | null;
  staleAfterSeconds: number;
  automationSafety: string;
  businessSafeDefault: boolean;
  degradedReason: string | null;
  updatedAt: string | null;
}

export interface SourceReadiness {
  source: string;
  enabled: boolean;
  configured: boolean;
  mode: string;
  role: string;
  businessSafeDefault: boolean;
  detail: string;
}

export interface KnowledgeSnippet {
  sourceName: string;
  sourceType: string;
  content: string;
  relevanceScore: number;
  metadata: Record<string, string | number | boolean | null | undefined>;
}

export interface WebSearchSource {
  id: string;
  name: string;
  baseUrl: string;
  searchIndexUrl: string;
  sourceClass: string;
  trustLevel: string;
  matchReason?: string | null;
}

export interface WebSearchSourcePlan extends WebSearchSource {
  status?: "queued" | "done";
}

export interface WebSearchResult {
  id: string;
  title: string;
  url: string;
  source: string;
  sourceId: string;
  sourceType: string;
  sourceClass: string;
  trustLevel: string;
  published?: string | null;
  updated?: string | null;
  summary: string;
  snippet: string;
  tags: string[];
  relevanceScore: number;
  matchReason: string;
}

export interface DemurrageExposure {
  shipmentId: string;
  terminalLocode: string | null;
  freeDays: number;
  dailyRateNgn: number;
  dailyRateUsd: number | null;
  projectedCostNgn: number;
  projectedCostUsd: number | null;
  clearanceRiskDays: number;
  riskLevel: "low" | "medium" | "high" | string;
  freeDaysEnd: string | null;
  notes: string[];
}

export interface ShipmentComparisonItem {
  shipmentId: string;
  bookingReference: string;
  carrier: string;
  status: string;
  riskScore: number;
  summary: string;
  freshness: string;
}

export interface ShipmentComparison {
  comparedAt: string;
  shipments: ShipmentComparisonItem[];
  recommendation: string | null;
}

export interface EtaRevision {
  revisionAt: string;
  previousEta: string | null;
  newEta: string | null;
  deltaHours: number | null;
  source: string;
}

export interface PortCongestionPoint {
  observedAt: string;
  delayDays: number;
  queueVessels: number | null;
  source: string;
}

export interface PortCongestionSummary {
  shipmentId: string;
  portLocode: string | null;
  currentWaitDays: number;
  p75WaitDays: number | null;
  p90WaitDays: number | null;
  seasonalMedianDays: number | null;
  aboveSeasonalDays: number | null;
  recentReadings: PortCongestionPoint[];
}

export interface CarrierPerformance {
  carrier: string;
  serviceLane: string;
  yearMonth: string;
  medianDelayDays: number | null;
  onTimeRate: number | null;
  sampleCount: number;
  notes: string | null;
}

export interface VesselAnomaly {
  shipmentId: string;
  severity: string;
  summary: string;
  indicators: string[];
  recommendedAction: string | null;
}

// PostGIS spatial query types

export interface NearestPort {
  locode: string;
  name: string;
  country: string;
  latitude: number;
  longitude: number;
  portType: string;
  geofenceRadiusNm: number;
  distanceNm: number | null;
}

export interface PortProximity {
  withinGeofence: boolean;
  locode: string | null;
  name: string | null;
  country: string | null;
  portLatitude: number | null;
  portLongitude: number | null;
  geofenceRadiusNm: number | null;
  distanceNm: number | null;
  proximityStatus: string | null;
}

export interface VesselPortProximity {
  mmsi: string;
  imo: string | null;
  vesselName: string | null;
  latitude: number;
  longitude: number;
  observedAt: string | null;
  portProximity: PortProximity | null;
  nearestPort: NearestPort | null;
}

export interface NearbyVessel {
  mmsi: string;
  imo: string | null;
  vesselName: string | null;
  latitude: number;
  longitude: number;
  sogKnots: number | null;
  cogDegrees: number | null;
  navigationStatus: string | null;
  destinationText: string | null;
  source: string;
  observedAt: string | null;
  distanceNm: number | null;
}

export interface ReferencePort {
  locode: string;
  name: string;
  country: string;
  latitude: number;
  longitude: number;
  portType: string;
  geofenceRadiusNm: number;
}

export function formatStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function getDaysRemaining(etaDate: string | null): number {
  if (!etaDate) return 0;
  const now = new Date();
  const eta = new Date(etaDate);
  return Math.max(0, Math.ceil((eta.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)));
}

export function getProgressPercent(departureDate: string | null, etaDate: string | null): number {
  if (!departureDate || !etaDate) return 0;
  const now = new Date();
  const dep = new Date(departureDate);
  const eta = new Date(etaDate);
  const total = eta.getTime() - dep.getTime();
  if (total <= 0) return 0;
  const elapsed = now.getTime() - dep.getTime();
  return Math.min(100, Math.max(0, Math.round((elapsed / total) * 100)));
}
