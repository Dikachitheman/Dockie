import { Bell, Bot, CalendarClock, Ship, Sparkles } from "lucide-react";
import type { Shipment } from "@/lib/shipment-ui";
import type { AgentNotification, StandbyAgent } from "@/lib/standby-agents";

interface HomeOverviewProps {
  shipments: Shipment[];
  agents: StandbyAgent[];
  notifications: AgentNotification[];
}

export default function HomeOverview({ shipments, agents, notifications }: HomeOverviewProps) {
  const activeShipments = shipments.filter((shipment) => shipment.status === "open" || shipment.status === "in_transit").length;
  const activeAgents = agents.filter((agent) => agent.status === "active").length;
  const unreadNotifications = notifications.filter((notification) => notification.unread).length;
  const confidenceValues = shipments
    .map((shipment) => shipment.etaConfidence?.score)
    .filter((value): value is number => typeof value === "number");
  const avgConfidence = confidenceValues.length > 0
    ? Math.round((confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length) * 100)
    : null;
  const lowConfidenceCount = shipments.filter((shipment) => (shipment.etaConfidence?.score ?? 1) < 0.45).length;
  const staleShipmentCount = shipments.filter((shipment) => Boolean(shipment.freshnessWarning)).length;
  const attentionShipment = shipments.find((shipment) => shipment.freshnessWarning || (shipment.etaConfidence?.score ?? 1) < 0.45) ?? shipments[0] ?? null;
  const recentlyFired = agents.find((agent) => agent.status === "fired");

  return (
    <div className="flex flex-1 overflow-y-auto bg-[#f7f5ef] p-4 sm:p-8 scrollbar-thin">
      <div className="mx-auto w-full max-w-6xl space-y-4 sm:space-y-6">
        <div className="rounded-[20px] sm:rounded-[28px] bg-[radial-gradient(circle_at_top_left,#f6d67c_0%,#d9e4f7_35%,#f8f5ef_100%)] p-5 sm:p-8 shadow-apple">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-apple-secondary">
            <Sparkles className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
            Daily Control Tower
          </div>
          <h1 className="mt-3 text-3xl font-semibold text-apple-text">What matters across your shipment operation today</h1>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-apple-secondary">
            Standby agents, shipment milestones, and live notifications are surfaced here so you can act on exceptions instead of hunting through every shipment manually.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="apple-card p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
              <Ship className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
              Active Shipments
            </div>
            <p className="mt-3 text-3xl font-semibold text-apple-text">{activeShipments}</p>
            <p className="mt-1 text-sm text-apple-secondary">Shipments currently moving or still open.</p>
          </div>
          <div className="apple-card p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
              <Bot className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
              Active Agents
            </div>
            <p className="mt-3 text-3xl font-semibold text-apple-text">{activeAgents}</p>
            <p className="mt-1 text-sm text-apple-secondary">Background watchers monitoring timing and risk conditions.</p>
          </div>
          <div className="apple-card p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
              <Bell className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
              Unread Alerts
            </div>
            <p className="mt-3 text-3xl font-semibold text-apple-text">{unreadNotifications}</p>
            <p className="mt-1 text-sm text-apple-secondary">Agent actions and recent attention items waiting for review.</p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="apple-card p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
              <Sparkles className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
              Avg ETA Confidence
            </div>
            <p className="mt-3 text-3xl font-semibold text-apple-text">{avgConfidence != null ? `${avgConfidence}%` : "N/A"}</p>
            <p className="mt-1 text-sm text-apple-secondary">Average across shipments with enough data to score.</p>
          </div>
          <div className="apple-card p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
              <Ship className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
              Low-confidence ETAs
            </div>
            <p className="mt-3 text-3xl font-semibold text-apple-text">{lowConfidenceCount}</p>
            <p className="mt-1 text-sm text-apple-secondary">Shipments that may need manual follow-up or schedule verification.</p>
          </div>
          <div className="apple-card p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
              <Bell className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
              Stale tracking signals
            </div>
            <p className="mt-3 text-3xl font-semibold text-apple-text">{staleShipmentCount}</p>
            <p className="mt-1 text-sm text-apple-secondary">Shipments currently carrying a freshness warning.</p>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.3fr_0.9fr]">
          <div className="apple-card p-6">
            <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
              <CalendarClock className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
              Morning Briefing
            </div>
            {attentionShipment ? (
              <>
                <p className="mt-4 text-lg font-semibold text-apple-text">{attentionShipment.bookingReference} is the shipment to watch today</p>
                <p className="mt-2 text-sm leading-relaxed text-apple-secondary">
                  {attentionShipment.freshnessWarning
                    ? attentionShipment.freshnessWarning
                    : `${attentionShipment.bookingReference} is active on the ${attentionShipment.carrier} lane and remains the best candidate for a manual morning review.`}
                </p>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div className="rounded-[16px] bg-apple-surface p-4">
                    <p className="text-xs uppercase tracking-[0.12em] text-apple-secondary">Vessel</p>
                    <p className="mt-1 text-sm font-medium text-apple-text">{attentionShipment.candidateVessels[0]?.name ?? "Awaiting assignment"}</p>
                  </div>
                  <div className="rounded-[16px] bg-apple-surface p-4">
                    <p className="text-xs uppercase tracking-[0.12em] text-apple-secondary">ETA confidence</p>
                    <p className="mt-1 text-sm font-medium text-apple-text">
                      {attentionShipment.etaConfidence ? `${Math.round(attentionShipment.etaConfidence.score * 100)}%` : "unknown"}
                    </p>
                    <p className="mt-1 text-xs text-apple-secondary">{attentionShipment.etaConfidence?.freshness ?? "no freshness signal"}</p>
                  </div>
                </div>
              </>
            ) : (
              <p className="mt-4 text-sm text-apple-secondary">No shipment briefing yet. Load shipments and standby agents to populate the dashboard.</p>
            )}
          </div>

          <div className="space-y-6">
            <div className="apple-card p-6">
              <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
                <Bot className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
                Standby Agent Spotlight
              </div>
              {recentlyFired ? (
                <>
                  <p className="mt-4 text-sm font-medium text-apple-text">{recentlyFired.conditionText}</p>
                  <p className="mt-2 text-sm leading-relaxed text-apple-secondary">{recentlyFired.lastResult ?? "Agent recently fired."}</p>
                </>
              ) : (
                <p className="mt-4 text-sm text-apple-secondary">No agent has fired yet. Create a watcher from the Agents page or directly from the shipment prompt box.</p>
              )}
            </div>

            <div className="apple-card p-6">
              <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
                <Bell className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
                Recent Notifications
              </div>
              <div className="mt-4 space-y-3">
                {notifications.length === 0 ? (
                  <p className="text-sm text-apple-secondary">No notifications yet.</p>
                ) : (
                  notifications.slice(0, 4).map((notification) => (
                    <div key={notification.id} className="rounded-[14px] bg-apple-surface p-3">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-medium text-apple-text">{notification.title}</p>
                        {notification.unread && <span className="h-2 w-2 rounded-full bg-apple-blue" />}
                      </div>
                      <p className="mt-1 text-sm leading-relaxed text-apple-secondary">{notification.detail}</p>
                      {notification.createdAt && (
                        <p className="mt-2 text-[11px] text-apple-secondary/70">{new Date(notification.createdAt).toLocaleString()}</p>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
