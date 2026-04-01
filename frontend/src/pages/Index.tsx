import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { User } from "@supabase/supabase-js";
import { Ship } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import AppSidebar from "@/components/AppSidebar";
import HomeOverview from "@/components/HomeOverview";
import ShipmentList from "@/components/ShipmentList";
import ChatPanel from "@/components/ChatPanel";
import TrackingView from "@/components/TrackingView";
import SourceHealthDashboard from "@/components/SourceHealthDashboard";
import StandbyAgentsView from "@/components/StandbyAgentsView";
import AgentNotificationsView from "@/components/AgentNotificationsView";
import AgentOutputDetailView from "@/components/AgentOutputDetailView";
import SettingsView from "@/components/SettingsView";
import {
  createStandbyAgent,
  getAppBootstrap,
  deleteStandbyAgent,
  getAgentOutput,
  getShipmentBundle,
  getThreadMessages,
  listAgentOutputs,
  listNotifications,
  listStandbyAgents,
  markNotificationsRead,
  runStandbyAgent,
  updateStandbyAgent,
  type UiChatMessage,
} from "@/lib/api";
import { type Shipment, type SourceHealth } from "@/lib/shipment-ui";
import type { AgentNotification, AgentOutput, StandbyAgent, StandbyAgentDraft } from "@/lib/standby-agents";

type ExtendedMessage = UiChatMessage & { isVoice?: boolean };
type AppView = "home" | "shipments" | "tracking" | "agents" | "analytics" | "notifications" | "output-detail" | "settings";
type OutputPanel = "agents" | "email" | "report" | "spreadsheet" | "document";

const viewRoutes: Record<Exclude<AppView, "output-detail">, string> = {
  home: "/home",
  shipments: "/",
  tracking: "/tracking",
  agents: "/agents",
  analytics: "/analytics",
  notifications: "/notifications",
  settings: "/settings",
};

function viewFromPath(pathname: string): AppView {
  if (pathname === "/" || pathname === "/shipments") return "shipments";
  if (pathname.startsWith("/home")) return "home";
  if (pathname.startsWith("/tracking")) return "tracking";
  if (pathname.startsWith("/agents")) return "agents";
  if (pathname.startsWith("/analytics")) return "analytics";
  if (pathname.startsWith("/notifications")) return "notifications";
  if (pathname.startsWith("/outputs/")) return "output-detail";
  if (pathname.startsWith("/settings")) return "settings";
  return "shipments";
}

function outputIdFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/outputs\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function createWelcome(shipment: Shipment | null): ExtendedMessage[] {
  if (!shipment) return [];

  const vesselName = shipment.candidateVessels[0]?.name ?? "unassigned vessel";
  const route = `${shipment.loadPort ?? "origin pending"} to ${shipment.dischargePort ?? "destination pending"}`;

  return [
    {
      id: `welcome-${shipment.shipmentId}`,
      role: "assistant",
      content: `I am tracking **${shipment.bookingReference}** on **${vesselName}** from ${route}. Ask for status, ETA confidence, vessel position, freshness, or source health.`,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      shipmentCard: true,
    },
  ];
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="text-center">
        <Ship className="mx-auto h-12 w-12 text-apple-secondary/20" strokeWidth={1.5} />
        <p className="mt-3 text-sm text-apple-secondary">{text}</p>
      </div>
    </div>
  );
}

function LoadingPane({ text }: { text: string }) {
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="text-center">
        <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-apple-divider border-t-apple-blue" />
        <p className="mt-3 text-sm text-apple-secondary">{text}</p>
      </div>
    </div>
  );
}

const Index = ({ user }: { user?: User }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const activeView = useMemo(() => viewFromPath(location.pathname), [location.pathname]);
  const selectedOutputId = useMemo(() => outputIdFromPath(location.pathname), [location.pathname]);
  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [selectedShipmentId, setSelectedShipmentId] = useState<string | null>(null);
  const [selectedShipment, setSelectedShipment] = useState<Shipment | null>(null);
  const [shipmentCache, setShipmentCache] = useState<Record<string, Shipment>>({});
  const [sourceHealth, setSourceHealth] = useState<SourceHealth[]>([]);
  const [messagesByShipment, setMessagesByShipment] = useState<Record<string, ExtendedMessage[]>>({});
  const [standbyAgents, setStandbyAgents] = useState<StandbyAgent[]>([]);
  const [agentNotifications, setAgentNotifications] = useState<AgentNotification[]>([]);
  const [agentOutputs, setAgentOutputs] = useState<AgentOutput[]>([]);
  const [activeOutputPanel, setActiveOutputPanel] = useState<OutputPanel>(() => {
    const params = new URLSearchParams(window.location.search);
    return (params.get("outputSection") as OutputPanel | null) ?? "agents";
  });
  const [outputReturnView, setOutputReturnView] = useState<AppView>(() => {
    const params = new URLSearchParams(window.location.search);
    return (params.get("outputFrom") as AppView | null) ?? "agents";
  });
  const [selectedOutput, setSelectedOutput] = useState<AgentOutput | null>(null);
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  const [shipmentsLoading, setShipmentsLoading] = useState(true);
  const [shipmentLoading, setShipmentLoading] = useState(false);
  const [sourceHealthLoading, setSourceHealthLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [visitedViews, setVisitedViews] = useState<Set<AppView>>(() => new Set([viewFromPath(window.location.pathname)]));

  const seenNotificationIdsRef = useRef<Set<string>>(new Set());

  const refreshStandbyData = useCallback(async () => {
    const [agents, notifications, outputs] = await Promise.all([listStandbyAgents(), listNotifications(), listAgentOutputs()]);
    setStandbyAgents(agents);
    setAgentNotifications(notifications);
    setAgentOutputs(outputs);
  }, []);

  useEffect(() => {
    setVisitedViews((current) => {
      if (current.has(activeView)) {
        return current;
      }
      return new Set([...current, activeView]);
    });
  }, [activeView]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    setActiveOutputPanel((params.get("outputSection") as OutputPanel | null) ?? "agents");
    setOutputReturnView((params.get("outputFrom") as AppView | null) ?? "agents");
  }, [location.search]);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      setShipmentsLoading(true);
      setSourceHealthLoading(true);
      setPageError(null);

      try {
        const bootstrapData = await getAppBootstrap();
        if (cancelled) return;

        setShipments(bootstrapData.shipments);
        setSourceHealth(bootstrapData.sourceHealth);
        setStandbyAgents(bootstrapData.standbyAgents);
        setAgentNotifications(bootstrapData.notifications);
        setAgentOutputs(bootstrapData.agentOutputs);
        seenNotificationIdsRef.current = new Set(bootstrapData.notifications.map((item) => item.id));
        setSelectedShipmentId((current) => current ?? bootstrapData.shipments[0]?.shipmentId ?? null);
      } catch (error) {
        if (!cancelled) {
          setPageError(error instanceof Error ? error.message : "Failed to load Dockie data.");
        }
      } finally {
        if (!cancelled) {
          setShipmentsLoading(false);
          setSourceHealthLoading(false);
        }
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const shouldPollStandby =
      (activeView === "agents" || activeView === "notifications" || activeView === "home" || activeView === "output-detail")
      && standbyAgents.length > 0;

    if (!shouldPollStandby) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const [agents, notifications, outputs] = await Promise.all([listStandbyAgents(), listNotifications(), listAgentOutputs()]);
        if (cancelled) return;
        setStandbyAgents(agents);
        setAgentNotifications(notifications);
        setAgentOutputs(outputs);
      } catch {
        // Keep polling silent so transient refresh failures do not interrupt the UI.
      }
    };

    void poll();
    const intervalId = window.setInterval(() => {
      void poll();
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [activeView, standbyAgents.length]);

  useEffect(() => {
    if (!selectedOutputId) {
      setSelectedOutput(null);
      return;
    }

    const fromList = agentOutputs.find((output) => output.id === selectedOutputId) ?? null;
    if (fromList) {
      setSelectedOutput(fromList);
      return;
    }

    let cancelled = false;
    void getAgentOutput(selectedOutputId)
      .then((output) => {
        if (!cancelled) {
          setSelectedOutput(output);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSelectedOutput(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [agentOutputs, selectedOutputId]);

  useEffect(() => {
    if (!selectedShipmentId) {
      setSelectedShipment(null);
      return;
    }

    let cancelled = false;

    async function loadShipmentContext() {
      const cachedShipment = shipmentCache[selectedShipmentId];
      if (cachedShipment) {
        setSelectedShipment(cachedShipment);
        setMessagesByShipment((current) => {
          if (current[selectedShipmentId]) {
            return current;
          }
          return {
            ...current,
            [selectedShipmentId]: createWelcome(cachedShipment),
          };
        });
        return;
      }

      setShipmentLoading(true);
      try {
        const [bundle, threadMessages] = await Promise.all([
          getShipmentBundle(selectedShipmentId),
          getThreadMessages(`shipment-${selectedShipmentId}`),
        ]);

        if (cancelled) return;

        setSelectedShipment(bundle);
        setShipmentCache((current) => ({
          ...current,
          [selectedShipmentId]: bundle,
        }));
        setMessagesByShipment((current) => {
          if (current[selectedShipmentId]) {
            return current;
          }
          return {
            ...current,
            [selectedShipmentId]: threadMessages.length > 0 ? threadMessages : createWelcome(bundle),
          };
        });
      } catch (error) {
        if (!cancelled) {
          setPageError(error instanceof Error ? error.message : "Failed to load shipment details.");
        }
      } finally {
        if (!cancelled) {
          setShipmentLoading(false);
        }
      }
    }

    void loadShipmentContext();
    return () => {
      cancelled = true;
    };
  }, [selectedShipmentId, shipmentCache]);

  const currentMessages = useMemo(() => {
    if (!selectedShipmentId) return [];
    return messagesByShipment[selectedShipmentId] ?? [];
  }, [messagesByShipment, selectedShipmentId]);

  const handleMessagesChange = useCallback((shipmentId: string, messages: ExtendedMessage[]) => {
    setMessagesByShipment((current) => ({
      ...current,
      [shipmentId]: messages,
    }));
  }, []);

  const selectedShipmentSummary = useMemo(
    () => shipments.find((shipment) => shipment.shipmentId === selectedShipmentId) ?? null,
    [shipments, selectedShipmentId],
  );

  const shipmentForPanels = selectedShipment ?? selectedShipmentSummary;
  const unreadNotifications = agentNotifications.filter((notification) => notification.unread).length;

  useEffect(() => {
    if (!shipments.length) {
      return;
    }

    const outputsById = new Map(agentOutputs.map((output) => [output.id, output]));
    const agentsById = new Map(standbyAgents.map((agent) => [agent.id, agent]));
    const shipmentIds = new Set(shipments.map((shipment) => shipment.shipmentId));

    for (const notification of agentNotifications) {
      if (seenNotificationIdsRef.current.has(notification.id)) {
        continue;
      }
      seenNotificationIdsRef.current.add(notification.id);

      const output = notification.outputId ? outputsById.get(notification.outputId) : null;
      const agent = notification.agentId ? agentsById.get(notification.agentId) : null;
      const notificationShipmentId = output?.shipmentId ?? agent?.shipmentId ?? null;
      if (!notificationShipmentId || !shipmentIds.has(notificationShipmentId)) {
        continue;
      }

      setMessagesByShipment((current) => {
        const currentMessages = current[notificationShipmentId] ?? [];
        const content = output
          ? `Standby agent update: ${notification.detail} Generated output attached below.`
          : `Standby agent update: ${notification.detail}`;
        return {
          ...current,
          [notificationShipmentId]: [
            ...currentMessages,
            {
              id: `notif-${notification.id}`,
              role: "assistant",
              content,
              timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
              agentOutputId: output?.id ?? null,
            },
          ],
        };
      });
    }
  }, [agentNotifications, agentOutputs, shipments, standbyAgents]);

  const handleCreateStandbyAgent = useCallback(async (draft: StandbyAgentDraft) => {
    const created = await createStandbyAgent(draft);
    setStandbyAgents((current) => [created, ...current]);
    await refreshStandbyData();
  }, [refreshStandbyData]);

  const handleRunStandbyAgent = useCallback(async (agentId: string) => {
    const updated = await runStandbyAgent(agentId);
    setStandbyAgents((current) => current.map((agent) => (agent.id === updated.id ? updated : agent)));
    await refreshStandbyData();
  }, [refreshStandbyData]);

  const handleDeleteStandbyAgent = useCallback(async (agentId: string) => {
    // Optimistic: remove from UI immediately before the API round-trip
    setStandbyAgents((current) => current.filter((agent) => agent.id !== agentId));
    setAgentNotifications((current) => current.filter((notification) => notification.agentId !== agentId));
    setAgentOutputs((current) => current.filter((output) => output.agentId !== agentId));
    await deleteStandbyAgent(agentId);
    await refreshStandbyData();
  }, [refreshStandbyData]);

  const handleUpdateStandbyAgent = useCallback(async (
    agentId: string,
    patch: Partial<Pick<StandbyAgent, "status">>,
  ) => {
    const updated = await updateStandbyAgent(agentId, patch);
    setStandbyAgents((current) => current.map((agent) => (agent.id === updated.id ? updated : agent)));
  }, []);

  const handleMarkNotificationsRead = useCallback(async () => {
    const updated = await markNotificationsRead();
    setAgentNotifications(updated);
  }, []);

  const handleAnalyticsAsk = useCallback((prompt: string) => {
    if (!selectedShipmentId && shipments[0]) {
      setSelectedShipmentId(shipments[0].shipmentId);
    }
    setPendingPrompt(prompt);
    navigate(viewRoutes.shipments);
  }, [navigate, selectedShipmentId, shipments]);

  const handleViewChange = useCallback((view: string) => {
    const targetRoute = viewRoutes[view as Exclude<AppView, "output-detail">];
    if (targetRoute) {
      navigate(targetRoute);
    }
  }, [navigate]);

  const handleOpenOutput = useCallback((outputId: string, returnView?: AppView) => {
    const nextReturnView = returnView ?? activeView;
    setOutputReturnView(nextReturnView);
    navigate(`/outputs/${encodeURIComponent(outputId)}?outputSection=${activeOutputPanel}&outputFrom=${nextReturnView}`);
  }, [activeOutputPanel, activeView, navigate]);

  const handleBackFromOutput = useCallback(() => {
    const targetView = outputReturnView === "output-detail" ? "agents" : outputReturnView;
    navigate(viewRoutes[targetView as Exclude<AppView, "output-detail">]);
  }, [navigate, outputReturnView]);

  return (
    <div className="flex h-screen overflow-hidden bg-white pt-14 md:pt-0">
      <AppSidebar activeView={activeView} onViewChange={handleViewChange} unreadNotifications={unreadNotifications} user={user} />

      {(visitedViews.has("shipments") || visitedViews.has("tracking")) && (
        <div className={activeView === "shipments" || activeView === "tracking" ? "" : "hidden"}>
          <ShipmentList shipments={shipments} selectedId={selectedShipmentId} onSelect={setSelectedShipmentId} />
        </div>
      )}

      {visitedViews.has("shipments") && (
        <div className={activeView === "shipments" ? "flex flex-1 min-w-0" : "hidden"}>
          {pageError ? (
            <EmptyState text={pageError} />
          ) : shipmentsLoading ? (
            <LoadingPane text="Loading shipments from the Dockie backend" />
          ) : shipmentLoading || !shipmentForPanels ? (
            <LoadingPane text="Loading shipment context" />
          ) : (
            <ChatPanel
              shipment={shipmentForPanels}
              shipments={shipments}
              notifications={agentNotifications}
              agentOutputs={agentOutputs}
              threadId={`shipment-${shipmentForPanels.shipmentId}`}
              messages={currentMessages}
              onMessagesChange={(messages) => handleMessagesChange(shipmentForPanels.shipmentId, messages)}
              onCreateStandbyAgent={handleCreateStandbyAgent}
              onSelectShipment={setSelectedShipmentId}
              onOpenOutput={handleOpenOutput}
              pendingPrompt={pendingPrompt}
              onPendingPromptConsumed={() => setPendingPrompt(null)}
            />
          )}
        </div>
      )}

      {visitedViews.has("tracking") && (
        <div className={activeView === "tracking" ? "flex flex-1 min-w-0" : "hidden"}>
          {pageError ? (
            <EmptyState text={pageError} />
          ) : shipmentsLoading ? (
            <LoadingPane text="Loading shipment tracking" />
          ) : shipmentLoading || !shipmentForPanels ? (
            <LoadingPane text="Loading tracking details" />
          ) : (
            <TrackingView shipment={shipmentForPanels} shipments={shipments} />
          )}
        </div>
      )}

      {visitedViews.has("agents") && (
        <div className={activeView === "agents" ? "flex flex-1 min-w-0" : "hidden"}>
          <StandbyAgentsView
            agents={standbyAgents}
            outputs={agentOutputs}
            shipments={shipments}
            activePanel={activeOutputPanel}
            onActivePanelChange={setActiveOutputPanel}
            onCreateAgent={handleCreateStandbyAgent}
            onRunAgent={handleRunStandbyAgent}
            onDeleteAgent={handleDeleteStandbyAgent}
            onUpdateAgent={handleUpdateStandbyAgent}
            onOpenOutput={(outputId) => handleOpenOutput(outputId, "agents")}
          />
        </div>
      )}

      {visitedViews.has("analytics") && (
        <div className={activeView === "analytics" ? "flex flex-1 min-w-0" : "hidden"}>
          <SourceHealthDashboard
            sourceHealth={sourceHealth}
            shipments={shipments}
            loading={sourceHealthLoading}
            error={pageError}
            onAsk={handleAnalyticsAsk}
          />
        </div>
      )}

      {visitedViews.has("home") && (
        <div className={activeView === "home" ? "flex flex-1 min-w-0" : "hidden"}>
          <HomeOverview shipments={shipments} agents={standbyAgents} notifications={agentNotifications} />
        </div>
      )}

      {visitedViews.has("notifications") && (
        <div className={activeView === "notifications" ? "flex flex-1 min-w-0" : "hidden"}>
          <AgentNotificationsView
            notifications={agentNotifications}
            outputs={agentOutputs}
            onMarkNotificationsRead={handleMarkNotificationsRead}
            onOpenOutput={(outputId) => handleOpenOutput(outputId, "notifications")}
          />
        </div>
      )}

      {visitedViews.has("output-detail") && (
        <div className={activeView === "output-detail" ? "flex flex-1 min-w-0" : "hidden"}>
          <AgentOutputDetailView output={selectedOutput} onBack={handleBackFromOutput} />
        </div>
      )}

      {visitedViews.has("settings") && (
        <div className={activeView === "settings" ? "flex flex-1 min-w-0" : "hidden"}>
          <SettingsView />
        </div>
      )}
    </div>
  );
};

export default Index;

