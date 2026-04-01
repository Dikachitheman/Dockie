import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ShipmentList from "@/components/ShipmentList";
import type { Shipment } from "@/lib/shipment-ui";

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
    candidateVessels: [
      { vesselId: "v-1", name: "GREAT ABIDJAN", imo: "9935040", mmsi: "357123000", isPrimary: true },
    ],
    evidence: [],
    currentPosition: null,
    historyPoints: [],
    events: [],
    ...overrides,
  };
}

describe("ShipmentList", () => {
  it("filters shipments by vessel search", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();

    render(
      <ShipmentList
        shipments={[
          makeShipment({ shipmentId: "ship-001", bookingReference: "SAL-LAG-24001" }),
          makeShipment({
            shipmentId: "ship-002",
            bookingReference: "GRI-LAG-24007",
            carrier: "grimaldi",
            candidateVessels: [{ vesselId: "v-2", name: "GREAT COTONOU", imo: "9922345", mmsi: "311000111", isPrimary: true }],
          }),
        ]}
        selectedId="ship-001"
        onSelect={onSelect}
      />,
    );

    await user.type(screen.getByPlaceholderText("Search shipments..."), "cotonou");

    expect(screen.getByText("GREAT COTONOU")).toBeInTheDocument();
    expect(screen.queryByText("GREAT ABIDJAN")).not.toBeInTheDocument();
  });

  it("filters shipments by status", async () => {
    const user = userEvent.setup();

    render(
      <ShipmentList
        shipments={[
          makeShipment({ shipmentId: "ship-001", bookingReference: "SAL-LAG-24001", status: "open" }),
          makeShipment({ shipmentId: "ship-002", bookingReference: "DEL-LAG-24009", status: "delivered" }),
        ]}
        selectedId="ship-001"
        onSelect={() => {}}
      />,
    );

    await user.selectOptions(screen.getByDisplayValue("All"), "delivered");

    expect(screen.getByText("#DEL-LAG-24009")).toBeInTheDocument();
    expect(screen.queryByText("#SAL-LAG-24001")).not.toBeInTheDocument();
  });

  it("shows a helpful empty state when filters remove all shipments", async () => {
    const user = userEvent.setup();

    render(
      <ShipmentList
        shipments={[makeShipment({ shipmentId: "ship-001", bookingReference: "SAL-LAG-24001" })]}
        selectedId="ship-001"
        onSelect={() => {}}
      />,
    );

    await user.type(screen.getByPlaceholderText("Search shipments..."), "no-match");

    expect(screen.getByText("No shipments match this filter")).toBeInTheDocument();
  });

  it("shows a backend-ingest empty state when there are no shipments", () => {
    render(<ShipmentList shipments={[]} selectedId={null} onSelect={() => {}} />);

    expect(screen.getByText("No shipments available yet")).toBeInTheDocument();
  });
});
