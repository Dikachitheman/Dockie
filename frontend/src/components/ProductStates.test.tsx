import { render, screen } from "@testing-library/react";
import SourceHealthDashboard from "@/components/SourceHealthDashboard";
import TrackingView from "@/components/TrackingView";
import type { Shipment } from "@/lib/shipment-ui";
import { getShipmentBundle } from "@/lib/api";

const shipmentMapSpy = vi.fn();
vi.mock("@/components/ShipmentMap", () => ({
  default: (props: unknown) => {
    shipmentMapSpy(props);
    return <div data-testid="shipment-map">map</div>;
  },
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getShipmentBundle: vi.fn(),
  };
});

function makeShipment(overrides: Partial<Shipment>): Shipment {
  return {
    shipmentId: "ship-001",
    bookingReference: "SAL-LAG-24001",
    carrier: "sallaum",
    serviceLane: "US -> West Africa",
    loadPort: "USBAL",
    dischargePort: "NGLOS",
    cargoType: "ro-ro vehicles",
    units: 42,
    declaredDepartureDate: "2026-03-18T00:00:00Z",
    declaredEtaDate: "2026-04-02T00:00:00Z",
    status: "open",
    candidateVessels: [],
    evidence: [],
    currentPosition: null,
    historyPoints: [],
    events: [],
    ...overrides,
  };
}

describe("frontend product states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows an empty source health state", () => {
    render(<SourceHealthDashboard sourceHealth={[]} shipments={[]} loading={false} error={null} />);

    expect(screen.getByText("Operational analytics that point to what needs action")).toBeInTheDocument();
    expect(screen.getByText("No congestion data available for the selected shipment.")).toBeInTheDocument();
  });

  it("shows degraded tracking fallbacks when vessel and position are missing", () => {
    render(<TrackingView shipment={makeShipment({})} />);

    expect(screen.getByText("No vessel has been linked to this shipment yet. Tracking can still use declared shipment context and later live overlays.")).toBeInTheDocument();
    expect(screen.getByText("No live position is available right now. The shipment may still be waiting for ingest, a vessel match, or a fresher upstream source.")).toBeInTheDocument();
  });

  it("passes multi-shipment overlay context into the shared map and keeps the selected shipment highlighted", async () => {
    const selected = makeShipment({ shipmentId: "ship-001", bookingReference: "SAL-LAG-24001" });
    const overlaySummary = makeShipment({ shipmentId: "ship-002", bookingReference: "GRI-LAG-24003" });
    const overlayDetail = makeShipment({
      shipmentId: "ship-002",
      bookingReference: "GRI-LAG-24003",
      historyPoints: [
        { observedAt: "2026-03-29T00:00:00Z", latitude: 5.1, longitude: 3.2, speedKnots: 8.1, courseDegrees: 90, source: "orbcomm" },
      ],
    });

    vi.mocked(getShipmentBundle).mockResolvedValue(overlayDetail);

    render(<TrackingView shipment={selected} shipments={[selected, overlaySummary]} />);

    expect(await screen.findByTestId("shipment-map")).toBeInTheDocument();
    expect(shipmentMapSpy).toHaveBeenCalled();

    const latestProps = shipmentMapSpy.mock.calls.at(-1)?.[0] as { selectedShipmentId?: string; shipments?: Shipment[] };
    expect(latestProps.selectedShipmentId).toBe("ship-001");
    expect(latestProps.shipments?.length).toBe(2);
    expect(latestProps.shipments?.some((item) => item.shipmentId === "ship-002" && item.historyPoints.length === 1)).toBe(true);
  });
});
