import { type ReactNode, useEffect, useMemo, useState } from "react";
import { getShipmentBundle, getShipmentPortProximity } from "@/lib/api";
import { type Shipment, type VesselPortProximity, formatStatus, getDaysRemaining, getProgressPercent } from "@/lib/shipment-ui";
import ShipmentMap from "./ShipmentMap";
import { Anchor, Calendar, Package, MapPin, Activity, ShieldCheck, FileSearch, Navigation } from "lucide-react";

interface TrackingViewProps {
  shipment: Shipment;
  shipments?: Shipment[];
}

function InfoSection({ icon: Icon, title, children }: { icon: any; title: string; children: ReactNode }) {
  return (
    <div className="apple-card p-6">
      <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
        <Icon className="h-[18px] w-[18px] text-apple-blue" strokeWidth={1.5} />
        {title}
      </div>
      <div className="mt-4 space-y-3 text-sm">{children}</div>
    </div>
  );
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-apple-secondary">{label}</span>
      <span className={`text-right font-medium text-apple-text ${mono ? "font-mono text-xs" : ""}`}>{value}</span>
    </div>
  );
}

function formatDate(value: string | null | undefined, withTime = false) {
  if (!value) return "N/A";
  return new Date(value).toLocaleString("en-US", withTime ? undefined : { month: "long", day: "numeric", year: "numeric" });
}

function formatCoordinate(value: number | null | undefined, positiveLabel: string, negativeLabel: string) {
  if (value == null) return "N/A";
  const direction = value >= 0 ? positiveLabel : negativeLabel;
  return `${Math.abs(value).toFixed(4)}°${direction}`;
}

export default function TrackingView({ shipment, shipments = [] }: TrackingViewProps) {
  const vessel = shipment.candidateVessels[0];
  const position = shipment.currentPosition;
  const progress = getProgressPercent(shipment.declaredDepartureDate, shipment.declaredEtaDate);
  const days = getDaysRemaining(shipment.declaredEtaDate);
  const isActiveTransit = shipment.status === "in_transit" || shipment.status === "open";
  const hasTimeline = Boolean(shipment.declaredDepartureDate && shipment.declaredEtaDate);
  const [proximities, setProximities] = useState<VesselPortProximity[]>([]);
  const [mapShipmentCache, setMapShipmentCache] = useState<Record<string, Shipment>>({
    [shipment.shipmentId]: shipment,
  });

  useEffect(() => {
    setMapShipmentCache((current) => ({
      ...current,
      [shipment.shipmentId]: shipment,
    }));
  }, [shipment]);

  useEffect(() => {
    let cancelled = false;
    getShipmentPortProximity(shipment.shipmentId)
      .then((result) => {
        if (!cancelled) setProximities(result.vesselProximities);
      })
      .catch(() => {
        if (!cancelled) setProximities([]);
      });
    return () => { cancelled = true; };
  }, [shipment.shipmentId]);

  useEffect(() => {
    const candidates = shipments.length > 0 ? shipments : [shipment];
    const missingIds = candidates
      .map((item) => item.shipmentId)
      .filter((shipmentId) => !mapShipmentCache[shipmentId]);

    if (missingIds.length === 0) {
      return;
    }

    let cancelled = false;

    void Promise.all(
      missingIds.map(async (shipmentId) => {
        try {
          return await getShipmentBundle(shipmentId);
        } catch {
          return candidates.find((item) => item.shipmentId === shipmentId) ?? null;
        }
      }),
    ).then((loaded) => {
      if (!cancelled) {
        setMapShipmentCache((current) => {
          const next = { ...current };
          for (const loadedShipment of loaded) {
            if (loadedShipment) {
              next[loadedShipment.shipmentId] = loadedShipment;
            }
          }
          return next;
        });
      }
    });

    return () => {
      cancelled = true;
    };
  }, [shipment, shipments, mapShipmentCache]);

  const mapShipments = useMemo(() => {
    const candidates = shipments.length > 0 ? shipments : [shipment];
    return candidates.map((item) => mapShipmentCache[item.shipmentId] ?? item);
  }, [shipment, shipments, mapShipmentCache]);

  return (
    <div className="flex h-full">
      <div className="w-[420px] overflow-y-auto bg-white p-6 scrollbar-thin">
        <h2 className="text-xl font-semibold text-apple-text">Shipment Details</h2>
        <p className="mt-1 text-xs font-medium text-apple-secondary">#{shipment.bookingReference}</p>

        <div className="mt-6 space-y-4">
          <div className="apple-card p-6">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-semibold text-apple-text">Status</span>
              <span className="apple-badge-blue">{formatStatus(shipment.status)}</span>
            </div>
            {isActiveTransit && hasTimeline && (
              <div className="mt-4">
                <div className="flex justify-between text-xs text-apple-secondary">
                  <span>{shipment.loadPort ?? "Origin TBD"}</span>
                  <span>{shipment.dischargePort ?? "Destination TBD"}</span>
                </div>
                <div className="mt-2 h-1.5 rounded-full bg-apple-divider">
                  <div className="h-full rounded-full bg-apple-blue" style={{ width: `${progress}%` }} />
                </div>
                <p className="mt-1.5 text-right text-xs font-medium text-apple-blue">{progress}% • {days} days left</p>
              </div>
            )}
            {shipment.freshnessWarning && <p className="mt-4 text-xs leading-relaxed text-apple-red">{shipment.freshnessWarning}</p>}
          </div>

          {vessel ? (
            <InfoSection icon={Anchor} title="Vessel">
              <Row label="Name" value={vessel.name} />
              <Row label="IMO" value={vessel.imo ?? "N/A"} mono />
              <Row label="MMSI" value={vessel.mmsi ?? "N/A"} mono />
              <Row label="Carrier" value={shipment.carrier.toUpperCase()} />
            </InfoSection>
          ) : (
            <InfoSection icon={Anchor} title="Vessel">
              <p className="text-sm leading-relaxed text-apple-secondary">
                No vessel has been linked to this shipment yet. Tracking can still use declared shipment context and later live overlays.
              </p>
            </InfoSection>
          )}

          {position ? (
            <InfoSection icon={MapPin} title="Current Position">
              <Row label="Coordinates" value={`${formatCoordinate(position.latitude, "N", "S")}, ${formatCoordinate(position.longitude, "E", "W")}`} mono />
              <Row label="Speed" value={position.speedKnots != null ? `${position.speedKnots} kn` : "N/A"} />
              <Row label="Course" value={position.courseDegrees != null ? `${position.courseDegrees}°` : "N/A"} />
              <Row label="Destination" value={position.destination ?? "Unknown"} />
              <Row label="Nav Status" value={(position.navStatus ?? "unknown").replace(/_/g, " ")} />
              <Row label="Source" value={position.source} />
              <Row label="Updated" value={formatDate(position.observedAt, true)} />
            </InfoSection>
          ) : (
            <InfoSection icon={MapPin} title="Current Position">
              <p className="text-sm leading-relaxed text-apple-secondary">
                No live position is available right now. The shipment may still be waiting for ingest, a vessel match, or a fresher upstream source.
              </p>
            </InfoSection>
          )}

          {proximities.length > 0 && (
            <InfoSection icon={Navigation} title="Port Proximity">
              {proximities.map((vp) => (
                <div key={vp.mmsi} className="space-y-2">
                  {vp.vesselName && <p className="text-xs font-semibold text-apple-text">{vp.vesselName}</p>}
                  {vp.portProximity ? (
                    <div className="rounded-apple bg-apple-surface p-3 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-apple-text">{vp.portProximity.name}</span>
                        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${
                          vp.portProximity.proximityStatus === "at_port"
                            ? "bg-emerald-100 text-emerald-700"
                            : vp.portProximity.proximityStatus === "approaching"
                            ? "bg-amber-100 text-amber-700"
                            : "bg-blue-100 text-blue-700"
                        }`}>
                          {(vp.portProximity.proximityStatus ?? "near").replace(/_/g, " ").toUpperCase()}
                        </span>
                      </div>
                      <Row label="Port" value={`${vp.portProximity.locode ?? ""} — ${vp.portProximity.country ?? ""}`} />
                      <Row label="Distance" value={vp.portProximity.distanceNm != null ? `${vp.portProximity.distanceNm} nm` : "N/A"} />
                      <Row label="Geofence" value={vp.portProximity.geofenceRadiusNm != null ? `${vp.portProximity.geofenceRadiusNm} nm radius` : "N/A"} />
                    </div>
                  ) : vp.nearestPort ? (
                    <div className="space-y-1.5">
                      <Row label="Nearest Port" value={`${vp.nearestPort.name} (${vp.nearestPort.locode})`} />
                      <Row label="Distance" value={vp.nearestPort.distanceNm != null ? `${vp.nearestPort.distanceNm} nm` : "N/A"} />
                      <Row label="Country" value={vp.nearestPort.country} />
                    </div>
                  ) : (
                    <p className="text-xs text-apple-secondary">No nearby port detected.</p>
                  )}
                </div>
              ))}
            </InfoSection>
          )}

          {shipment.etaConfidence && (
            <InfoSection icon={ShieldCheck} title="ETA Confidence">
              <Row label="Score" value={shipment.etaConfidence.score.toFixed(2)} />
              <Row label="Freshness" value={shipment.etaConfidence.freshness} />
              <p className="text-xs leading-relaxed text-apple-secondary">{shipment.etaConfidence.explanation}</p>
            </InfoSection>
          )}

          <InfoSection icon={Package} title="Cargo">
            <Row label="Type" value={shipment.cargoType ?? "Not provided"} />
            <Row label="Units" value={shipment.units != null ? String(shipment.units) : "N/A"} />
            <Row label="Service" value={shipment.serviceLane ?? "N/A"} />
          </InfoSection>

          <InfoSection icon={Calendar} title="Schedule">
            <Row label="Departure" value={formatDate(shipment.declaredDepartureDate)} />
            <Row label="ETA" value={formatDate(shipment.declaredEtaDate)} />
          </InfoSection>

          {shipment.evidence.length > 0 && (
            <InfoSection icon={FileSearch} title="Evidence and Provenance">
              {shipment.evidence.map((evidence) => (
                <div key={`${evidence.source}-${evidence.capturedAt}`} className="rounded-apple bg-apple-surface p-3">
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className="font-semibold text-apple-text">{evidence.source}</span>
                    <span className="text-apple-secondary">{formatDate(evidence.capturedAt, true)}</span>
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-apple-secondary">{evidence.claim}</p>
                </div>
              ))}
            </InfoSection>
          )}

          {shipment.events.length > 0 && (
            <div className="apple-card p-6">
              <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
                <Activity className="h-[18px] w-[18px] text-apple-blue" strokeWidth={1.5} />
                Timeline
              </div>
              <div className="mt-4 space-y-4">
                {shipment.events.map((event, index) => (
                  <div key={`${event.eventType}-${event.eventAt}-${index}`} className="flex gap-3">
                    <div className="relative flex flex-col items-center">
                      <div className="h-2.5 w-2.5 rounded-full bg-apple-blue" />
                      {index < shipment.events.length - 1 && <div className="h-full w-px bg-apple-divider" />}
                    </div>
                    <div className="pb-1">
                      <p className="text-xs font-semibold capitalize text-apple-text">{event.eventType.replace(/_/g, " ")}</p>
                      <p className="mt-0.5 text-xs text-apple-secondary">{event.details ?? "No details available"}</p>
                      <p className="mt-0.5 text-[11px] text-apple-secondary/60">{formatDate(event.eventAt, true)}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-hidden bg-white">
        <ShipmentMap shipment={shipment} shipments={mapShipments} selectedShipmentId={shipment.shipmentId} />
      </div>
    </div>
  );
}
