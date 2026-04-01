import { test, expect } from "../playwright-fixture";

const shipments = [
  {
    id: "ship-001",
    booking_ref: "SAL-LAG-24001",
    carrier: "sallaum",
    service_lane: "US -> West Africa",
    load_port: "USBAL",
    discharge_port: "NGLOS",
    cargo_type: "ro-ro vehicles",
    units: 42,
    status: "open",
    declared_departure_date: "2026-03-18T00:00:00Z",
    declared_eta_date: "2026-04-02T00:00:00Z",
    candidate_vessels: [
      {
        vessel_id: "v-1",
        imo: "9935040",
        mmsi: "357123000",
        name: "GREAT ABIDJAN",
        is_primary: true,
      },
    ],
  },
  {
    id: "ship-002",
    booking_ref: "GRI-LAG-24007",
    carrier: "grimaldi",
    service_lane: "US -> West Africa",
    load_port: "USSAV",
    discharge_port: "NGAPP",
    cargo_type: "rolling equipment",
    units: 11,
    status: "delivered",
    declared_departure_date: "2026-03-16T00:00:00Z",
    declared_eta_date: "2026-03-31T00:00:00Z",
    candidate_vessels: [
      {
        vessel_id: "v-2",
        imo: "9922345",
        mmsi: "311000111",
        name: "GREAT COTONOU",
        is_primary: true,
      },
    ],
  },
];

const shipmentBundle = {
  id: "ship-001",
  booking_ref: "SAL-LAG-24001",
  carrier: "sallaum",
  service_lane: "US -> West Africa",
  load_port: "USBAL",
  discharge_port: "NGLOS",
  cargo_type: "ro-ro vehicles",
  units: 42,
  status: "open",
  declared_departure_date: "2026-03-18T00:00:00Z",
  declared_eta_date: "2026-04-02T00:00:00Z",
  candidate_vessels: [
    {
      vessel_id: "v-1",
      imo: "9935040",
      mmsi: "357123000",
      name: "GREAT ABIDJAN",
      is_primary: true,
    },
  ],
  evidence: [
    {
      source: "carrier_schedule",
      captured_at: "2026-03-18T08:12:00Z",
      claim: "Lagos discharge expected early April",
      url: null,
    },
  ],
};

const shipmentStatus = {
  shipment_id: "ship-001",
  booking_ref: "SAL-LAG-24001",
  carrier: "sallaum",
  status: "open",
  declared_eta: "2026-04-02T00:00:00Z",
  latest_position: {
    mmsi: "357123000",
    imo: "9935040",
    vessel_name: "GREAT ABIDJAN",
    latitude: 5.25,
    longitude: 3.85,
    sog_knots: 14.2,
    cog_degrees: 92.5,
    heading_degrees: 91,
    navigation_status: "under_way_using_engine",
    destination_text: "LAGOS",
    source: "aisstream",
    observed_at: "2026-03-20T12:00:00Z",
  },
  eta_confidence: {
    confidence: 0.82,
    freshness: "fresh",
    explanation: "Live position is recent and consistent with the planned arrival window.",
    declared_eta: "2026-04-02T00:00:00Z",
  },
  candidate_vessels: shipmentBundle.candidate_vessels,
  evidence_count: 1,
  freshness_warning: null,
};

const shipmentHistory = {
  shipment_id: "ship-001",
  vessel_mmsi: "357123000",
  vessel_name: "GREAT ABIDJAN",
  track: [
    {
      latitude: 4.1,
      longitude: -8.9,
      sog_knots: 15.1,
      cog_degrees: 88,
      observed_at: "2026-03-19T00:00:00Z",
      source: "historical_ais",
    },
    {
      latitude: 5.25,
      longitude: 3.85,
      sog_knots: 14.2,
      cog_degrees: 92.5,
      observed_at: "2026-03-20T12:00:00Z",
      source: "aisstream",
    },
  ],
  events: [
    {
      event_type: "lagos_expected_detected",
      event_at: "2026-03-20T12:00:00Z",
      details: "Destination text set to LAGOS",
      source: "aisstream",
    },
  ],
};

const sourceHealth = [
  {
    source: "aisstream",
    source_class: "public_api_terms",
    automation_safety: "moderate",
    business_safe_default: true,
    source_status: "healthy",
    last_success_at: "2026-03-22T18:34:07Z",
    stale_after_seconds: 3600,
    degraded_reason: null,
    updated_at: "2026-03-22T18:34:07Z",
  },
];

test.beforeEach(async ({ page }) => {
  await page.route("**/shipments/ship-001/status", async (route) => {
    await route.fulfill({ json: shipmentStatus });
  });

  await page.route("**/shipments/ship-001/history", async (route) => {
    await route.fulfill({ json: shipmentHistory });
  });

  await page.route("**/shipments/ship-001", async (route) => {
    await route.fulfill({ json: shipmentBundle });
  });

  await page.route("**/shipments", async (route) => {
    await route.fulfill({ json: shipments });
  });

  await page.route("**/source-health", async (route) => {
    await route.fulfill({ json: sourceHealth });
  });

  await page.route("**/sources/readiness", async (route) => {
    await route.fulfill({
      json: [
        {
          source: "aisstream",
          enabled: true,
          configured: true,
          mode: "live_overlay",
          role: "live movement bootstrap",
          business_safe_default: true,
          detail: "Recent live position source",
        },
      ],
    });
  });

  await page.route("**/knowledge/search?*", async (route) => {
    await route.fulfill({
      json: {
        query: "test",
        shipment_id: "ship-001",
        snippets: [],
        retrieved_at: "2026-03-29T00:00:00Z",
      },
    });
  });

  await page.route("**/agent/agents/state", async (route) => {
    await route.fulfill({
      json: {
        threadId: "shipment-ship-001",
        threadExists: false,
        state: "{}",
        messages: "[]",
      },
    });
  });
});

test("supports shipment, tracking, and analytics flows in the browser", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("GREAT ABIDJAN")).toBeVisible();
  await expect(page.getByText("#SAL-LAG-24001")).toBeVisible();

  await page.getByRole("button", { name: "Tracking" }).click();
  await expect(page.getByText("Shipment Details")).toBeVisible();
  await expect(page.getByText("Current Position")).toBeVisible();

  await page.getByRole("button", { name: "Analytics" }).click();
  await expect(page.getByText("Source Health")).toBeVisible();
  await expect(page.getByText("aisstream")).toBeVisible();
});
