import type {
  CarrierPerformance,
  EtaRevision,
  PortCongestionSummary,
  VesselAnomaly,
  DemurrageExposure,
  ShipmentComparison,
} from "./shipment-ui";

export const carrierPerformance: CarrierPerformance[] = [
  {
    carrier: "sallaum",
    serviceLane: "US -> West Africa -> Lagos",
    yearMonth: "2026-03",
    medianDelayDays: 1.8,
    onTimeRate: 0.72,
    sampleCount: 11,
    notes: "Usually reliable, but Lagos berth delays still create soft slippage.",
  },
  {
    carrier: "grimaldi",
    serviceLane: "US -> West Africa -> Lagos",
    yearMonth: "2026-03",
    medianDelayDays: 4.1,
    onTimeRate: 0.38,
    sampleCount: 9,
    notes: "This lane shows optimistic declared ETAs and more hull substitutions.",
  },
];

export const etaRevisions: EtaRevision[] = [
  {
    revisionAt: "2026-03-30T08:10:00Z",
    previousEta: "2026-04-03T00:00:00Z",
    newEta: "2026-04-05T00:00:00Z",
    deltaHours: 48,
    source: "scenario_eta_slip",
  },
];

export const portCongestion: PortCongestionSummary = {
  shipmentId: "ship-002",
  portLocode: "NGAPP",
  currentWaitDays: 2.5,
  p75WaitDays: 3.5,
  p90WaitDays: 5.0,
  seasonalMedianDays: 1.5,
  aboveSeasonalDays: 1.0,
  recentReadings: [
    { observedAt: "2026-03-29T09:00:00Z", delayDays: 0.5, queueVessels: 4, source: "simulated_gocomet" },
    { observedAt: "2026-03-30T09:00:00Z", delayDays: 1.0, queueVessels: 6, source: "simulated_gocomet" },
    { observedAt: "2026-03-31T09:00:00Z", delayDays: 2.5, queueVessels: 8, source: "scenario_eta_delay" },
  ],
};

export const vesselAnomaly: VesselAnomaly = {
  shipmentId: "ship-004",
  severity: "medium",
  summary: "Vessel has reported an unexpected course change and reduced speed.",
  indicators: ["speed_drop", "course_change"],
  recommendedAction: "Contact carrier and monitor AIS feed for reassessment.",
};

export const demurrageExposure: DemurrageExposure = {
  shipmentId: "ship-004",
  terminalLocode: "NGAPP",
  freeDays: 5,
  dailyRateNgn: 52000,
  dailyRateUsd: 35,
  projectedCostNgn: 156000,
  projectedCostUsd: 100,
  clearanceRiskDays: 3,
  riskLevel: "medium",
  freeDaysEnd: "2026-04-10T00:00:00Z",
  notes: ["Simulated exposure for demo"],
};

export const comparison: ShipmentComparison = {
  comparedAt: new Date().toISOString(),
  shipments: [
    { shipmentId: "ship-002", bookingReference: "BK-002", carrier: "grimaldi", status: "delayed", riskScore: 7.3, summary: "ETA slipped", freshness: "stale" },
    { shipmentId: "ship-004", bookingReference: "BK-004", carrier: "sallaum", status: "in_transit", riskScore: 4.1, summary: "At-sea, slower", freshness: "fresh" },
  ],
  recommendation: "Prioritise ship-002 for follow-up",
};

export default {
  carrierPerformance,
  etaRevisions,
  portCongestion,
  vesselAnomaly,
  demurrageExposure,
  comparison,
};
