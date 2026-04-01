import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ChatPanel from "@/components/ChatPanel";
import type { Shipment } from "@/lib/shipment-ui";
import {
  compareShipments,
  getDemurrageExposure,
  getSourceReadiness,
  runAgentStream,
  searchFakeWeb,
  searchFakeWebPlan,
  searchKnowledgeBase,
  type UiChatMessage,
} from "@/lib/api";

vi.mock("@/components/ShipmentMap", () => ({
  default: () => <div data-testid="shipment-map">map</div>,
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    compareShipments: vi.fn(),
    getDemurrageExposure: vi.fn(),
    getSourceReadiness: vi.fn(),
    runAgentStream: vi.fn(),
    searchFakeWeb: vi.fn(),
    searchFakeWebPlan: vi.fn(),
    searchKnowledgeBase: vi.fn(),
  };
});

function makeShipment(overrides: Partial<Shipment> = {}): Shipment {
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

function ChatPanelHarness() {
  const [messages, setMessages] = useState<UiChatMessage[]>([]);

  return (
    <ChatPanel
      shipment={makeShipment()}
      threadId="thread-001"
      messages={messages}
      onMessagesChange={setMessages}
    />
  );
}

function ChatPanelMessageHarness({
  shipment = makeShipment(),
  onCreateStandbyAgent,
  initialMessages,
}: {
  shipment?: Shipment;
  onCreateStandbyAgent?: (draft: any) => void | Promise<void>;
  initialMessages: UiChatMessage[];
}) {
  const [messages, setMessages] = useState<UiChatMessage[]>(initialMessages);

  return (
    <ChatPanel
      shipment={shipment}
      threadId="thread-001"
      messages={messages}
      onMessagesChange={setMessages}
      onCreateStandbyAgent={onCreateStandbyAgent}
    />
  );
}

describe("ChatPanel web search states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Element.prototype.scrollIntoView = vi.fn();

    vi.mocked(getSourceReadiness).mockResolvedValue([]);
    vi.mocked(compareShipments).mockResolvedValue({
      comparedAt: "2026-03-30T10:00:00Z",
      recommendation: "SAL-LAG-24001 needs more attention.",
      shipments: [
        {
          shipmentId: "ship-001",
          bookingReference: "SAL-LAG-24001",
          carrier: "sallaum",
          status: "open",
          riskScore: 0.78,
          summary: "Great Abidjan needs attention.",
          freshness: "aging",
        },
        {
          shipmentId: "ship-002",
          bookingReference: "GRI-LAG-24003",
          carrier: "grimaldi",
          status: "open",
          riskScore: 0.24,
          summary: "Grande Tema is on track.",
          freshness: "fresh",
        },
      ],
    });
    vi.mocked(getDemurrageExposure).mockResolvedValue({
      shipmentId: "ship-001",
      terminalLocode: "NGLOS",
      freeDays: 2,
      dailyRateNgn: 18500,
      dailyRateUsd: null,
      projectedCostNgn: 222000,
      projectedCostUsd: null,
      clearanceRiskDays: 2,
      riskLevel: "high",
      freeDaysEnd: "2026-04-03T00:00:00Z",
      notes: ["Missing checklist items: form_m_approved, trucking_booked."],
    });
    vi.mocked(searchKnowledgeBase).mockResolvedValue([]);
    vi.mocked(searchFakeWebPlan).mockResolvedValue({
      query: "Lagos congestion update",
      normalizedQuery: "lagos congestion update",
      topics: ["congestion"],
      candidateSources: [
        {
          id: "nigeria-port-watch",
          name: "Nigeria Port Watch",
          baseUrl: "https://fake-websites-84bc.vercel.app",
          searchIndexUrl: "https://fake-websites-84bc.vercel.app/search-index.json",
          sourceClass: "industry_media",
          trustLevel: "high",
          matchReason: "Port congestion coverage",
          status: "queued",
        },
      ],
      retrievedAt: "2026-03-30T10:00:00Z",
      searchMode: "planned",
    });
    vi.mocked(searchFakeWeb).mockResolvedValue({
      query: "Lagos congestion update",
      normalizedQuery: "lagos congestion update",
      topics: ["congestion"],
      candidateSources: [],
      results: [
        {
          id: "port-001",
          title: "Apapa yard dwell time extends for inbound units",
          url: "https://fake-websites-84bc.vercel.app/articles/apapa-yard-dwell-time",
          source: "Nigeria Port Watch",
          sourceId: "nigeria-port-watch",
          sourceType: "article",
          sourceClass: "industry_media",
          trustLevel: "high",
          published: "2026-03-28T09:00:00Z",
          updated: "2026-03-29T11:00:00Z",
          summary: "Yard congestion remains elevated.",
          snippet: "Terminal dwell time remains elevated for ro-ro cargo this week.",
          tags: ["lagos", "congestion", "terminal"],
          relevanceScore: 0.91,
          matchReason: "Matched on Lagos congestion and terminal dwell time.",
        },
      ],
      retrievedAt: "2026-03-30T10:00:05Z",
      searchMode: "remote",
    });
  });

  it("shows queued web sources during streaming and renders source cards after completion", async () => {
    let releaseStream: (() => void) | null = null;
    vi.mocked(runAgentStream).mockImplementation(async ({ onEvent, onAssistantDelta }) => {
      onEvent?.({ type: "RUN_STARTED" });
      onEvent?.({ type: "TOOL_CALL_START", toolCallId: "tool-web-1", toolCallName: "search_supporting_context" });

      await new Promise<void>((resolve) => {
        releaseStream = resolve;
      });

      onEvent?.({ type: "TOOL_CALL_END", toolCallId: "tool-web-1", toolCallName: "search_supporting_context" });
      onEvent?.({ type: "TEXT_MESSAGE_START", messageId: "assistant-001" });
      onAssistantDelta("Fresh Lagos congestion context is now available.", "assistant-001");
    });

    render(<ChatPanelHarness />);

    const input = screen.getByPlaceholderText("Ask for status, confidence, changes, or evidence...");
    fireEvent.change(input, { target: { value: "Lagos congestion update" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", charCode: 13 });

    expect(await screen.findByText("Reviewing external context")).toBeInTheDocument();
    expect(await screen.findByText("Remote sources")).toBeInTheDocument();
    expect((await screen.findAllByText("Nigeria Port Watch")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("queued")).length).toBeGreaterThan(0);

    releaseStream?.();

    expect(await screen.findByText("Web sources")).toBeInTheDocument();
    expect((await screen.findAllByText("Apapa yard dwell time extends for inbound units")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Why this matched: Matched on Lagos congestion and terminal dwell time.")).toBeInTheDocument();
    expect((await screen.findAllByText("updated Mar 29, 2026")).length).toBeGreaterThan(0);
  });

  it("shows a partial-availability notice when web enrichment fails after the agent response", async () => {
    vi.mocked(searchFakeWeb).mockRejectedValue(new Error("remote web timeout"));
    vi.mocked(runAgentStream).mockImplementation(async ({ onEvent, onAssistantDelta }) => {
      onEvent?.({ type: "RUN_STARTED" });
      onEvent?.({ type: "TOOL_CALL_START", toolCallId: "tool-web-2", toolCallName: "search_supporting_context" });
      onEvent?.({ type: "TOOL_CALL_END", toolCallId: "tool-web-2", toolCallName: "search_supporting_context" });
      onEvent?.({ type: "TEXT_MESSAGE_START", messageId: "assistant-002" });
      onAssistantDelta("I found internal evidence about the delay.", "assistant-002");
    });

    render(<ChatPanelHarness />);

    const input = screen.getByPlaceholderText("Ask for status, confidence, changes, or evidence...");
    fireEvent.change(input, { target: { value: "Why is Lagos delayed?" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", charCode: 13 });

    expect(await screen.findByText("Web sources")).toBeInTheDocument();
    expect(
      await screen.findByText(
        "External web context was only partially available: remote web timeout. Internal evidence may still be complete.",
      ),
    ).toBeInTheDocument();
  });

  it("cleans up the live stream and shows a friendly message when the model is temporarily unavailable", async () => {
    vi.mocked(runAgentStream).mockImplementation(async ({ onEvent }) => {
      onEvent?.({ type: "RUN_STARTED" });
      onEvent?.({
        type: "RUN_ERROR",
        code: "MODEL_UNAVAILABLE",
        message: "The model is temporarily overloaded right now. Please try again in a moment.",
      });
      throw new Error("The model is temporarily overloaded right now. Please try again in a moment.");
    });

    render(<ChatPanelHarness />);

    const input = screen.getByPlaceholderText("Ask for status, confidence, changes, or evidence...");
    fireEvent.change(input, { target: { value: "Where is this vessel now?" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", charCode: 13 });

    expect(await screen.findByText(/I could not reach the shipment agent just now/i)).toBeInTheDocument();
    expect(await screen.findByText(/temporarily overloaded right now/i)).toBeInTheDocument();
    expect(screen.queryByText("Dockie agent is working")).not.toBeInTheDocument();
  });

  it("passes a repeated-intent reuse hint for short-window follow-up shipment questions", async () => {
    vi.mocked(runAgentStream)
      .mockImplementationOnce(async ({ onEvent, onAssistantDelta }) => {
        onEvent?.({ type: "RUN_STARTED" });
        onEvent?.({ type: "TEXT_MESSAGE_START", messageId: "assistant-repeat-1" });
        onAssistantDelta("Fresh position update.", "assistant-repeat-1");
      })
      .mockImplementationOnce(async ({ onEvent, onAssistantDelta }) => {
        onEvent?.({ type: "RUN_STARTED" });
        onEvent?.({ type: "TEXT_MESSAGE_START", messageId: "assistant-repeat-2" });
        onAssistantDelta("Still offshore Lagos.", "assistant-repeat-2");
      });

    render(<ChatPanelHarness />);

    const input = screen.getByPlaceholderText("Ask for status, confidence, changes, or evidence...");
    fireEvent.change(input, { target: { value: "Where is this shipment now?" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", charCode: 13 });
    expect(await screen.findByText("Fresh position update.")).toBeInTheDocument();
    expect(await screen.findByText("How reliable is this location update?")).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "Where is it now?" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", charCode: 13 });
    await waitFor(() => expect(vi.mocked(runAgentStream)).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Still offshore Lagos.")).toBeInTheDocument();

    const secondCall = vi.mocked(runAgentStream).mock.calls[1]?.[0];
    expect(secondCall?.state).toMatchObject({
      recent_intent_kind: "shipment_location",
      recent_intent_repeated: true,
    });
  });

  it("does not render the voyage timeline card for a basic current-location answer", async () => {
    render(
      <ChatPanelMessageHarness
        shipment={makeShipment({
          currentPosition: {
            source: "aisstream",
            observedAt: "2026-03-30T08:15:00Z",
            mmsi: "123456789",
            imo: "IMO123",
            vesselName: "Great Abidjan",
            latitude: 5.25,
            longitude: 3.85,
            speedKnots: 14.2,
            courseDegrees: 120,
            headingDegrees: 118,
            navStatus: "under_way_using_engine",
            destination: "LAGOS",
          },
          events: [
            { eventType: "departed_baltimore", eventAt: "2026-03-10T08:45:00Z", details: "Departed Baltimore", source: "carrier_schedule" },
          ],
          historyPoints: [
            { observedAt: "2026-03-29T08:15:00Z", latitude: 4.8, longitude: 3.4, speedKnots: 13.5, courseDegrees: 121, source: "aisstream" },
          ],
        })}
        initialMessages={[
          {
            id: "user-location-1",
            role: "user",
            content: "Where is this shipment now?",
            timestamp: "10:00",
          },
          {
            id: "assistant-location-1",
            role: "assistant",
            content: "The vessel is currently offshore Lagos with a fresh tracking position.",
            timestamp: "10:01",
            richComponents: ["tracking"],
          },
        ]}
      />,
    );

    expect(await screen.findByText(/The vessel is currently offshore Lagos/i)).toBeInTheDocument();
    expect(screen.getByTestId("shipment-map")).toBeInTheDocument();
    expect(screen.queryByText("Voyage events")).not.toBeInTheDocument();
  });

  it("renders grounded badges plus the demurrage and voyage cards for status-rich answers", async () => {
    render(
      <ChatPanelMessageHarness
        shipment={makeShipment({
          currentPosition: {
            source: "aisstream",
            observedAt: "2026-03-30T08:15:00Z",
            mmsi: "123456789",
            imo: "IMO123",
            vesselName: "Great Abidjan",
            latitude: 5.25,
            longitude: 3.85,
            speedKnots: 14.2,
            courseDegrees: 120,
            headingDegrees: 118,
            navStatus: "under_way_using_engine",
            destination: "LAGOS",
          },
          etaConfidence: {
            score: 0.38,
            freshness: "aging",
            explanation: "Position is aging.",
            declaredEta: "2026-04-06T00:00:00Z",
          },
          evidenceCount: 3,
          events: [
            { eventType: "departed_baltimore", eventAt: "2026-03-10T08:45:00Z", details: "Departed Baltimore", source: "carrier_schedule" },
            { eventType: "lagos_destination_detected", eventAt: "2026-03-20T12:00:00Z", details: "AIS destination updated", source: "aisstream" },
          ],
          historyPoints: [
            { observedAt: "2026-03-29T08:15:00Z", latitude: 4.8, longitude: 3.4, speedKnots: 13.5, courseDegrees: 121, source: "aisstream" },
          ],
        })}
        initialMessages={[
          {
            id: "user-1",
            role: "user",
            content: "What is the demurrage risk and what changed on this voyage?",
            timestamp: "10:00",
          },
          {
            id: "assistant-1",
            role: "assistant",
            content: "Demurrage risk is rising and the voyage timeline shows a recent Lagos destination update.",
            timestamp: "10:01",
            richComponents: ["tracking"],
          },
        ]}
      />,
    );

    expect(await screen.findByText(/ETA confidence 0.38/i)).toBeInTheDocument();
    expect(await screen.findByText("Demurrage exposure")).toBeInTheDocument();
    expect(await screen.findByText("Voyage events")).toBeInTheDocument();
    expect(await screen.findByText(/Projected cost/i)).toBeInTheDocument();
  });

  it("shows the inline standby creator and can create a watcher from chat", async () => {
    const onCreateStandbyAgent = vi.fn().mockResolvedValue(undefined);

    render(
      <ChatPanelMessageHarness
        onCreateStandbyAgent={onCreateStandbyAgent}
        initialMessages={[
          {
            id: "user-2",
            role: "user",
            content: "Please alert me when this shipment reaches Lagos.",
            timestamp: "11:00",
          },
          {
            id: "assistant-2",
            role: "assistant",
            content: "I can keep watching this shipment and notify you when it arrives.",
            timestamp: "11:01",
          },
        ]}
      />,
    );

    expect(await screen.findByText("Watch this shipment")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Create watcher"));
    expect(await screen.findByText("Watcher active")).toBeInTheDocument();
    expect(onCreateStandbyAgent).toHaveBeenCalled();
  });

  it("renders the standby alert card, comparison strip, and voice mode toggle", async () => {
    const onSelectShipment = vi.fn();

    render(
      <ChatPanel
        shipment={makeShipment()}
        shipments={[
          makeShipment(),
          makeShipment({ shipmentId: "ship-002", bookingReference: "GRI-LAG-24003" }),
        ]}
        notifications={[
          {
            id: "notif-1",
            userId: "user-1",
            agentId: "agent-1",
            channel: "in_app",
            title: "Lagos arrival signal detected",
            detail: "SAL-LAG-24001 is showing a Lagos-bound arrival signal.",
            unread: true,
            readAt: null,
            createdAt: "2026-03-30T10:02:00Z",
          },
        ]}
        threadId="thread-001"
        messages={[
          {
            id: "user-3",
            role: "user",
            content: "Compare my shipments and keep this one on watch.",
            timestamp: "12:00",
          },
          {
            id: "assistant-3",
            role: "assistant",
            content: "This shipment needs attention and I can keep watching it.",
            timestamp: "12:01",
          },
        ]}
        onMessagesChange={() => {}}
        onSelectShipment={onSelectShipment}
      />,
    );

    expect(await screen.findByText("Standby agent fired")).toBeInTheDocument();
    expect(await screen.findByText("Active shipments")).toBeInTheDocument();
    expect(await screen.findByText("Voice mode off")).toBeInTheDocument();
    fireEvent.click(screen.getByText("#GRI-LAG-24003"));
    expect(onSelectShipment).toHaveBeenCalledWith("ship-002");
  });
});
