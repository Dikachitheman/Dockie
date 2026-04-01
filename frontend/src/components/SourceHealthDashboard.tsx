import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, CheckCircle, ShieldAlert, XCircle } from "lucide-react";
import {
  compareShipments,
  getDemurrageExposure,
  getEtaRevisions,
  getPortCongestionSummary,
  getVesselAnomaly,
  listCarrierPerformance,
} from "@/lib/api";
import type {
  CarrierPerformance,
  DemurrageExposure,
  EtaRevision,
  PortCongestionSummary,
  Shipment,
  ShipmentComparison,
  SourceHealth,
  VesselAnomaly,
} from "@/lib/shipment-ui";

interface SourceHealthDashboardProps {
  sourceHealth: SourceHealth[];
  shipments: Shipment[];
  loading?: boolean;
  error?: string | null;
  onAsk?: (prompt: string) => void;
}

function StatusIcon({ status }: { status: string }) {
  if (status === "healthy") return <CheckCircle className="h-[18px] w-[18px] text-apple-green" strokeWidth={1.5} />;
  if (status === "degraded" || status === "manual") return <AlertTriangle className="h-[18px] w-[18px] text-apple-amber" strokeWidth={1.5} />;
  return <XCircle className="h-[18px] w-[18px] text-apple-red" strokeWidth={1.5} />;
}

function formatShortDate(value: string | null) {
  if (!value) return "Unknown";
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function barTone(status: string) {
  if (status === "healthy") return "bg-[#639922]";
  if (status === "degraded" || status === "manual") return "bg-[#ba7517]";
  return "bg-[#e24b4a]";
}

function sourceBarWidth(source: SourceHealth) {
  if (!source.lastSuccessAt) return 8;
  const ageSeconds = (Date.now() - new Date(source.lastSuccessAt).getTime()) / 1000;
  const freshnessRatio = Math.max(0.08, 1 - (ageSeconds / Math.max(source.staleAfterSeconds, 1)));
  return Math.round(freshnessRatio * 100);
}

export default function SourceHealthDashboard({
  sourceHealth,
  shipments,
  loading = false,
  error = null,
  onAsk,
}: SourceHealthDashboardProps) {
  const [etaRevisions, setEtaRevisions] = useState<EtaRevision[]>([]);
  const [portCongestion, setPortCongestion] = useState<PortCongestionSummary | null>(null);
  const [carrierPerformance, setCarrierPerformance] = useState<CarrierPerformance[]>([]);
  const [vesselAnomaly, setVesselAnomaly] = useState<VesselAnomaly | null>(null);
  const [demurrageExposure, setDemurrageExposure] = useState<DemurrageExposure | null>(null);
  const [comparison, setComparison] = useState<ShipmentComparison | null>(null);
  const [useDummyData, setUseDummyData] = useState<boolean>(() => {
    try {
      return localStorage.getItem("useDummyData") === "1";
    } catch (e) {
      return false;
    }
  });
  const [refreshKey, setRefreshKey] = useState(0);

  const selectedShipment = useMemo(
    () => shipments.find((shipment) => shipment.status !== "delivered") ?? shipments[0] ?? null,
    [shipments],
  );
  const staleSourceCount = sourceHealth.filter((source) => source.sourceStatus !== "healthy").length;
  const avgConfidence = shipments.length > 0
    ? shipments.reduce((sum, shipment) => sum + (shipment.etaConfidence?.score ?? 0), 0) / shipments.length
    : null;
  const highRiskCount = shipments.filter((shipment) => shipment.freshnessWarning || (shipment.etaConfidence?.score ?? 1) < 0.45).length;

  useEffect(() => {
    if (!selectedShipment) {
      setEtaRevisions([]);
      setPortCongestion(null);
      setCarrierPerformance([]);
      setVesselAnomaly(null);
      setDemurrageExposure(null);
      setComparison(null);
      return;
    }

    let cancelled = false;

    if (useDummyData) {
      // lazy-load dummy data to avoid bundling large fixtures
      void import("@/lib/dummyData").then((mod) => {
        if (cancelled) return;
        setEtaRevisions(mod.default.etaRevisions || []);
        setPortCongestion(mod.default.portCongestion || null);
        setCarrierPerformance(mod.default.carrierPerformance || []);
        setVesselAnomaly(mod.default.vesselAnomaly || null);
        setDemurrageExposure(mod.default.demurrageExposure || null);
        setComparison(mod.default.comparison || null);
      });
    } else {
      void Promise.allSettled([
        getEtaRevisions(selectedShipment.shipmentId),
        getPortCongestionSummary(selectedShipment.shipmentId),
        listCarrierPerformance(selectedShipment.serviceLane),
        getVesselAnomaly(selectedShipment.shipmentId),
        getDemurrageExposure(selectedShipment.shipmentId),
        compareShipments(),
      ]).then(([revisions, congestion, carriers, anomaly, exposure, shipmentComparison]) => {
        if (cancelled) return;
        setEtaRevisions(revisions.status === "fulfilled" ? revisions.value : []);
        setPortCongestion(congestion.status === "fulfilled" ? congestion.value : null);
        setCarrierPerformance(carriers.status === "fulfilled" ? carriers.value : []);
        setVesselAnomaly(anomaly.status === "fulfilled" ? anomaly.value : null);
        setDemurrageExposure(exposure.status === "fulfilled" ? exposure.value : null);
        setComparison(shipmentComparison.status === "fulfilled" ? shipmentComparison.value : null);
      });
    }

    return () => {
      cancelled = true;
    };
  }, [selectedShipment, useDummyData, refreshKey]);

  return (
    <div className="flex-1 overflow-y-auto bg-white p-4 sm:p-8 scrollbar-thin">
      <div className="mx-auto max-w-6xl space-y-4 sm:space-y-6">
        <div className="rounded-[24px] bg-[linear-gradient(135deg,#07111f_0%,#17334f_100%)] p-6 text-white shadow-apple">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-white/70">
            <Activity className="h-4 w-4" strokeWidth={1.5} />
            Analytics
          </div>
          <div className="mt-2 flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-white/85">
              <input
                type="checkbox"
                checked={useDummyData}
                onChange={(e) => {
                  const v = e.target.checked;
                  setUseDummyData(v);
                  try {
                    localStorage.setItem("useDummyData", v ? "1" : "0");
                  } catch (err) {
                    // ignore
                  }
                }}
              />
              Use demo data
            </label>
            <button
              type="button"
              onClick={() => setRefreshKey((k) => k + 1)}
              className="ml-2 rounded bg-white/10 px-3 py-1 text-xs text-white/90"
            >
              Refresh
            </button>
          </div>
          <h2 className="mt-3 text-2xl font-semibold">Operational analytics that point to what needs action</h2>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-white/80">
            Live source freshness, ETA revisions, congestion pressure, carrier reliability, and anomaly signals in one place.
          </p>
        </div>

        {error && <div className="rounded-apple bg-apple-red/5 p-4 text-sm text-apple-red">{error}</div>}
        {loading && <div className="text-sm text-apple-secondary">Loading analytics from the backend...</div>}

        {!loading && !error && (
          <>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="apple-card p-5">
                <p className="text-[11px] uppercase tracking-[0.12em] text-apple-secondary">Active shipments</p>
                <p className="mt-3 text-3xl font-semibold text-apple-text">{shipments.length}</p>
                <p className="mt-2 text-xs text-apple-secondary">{highRiskCount} need attention</p>
              </div>
              <div className="apple-card p-5">
                <p className="text-[11px] uppercase tracking-[0.12em] text-apple-secondary">Avg ETA confidence</p>
                <p className="mt-3 text-3xl font-semibold text-apple-text">{avgConfidence != null ? avgConfidence.toFixed(2) : "N/A"}</p>
                <p className="mt-2 text-xs text-apple-secondary">{selectedShipment?.bookingReference ?? "No active shipment selected"}</p>
              </div>
              <div className="apple-card p-5">
                <p className="text-[11px] uppercase tracking-[0.12em] text-apple-secondary">Open demurrage risk</p>
                <p className="mt-3 text-3xl font-semibold text-[#e24b4a]">
                  {demurrageExposure ? `₦${Math.round(demurrageExposure.projectedCostNgn).toLocaleString()}` : "N/A"}
                </p>
                <p className="mt-2 text-xs text-apple-secondary">
                  {demurrageExposure ? `${demurrageExposure.riskLevel} risk` : "No exposure loaded"}
                </p>
              </div>
              <div className="apple-card p-5">
                <p className="text-[11px] uppercase tracking-[0.12em] text-apple-secondary">Stale sources</p>
                <p className="mt-3 text-3xl font-semibold text-apple-text">{staleSourceCount}</p>
                <p className="mt-2 text-xs text-apple-secondary">of {sourceHealth.length} monitored</p>
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="apple-card p-6">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-apple-text">Source health</h3>
                  <span className="apple-badge-amber">{staleSourceCount} degraded</span>
                </div>
                <div className="mt-4 space-y-3">
                  {sourceHealth.map((source) => (
                    <div key={source.source} className="rounded-[14px] bg-apple-surface p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <StatusIcon status={source.sourceStatus} />
                          <span className="text-sm font-medium capitalize text-apple-text">{source.source.replace(/_/g, " ")}</span>
                        </div>
                        <span className="text-[11px] text-apple-secondary">
                          {source.lastSuccessAt ? new Date(source.lastSuccessAt).toLocaleString() : "Never"}
                        </span>
                      </div>
                      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-apple-divider">
                        <div className={`h-full rounded-full ${barTone(source.sourceStatus)}`} style={{ width: `${sourceBarWidth(source)}%` }} />
                      </div>
                      {source.degradedReason && <p className="mt-2 text-xs text-apple-secondary">{source.degradedReason}</p>}
                    </div>
                  ))}
                </div>
                {onAsk && (
                  <button
                    type="button"
                    onClick={() => onAsk("Which data sources are stale and how does that affect my shipment answers?")}
                    className="apple-btn-secondary mt-4 w-full px-4 py-2 text-xs flex items-center gap-1"
                  >
                    <span role="img" aria-label="sparkles">✨</span> Why does this matter for my shipments?
                  </button>
                )}
              </div>

              <div className="apple-card p-6">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-apple-text">ETA revision history</h3>
                  <span className="apple-badge-blue">{selectedShipment?.bookingReference ?? "No shipment"}</span>
                </div>
                <div className="mt-4 space-y-3">
                  {etaRevisions.length === 0 ? (
                    <p className="text-sm text-apple-secondary">No ETA revisions available yet.</p>
                  ) : (
                    etaRevisions.map((revision) => {
                      const deltaDays = revision.deltaHours != null ? (revision.deltaHours / 24) : null;
                      const width = Math.min(100, Math.max(20, Math.round(Math.abs(deltaDays ?? 0) * 20) + 24));
                      const tone = (deltaDays ?? 0) > 1 ? "bg-[#e24b4a]" : (deltaDays ?? 0) > 0 ? "bg-[#ba7517]" : "bg-[#639922]";
                      return (
                        <div key={`${revision.revisionAt}-${revision.source}`} className="rounded-[14px] bg-apple-surface p-3">
                          <div className="flex items-center justify-between gap-3 text-xs text-apple-secondary">
                            <span>{formatShortDate(revision.revisionAt)}</span>
                            <span>{deltaDays != null ? `${deltaDays >= 0 ? "+" : ""}${deltaDays.toFixed(1)}d` : "n/a"}</span>
                          </div>
                          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-apple-divider">
                            <div className={`h-full rounded-full ${tone}`} style={{ width: `${width}%` }} />
                          </div>
                          <div className="mt-2 flex items-center justify-between gap-3 text-sm">
                            <span className="text-apple-text">{formatShortDate(revision.previousEta)}</span>
                            <span className="text-apple-secondary">→</span>
                            <span className="text-apple-text">{formatShortDate(revision.newEta)}</span>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
                {onAsk && selectedShipment && (
                  <button
                    type="button"
                    onClick={() => onAsk(`Why has the ETA for ${selectedShipment.bookingReference} slipped recently?`)}
                    className="apple-btn-secondary mt-4 w-full px-4 py-2 text-xs flex items-center gap-1"
                  >
                    <span role="img" aria-label="sparkles">✨</span> Why did ETA slip?
                  </button>
                )}
              </div>
            </div>

            <div className="apple-card p-6">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-apple-text">Port congestion</h3>
                <span className="apple-badge-amber">{portCongestion?.portLocode ?? "No port selected"}</span>
              </div>
              {portCongestion ? (
                <>
                  <div className="mt-4 grid gap-4 md:grid-cols-[200px,1fr,180px]">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.12em] text-apple-secondary">Current wait</p>
                      <p className="mt-2 text-3xl font-semibold text-[#e24b4a]">{portCongestion.currentWaitDays.toFixed(1)}d</p>
                      <p className="mt-2 text-xs text-apple-secondary">
                        p75: {portCongestion.p75WaitDays?.toFixed(1) ?? "n/a"} · p90: {portCongestion.p90WaitDays?.toFixed(1) ?? "n/a"}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.12em] text-apple-secondary">Recent readings</p>
                      <div className="mt-3 flex h-24 items-end gap-2">
                        {portCongestion.recentReadings.map((reading) => {
                          const maxDelay = Math.max(...portCongestion.recentReadings.map((item) => item.delayDays), 1);
                          const height = Math.max(18, Math.round((reading.delayDays / maxDelay) * 72));
                          return (
                            <div key={reading.observedAt} className="flex flex-1 flex-col items-center gap-2">
                              <div className="w-full rounded-t-[6px] bg-[#b5d4f4]" style={{ height }} />
                              <span className="text-[10px] text-apple-secondary">{formatShortDate(reading.observedAt)}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                    <div className="rounded-[16px] bg-apple-surface p-4">
                      <p className="text-[11px] uppercase tracking-[0.12em] text-apple-secondary">Vs seasonal</p>
                      <p className="mt-2 text-2xl font-semibold text-[#e24b4a]">
                        {portCongestion.aboveSeasonalDays != null ? `${portCongestion.aboveSeasonalDays >= 0 ? "+" : ""}${portCongestion.aboveSeasonalDays.toFixed(1)}d` : "n/a"}
                      </p>
                      <p className="mt-2 text-xs text-apple-secondary">Median {portCongestion.seasonalMedianDays?.toFixed(1) ?? "n/a"} days</p>
                    </div>
                  </div>
                  {onAsk && selectedShipment && (
                    <button
                      type="button"
                      onClick={() => onAsk(`How will current congestion at ${portCongestion.portLocode} affect ${selectedShipment.bookingReference}?`)}
                      className="apple-btn-secondary mt-4 w-full px-4 py-2 text-xs flex items-center gap-1"
                    >
                      <span role="img" aria-label="sparkles">✨</span> How does this affect my clearance?
                    </button>
                  )}
                </>
              ) : (
                <p className="mt-4 text-sm text-apple-secondary">No congestion data available for the selected shipment.</p>
              )}
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="apple-card p-6">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-apple-text">Carrier performance</h3>
                  <span className="apple-badge-blue">last latest snapshot</span>
                </div>
                {carrierPerformance.length === 0 ? (
                  <p className="mt-4 text-sm text-apple-secondary">No carrier performance metrics available.</p>
                ) : (
                  <div className="mt-4 overflow-hidden rounded-[16px] border border-apple-divider bg-apple-surface/70">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-apple-divider text-apple-secondary">
                          <th className="px-4 py-3">Carrier</th>
                          <th className="px-4 py-3">On-time</th>
                          <th className="px-4 py-3">Avg delay</th>
                          <th className="px-4 py-3">Samples</th>
                        </tr>
                      </thead>
                      <tbody>
                        {carrierPerformance.map((item) => (
                          <tr key={`${item.carrier}-${item.yearMonth}`} className="border-b border-apple-divider last:border-b-0">
                            <td className="px-4 py-3 font-medium text-apple-text">{item.carrier}</td>
                            <td className="px-4 py-3 text-apple-secondary">{item.onTimeRate != null ? `${Math.round(item.onTimeRate * 100)}%` : "n/a"}</td>
                            <td className="px-4 py-3 text-apple-secondary">{item.medianDelayDays != null ? `+${item.medianDelayDays.toFixed(1)}d` : "n/a"}</td>
                            <td className="px-4 py-3 text-apple-secondary">{item.sampleCount}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {onAsk && (
                  <button
                    type="button"
                    onClick={() => onAsk("Which carrier has the best reliability record for Lagos routes?")}
                    className="apple-btn-secondary mt-4 w-full px-4 py-2 text-xs flex items-center gap-1"
                  >
                    <span role="img" aria-label="sparkles">✨</span> Which carrier should I trust most?
                  </button>
                )}
              </div>

              <div className="apple-card p-6">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-apple-text">Vessel anomalies</h3>
                  <span className={vesselAnomaly?.severity === "high" ? "apple-badge-red" : vesselAnomaly?.severity === "medium" ? "apple-badge-amber" : "apple-badge-green"}>
                    {vesselAnomaly?.severity ?? "none"}
                  </span>
                </div>
                {vesselAnomaly ? (
                  <div className="mt-4 space-y-3">
                    <div className="rounded-[14px] bg-apple-surface p-4">
                      <p className="text-sm font-medium text-apple-text">{vesselAnomaly.summary}</p>
                      {vesselAnomaly.indicators.length > 0 && (
                        <ul className="mt-3 space-y-2 text-sm text-apple-secondary">
                          {vesselAnomaly.indicators.map((indicator) => (
                            <li key={indicator} className="flex items-start gap-2">
                              <span className="mt-1 h-2 w-2 rounded-full bg-[#ba7517]" />
                              <span>{indicator}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                      {vesselAnomaly.recommendedAction && (
                        <div className="mt-4 rounded-[14px] border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                          <div className="flex items-center gap-2">
                            <ShieldAlert className="h-3.5 w-3.5" strokeWidth={1.5} />
                            Recommended action
                          </div>
                          <p className="mt-2">{vesselAnomaly.recommendedAction}</p>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <p className="mt-4 text-sm text-apple-secondary">No anomaly data available yet.</p>
                )}
                {onAsk && selectedShipment && (
                  <button
                    type="button"
                    onClick={() => onAsk(`Is there anything operationally unusual about ${selectedShipment.bookingReference} right now?`)}
                    className="apple-btn-secondary mt-4 w-full px-4 py-2 text-xs flex items-center gap-1"
                  >
                    <span role="img" aria-label="sparkles">✨</span> Should I be worried?
                  </button>
                )}
              </div>
            </div>

            {comparison && (
              <div className="apple-card p-6">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-apple-text">Shipment attention ranking</h3>
                  <span className="apple-badge-blue">cross-shipment</span>
                </div>
                <div className="mt-4 overflow-hidden rounded-[16px] border border-apple-divider bg-apple-surface/70">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-apple-divider text-apple-secondary">
                        <th className="px-4 py-3">Shipment</th>
                        <th className="px-4 py-3">Carrier</th>
                        <th className="px-4 py-3">Risk</th>
                        <th className="px-4 py-3">Freshness</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comparison.shipments.slice(0, 5).map((item) => (
                        <tr key={item.shipmentId} className="border-b border-apple-divider last:border-b-0">
                          <td className="px-4 py-3 font-medium text-apple-text">{item.bookingReference}</td>
                          <td className="px-4 py-3 text-apple-secondary">{item.carrier}</td>
                          <td className="px-4 py-3 text-apple-secondary">{item.riskScore.toFixed(1)}</td>
                          <td className="px-4 py-3 text-apple-secondary">{item.freshness}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
