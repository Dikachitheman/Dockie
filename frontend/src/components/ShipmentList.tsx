import { formatStatus, getDaysRemaining, getProgressPercent, type Shipment } from "@/lib/shipment-ui";
import { Search, ChevronDown } from "lucide-react";
import { useState } from "react";

interface ShipmentListProps {
  shipments: Shipment[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function StatusBadge({ status }: { status: string }) {
  const classMap: Record<string, string> = {
    in_transit: "apple-badge-blue",
    open: "apple-badge-blue",
    booked: "apple-badge-grey",
    assigned: "apple-badge-amber",
    delivered: "apple-badge-green",
    delayed: "apple-badge-red",
  };
  return (
    <span className={classMap[status] ?? "apple-badge-grey"}>
      {(status === "in_transit" || status === "open") && (
        <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-apple-blue animate-pulse-dot" />
      )}
      {formatStatus(status)}
    </span>
  );
}

export default function ShipmentList({ shipments, selectedId, onSelect }: ShipmentListProps) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "delivered">("all");

  const filtered = shipments.filter((shipment) => {
    const matchesSearch =
      shipment.bookingReference.toLowerCase().includes(search.toLowerCase()) ||
      shipment.candidateVessels.some((vessel) => vessel.name.toLowerCase().includes(search.toLowerCase())) ||
      (shipment.dischargePort ?? "").toLowerCase().includes(search.toLowerCase()) ||
      shipment.carrier.toLowerCase().includes(search.toLowerCase());

    const isActive = shipment.status === "in_transit" || shipment.status === "open" || shipment.status === "assigned" || shipment.status === "booked";
    const matchesStatus =
      statusFilter === "all"
        ? true
        : statusFilter === "active"
          ? isActive
          : shipment.status === "delivered";

    return matchesSearch && matchesStatus;
  });

  return (
    <div className="flex h-full w-[380px] flex-col bg-apple-surface">
      <div className="px-6 pb-4 pt-6">
        <h2 className="text-xl font-semibold text-apple-text">Shipments</h2>
        <div className="mt-4 flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-apple-secondary" strokeWidth={1.5} />
            <input
              type="text"
              placeholder="Search shipments..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="apple-input h-10 w-full pl-10 pr-3 text-sm text-apple-text placeholder:text-apple-secondary"
            />
          </div>
          <div className="relative">
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3 w-3 -translate-y-1/2 text-apple-secondary" strokeWidth={1.5} />
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as "all" | "active" | "delivered")}
              className="apple-btn-secondary h-10 appearance-none px-4 pr-8 text-xs font-medium text-apple-text"
            >
              <option value="all">All</option>
              <option value="active">Active</option>
              <option value="delivered">Delivered</option>
            </select>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-3 scrollbar-thin">
        {shipments.length === 0 ? (
          <div className="flex h-full items-center justify-center px-6 text-center">
            <div>
              <p className="text-sm font-medium text-apple-text">No shipments available yet</p>
              <p className="mt-2 text-xs leading-relaxed text-apple-secondary">
                Run ingest or refresh in the backend to load tracked shipments into the app.
              </p>
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex h-full items-center justify-center px-6 text-center">
            <div>
              <p className="text-sm font-medium text-apple-text">No shipments match this filter</p>
              <p className="mt-2 text-xs leading-relaxed text-apple-secondary">
                Try a different search term or switch the status filter back to All.
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((shipment) => {
            const vessel = shipment.candidateVessels[0];
            const days = getDaysRemaining(shipment.declaredEtaDate);
            const progress = getProgressPercent(shipment.declaredDepartureDate, shipment.declaredEtaDate);
            const isSelected = selectedId === shipment.shipmentId;
            const isActiveTransit = shipment.status === "in_transit" || shipment.status === "open";
            const hasTimeline = Boolean(shipment.declaredDepartureDate && shipment.declaredEtaDate);

            return (
              <button
                key={shipment.shipmentId}
                onClick={() => onSelect(shipment.shipmentId)}
                className={`w-full rounded-apple p-5 text-left transition-all duration-150 active:scale-[0.98] ${isSelected ? "apple-card" : "hover:bg-apple-hover"}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <span className="text-xs font-medium text-apple-secondary">#{shipment.bookingReference}</span>
                  <StatusBadge status={shipment.status} />
                </div>

                {vessel && <p className="mt-1.5 text-sm font-semibold text-apple-text">{vessel.name}</p>}

                <div className="mt-3 flex items-center justify-between text-xs text-apple-secondary">
                  <span>{shipment.loadPort ?? "TBD"}</span>
                  <span className="text-apple-secondary/40">?</span>
                  <span>{shipment.dischargePort ?? "TBD"}</span>
                </div>

                {isActiveTransit && hasTimeline && (
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-xs text-apple-secondary">
                      <span>{shipment.declaredDepartureDate ? new Date(shipment.declaredDepartureDate).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "TBD"}</span>
                      <span className="font-medium text-apple-blue">{days}d left</span>
                      <span>{shipment.declaredEtaDate ? new Date(shipment.declaredEtaDate).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "TBD"}</span>
                    </div>
                    <div className="mt-2 h-1 rounded-full bg-apple-divider">
                      <div className="h-full rounded-full bg-apple-blue transition-all" style={{ width: `${progress}%` }} />
                    </div>
                  </div>
                )}
              </button>
            );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
