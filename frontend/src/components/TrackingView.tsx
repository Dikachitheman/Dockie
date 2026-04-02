import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Search, ChevronDown, Anchor, Calendar, Package, MapPin, Activity, ShieldCheck, FileSearch, ShipWheel } from "lucide-react";
import { getShipmentBundle } from "@/lib/api";
import { type Shipment, formatStatus, getDaysRemaining, getProgressPercent } from "@/lib/shipment-ui";
import ShipmentMap from "./ShipmentMap";

interface TrackingViewProps {
  shipment: Shipment;
  shipments?: Shipment[];
  onSelectShipment?: (shipmentId: string) => void;
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

function StatusBadge({ status }: { status: Shipment["status"] }) {
  const classMap: Record<Shipment["status"], string> = {
    in_transit: "apple-badge-blue",
    open: "apple-badge-blue",
    booked: "apple-badge-grey",
    assigned: "apple-badge-amber",
    delivered: "apple-badge-green",
    delayed: "apple-badge-red",
  };

  return (
    <span className={classMap[status]}>
      {(status === "in_transit" || status === "open") && (
        <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse-dot rounded-full bg-apple-blue" />
      )}
      {formatStatus(status)}
    </span>
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


function ShipmentSelectorCard({
  shipment,
  selected,
}: {
  shipment: Shipment;
  selected: boolean;
}) {
  const vessel = shipment.candidateVessels[0];
  const isActiveTransit = shipment.status === "in_transit" || shipment.status === "open";
  const hasTimeline = Boolean(shipment.declaredDepartureDate && shipment.declaredEtaDate);
  const progress = getProgressPercent(shipment.declaredDepartureDate, shipment.declaredEtaDate);
  const days = getDaysRemaining(shipment.declaredEtaDate);

  return (
    <div
      className={`rounded-[18px] border p-4 transition-all ${
        selected
          ? "border-apple-blue/30 bg-[#f4f8ff] shadow-[0_10px_28px_rgba(0,113,227,0.14)]"
          : "border-transparent bg-white hover:border-[#e3e8ef] hover:bg-[#fafbfc]"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-apple-secondary">#{shipment.bookingReference}</p>
          <p className="mt-1 text-sm font-semibold text-apple-text">{vessel?.name ?? "Vessel pending"}</p>
        </div>
        <StatusBadge status={shipment.status} />
      </div>

      <div className="mt-3 flex items-center justify-between text-xs text-apple-secondary">
        <span>{shipment.loadPort ?? "Origin TBD"}</span>
        <span className="text-apple-secondary/40">to</span>
        <span>{shipment.dischargePort ?? "Destination TBD"}</span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-[14px] bg-[#f5f5f7] px-3 py-2">
          <p className="text-apple-secondary">Carrier</p>
          <p className="mt-1 font-medium text-apple-text">{shipment.carrier.toUpperCase()}</p>
        </div>
        <div className="rounded-[14px] bg-[#f5f5f7] px-3 py-2">
          <p className="text-apple-secondary">Position</p>
          <p className="mt-1 font-medium text-apple-text">{shipment.currentPosition ? "Live" : "Pending"}</p>
        </div>
      </div>

      {isActiveTransit && hasTimeline && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-[11px] text-apple-secondary">
            <span>{shipment.declaredDepartureDate ? new Date(shipment.declaredDepartureDate).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "TBD"}</span>
            <span className="font-medium text-apple-blue">{days}d left</span>
            <span>{shipment.declaredEtaDate ? new Date(shipment.declaredEtaDate).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "TBD"}</span>
          </div>
          <div className="mt-2 h-1.5 rounded-full bg-apple-divider">
            <div className="h-full rounded-full bg-apple-blue" style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}
    </div>
  );
}

export default function TrackingView({ shipment, shipments = [], onSelectShipment }: TrackingViewProps) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "delivered">("all");
  const [mapShipmentCache, setMapShipmentCache] = useState<Record<string, Shipment>>({
    [shipment.shipmentId]: shipment,
  });

  const allShipments = useMemo(() => {
    if (shipments.length === 0) return [shipment];
    const merged = new Map(shipments.map((item) => [item.shipmentId, item]));
    merged.set(shipment.shipmentId, shipment);
    return [...merged.values()];
  }, [shipment, shipments]);

  useEffect(() => {
    setMapShipmentCache((current) => ({
      ...current,
      [shipment.shipmentId]: shipment,
    }));
  }, [shipment]);

  useEffect(() => {
    const missingShipments = allShipments.filter((item) => !mapShipmentCache[item.shipmentId]);
    if (missingShipments.length === 0) {
      return;
    }

    let cancelled = false;

    void Promise.all(
      missingShipments.map(async (item) => {
        try {
          return await getShipmentBundle(item.shipmentId);
        } catch {
          return item;
        }
      }),
    ).then((loaded) => {
      if (cancelled) return;
      setMapShipmentCache((current) => {
        const next = { ...current };
        for (const loadedShipment of loaded) {
          next[loadedShipment.shipmentId] = loadedShipment;
        }
        return next;
      });
    });

    return () => {
      cancelled = true;
    };
  }, [allShipments, mapShipmentCache]);

  const mapShipments = useMemo(
    () => allShipments.map((item) => mapShipmentCache[item.shipmentId] ?? item),
    [allShipments, mapShipmentCache],
  );

  const filteredShipments = useMemo(() => {
    return allShipments.filter((item) => {
      const query = search.trim().toLowerCase();
      const matchesSearch = query.length === 0
        || item.bookingReference.toLowerCase().includes(query)
        || item.carrier.toLowerCase().includes(query)
        || item.candidateVessels.some((vessel) => vessel.name.toLowerCase().includes(query))
        || (item.loadPort ?? "").toLowerCase().includes(query)
        || (item.dischargePort ?? "").toLowerCase().includes(query);

      const isActive = item.status === "in_transit" || item.status === "open" || item.status === "assigned" || item.status === "booked";
      const matchesStatus = statusFilter === "all"
        ? true
        : statusFilter === "active"
          ? isActive
          : item.status === "delivered";

      return matchesSearch && matchesStatus;
    });
  }, [allShipments, search, statusFilter]);

  const vessel = shipment.candidateVessels[0];
  const position = shipment.currentPosition;
  const progress = getProgressPercent(shipment.declaredDepartureDate, shipment.declaredEtaDate);
  const days = getDaysRemaining(shipment.declaredEtaDate);
  const isActiveTransit = shipment.status === "in_transit" || shipment.status === "open";
  const hasTimeline = Boolean(shipment.declaredDepartureDate && shipment.declaredEtaDate);

  return (
    <div className="flex h-full min-h-0 min-w-0 bg-[#f6f7fb]">
      <div className="flex w-full min-w-0 flex-col lg:flex-row">

        {/* Left: shipment list */}
        <div className="flex min-h-0 w-full shrink-0 flex-col border-r border-black/5 bg-[#f8f9fb] lg:w-[300px] xl:w-[320px]">
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-4 py-5">
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-apple-secondary" strokeWidth={1.5} />
                <input
                  type="text"
                  placeholder="Search booking, vessel or port"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  className="apple-input h-10 w-full pl-10 pr-3 text-sm text-apple-text placeholder:text-apple-secondary"
                />
              </div>
              <div className="relative">
                <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-apple-secondary" strokeWidth={1.5} />
                <select
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value as "all" | "active" | "delivered")}
                  className="apple-btn-secondary h-10 appearance-none px-3 pr-7 text-xs font-medium text-apple-text"
                >
                  <option value="all">All</option>
                  <option value="active">Active</option>
                  <option value="delivered">Delivered</option>
                </select>
              </div>
            </div>

            <div className="mt-4 min-h-0 flex-1 overflow-y-auto pr-1 scrollbar-thin">
              <div className="mb-3 flex items-center justify-between">
                <p className="text-sm font-semibold text-apple-text">Shipments</p>
                <p className="text-xs text-apple-secondary">{filteredShipments.length} visible</p>
              </div>

              {filteredShipments.length === 0 ? (
                <div className="apple-card px-4 py-8 text-center">
                  <p className="text-sm font-medium text-apple-text">No shipments match</p>
                  <p className="mt-1 text-xs leading-relaxed text-apple-secondary">Try another search or filter.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredShipments.map((item) => (
                    <button
                      key={item.shipmentId}
                      type="button"
                      onClick={() => onSelectShipment?.(item.shipmentId)}
                      className="block w-full text-left"
                    >
                      <ShipmentSelectorCard shipment={item} selected={item.shipmentId === shipment.shipmentId} />
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Middle: selected shipment details */}
        <div className="flex min-h-0 w-full shrink-0 flex-col border-r border-black/5 bg-white lg:w-[340px] xl:w-[380px]">
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-5 py-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-apple-text">#{shipment.bookingReference}</p>
                <p className="mt-0.5 text-xs text-apple-secondary">{shipment.loadPort ?? "Origin TBD"} → {shipment.dischargePort ?? "Destination TBD"}</p>
              </div>
              <StatusBadge status={shipment.status} />
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto pr-1 scrollbar-thin">
              <div className="space-y-3">
                <div className="apple-card p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-apple-text">{vessel?.name ?? "Vessel pending assignment"}</p>
                      <p className="mt-1 text-xs text-apple-secondary">
                        {shipment.loadPort ?? "Origin TBD"} to {shipment.dischargePort ?? "Destination TBD"}
                      </p>
                    </div>
                    <div className="rounded-[16px] bg-[#f5f8ff] p-3 text-apple-blue">
                      <ShipWheel className="h-5 w-5" strokeWidth={1.8} />
                    </div>
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
                      <p className="mt-2 text-right text-xs font-medium text-apple-blue">{progress}% • {days} days left</p>
                    </div>
                  )}

                  {shipment.freshnessWarning && (
                    <p className="mt-4 text-xs leading-relaxed text-apple-red">{shipment.freshnessWarning}</p>
                  )}
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
                    <p className="text-sm leading-relaxed text-apple-secondary">No vessel has been linked to this shipment yet.</p>
                  </InfoSection>
                )}

                {position ? (
                  <InfoSection icon={MapPin} title="Current Position">
                    <Row
                      label="Coordinates"
                      value={`${formatCoordinate(position.latitude, "N", "S")}, ${formatCoordinate(position.longitude, "E", "W")}`}
                      mono
                    />
                    <Row label="Speed" value={position.speedKnots != null ? `${position.speedKnots} kn` : "N/A"} />
                    <Row label="Course" value={position.courseDegrees != null ? `${position.courseDegrees}°` : "N/A"} />
                    <Row label="Destination" value={position.destination ?? "Unknown"} />
                    <Row label="Nav Status" value={(position.navStatus ?? "unknown").replace(/_/g, " ")} />
                    <Row label="Source" value={position.source} />
                    <Row label="Updated" value={formatDate(position.observedAt, true)} />
                  </InfoSection>
                ) : (
                  <InfoSection icon={MapPin} title="Current Position">
                    <p className="text-sm leading-relaxed text-apple-secondary">No live position is available right now.</p>
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
                      <div key={`${evidence.source}-${evidence.capturedAt}`} className="rounded-[14px] bg-apple-surface p-3">
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
                  <div className="apple-card p-5">
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
          </div>
        </div>

        {/* Right: map */}
        <div className="flex min-h-[360px] min-w-0 flex-1 flex-col bg-white p-4 lg:min-h-0 lg:p-6">
          <div className="apple-card flex min-h-0 flex-1 flex-col overflow-hidden p-3 lg:p-4">
            <div className="mb-3 flex items-center justify-between gap-3 px-1">
              <div>
                <p className="text-sm font-semibold text-apple-text">Live map</p>
                <p className="mt-1 text-xs text-apple-secondary">
                  All shipment markers stay visible while the selected shipment route is highlighted.
                </p>
              </div>
              <StatusBadge status={shipment.status} />
            </div>

            <ShipmentMap shipment={shipment} shipments={mapShipments} selectedShipmentId={shipment.shipmentId} />
          </div>
        </div>
      </div>
    </div>
  );
}
