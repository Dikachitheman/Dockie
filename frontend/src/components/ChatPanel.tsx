import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, BookOpenText, Mic, Pause, Play, Plus, Radar, Send, ShieldCheck } from "lucide-react";
import { AgentRunError, compareShipments, getDemurrageExposure, getSourceReadiness, runAgentStream, searchFakeWeb, searchFakeWebPlan, searchKnowledgeBase, type AgentStreamEvent, type UiChatMessage, type UiRichComponent } from "@/lib/api";
import {
  type DemurrageExposure,
  type KnowledgeSnippet,
  type Shipment,
  type ShipmentComparison,
  type SourceReadiness,
  type WebSearchResult,
  type WebSearchSourcePlan,
  formatStatus,
  getDaysRemaining,
  getProgressPercent,
} from "@/lib/shipment-ui";
import {
  createStandbyAgentDraft,
  describeStandbyAction,
  formatStandbyInterval,
  parseStandbyCondition,
  type AgentOutput,
  type AgentNotification,
  type StandbyAction,
  type StandbyAgentDraft,
} from "@/lib/standby-agents";
import ShipmentMap from "./ShipmentMap";

interface ChatPanelProps {
  shipment: Shipment;
  shipments?: Shipment[];
  notifications?: AgentNotification[];
  agentOutputs?: AgentOutput[];
  threadId: string;
  messages: (UiChatMessage & { isVoice?: boolean })[];
  onMessagesChange: (msgs: (UiChatMessage & { isVoice?: boolean })[]) => void;
  onCreateStandbyAgent?: (draft: StandbyAgentDraft) => void | Promise<void>;
  onSelectShipment?: (shipmentId: string) => void;
  onOpenOutput?: (outputId: string) => void;
  pendingPrompt?: string | null;
  onPendingPromptConsumed?: () => void;
}

type ChatMessage = UiChatMessage & { isVoice?: boolean };
type RichComponent = UiRichComponent;
type RailTab = "confidence" | "evidence" | "sources";
type ResponseMode = "concise" | "balanced" | "verbose";

type ToolProgressItem = {
  id: string;
  label: string;
  status: "active" | "done";
};

type StreamStatus = {
  title: string;
  detail: string;
  startedAt: number;
};

type StreamEventItem = {
  id: string;
  label: string;
  kind: "thinking" | "tool" | "source" | "writing";
};

type RecentIntentSnapshot = {
  intentKind: string;
  shipmentId: string;
  recordedAt: number;
};

function buildFollowUpQuestions(shipment: Shipment, messages: ChatMessage[], assistantText: string): string[] {
  const latestUserText = [...messages].reverse().find((message) => message.role === "user")?.content.toLowerCase() ?? "";
  const combined = `${latestUserText} ${assistantText.toLowerCase()}`;
  const vesselName = shipment.candidateVessels[0]?.name ?? shipment.bookingReference;
  const suggestions: string[] = [];

  const add = (question: string) => {
    if (!suggestions.includes(question) && suggestions.length < 2) {
      suggestions.push(question);
    }
  };

  // Feature-discovery suggestions — surface things the user hasn't tried
  if (!/watch|monitor|alert|notify|standby/i.test(combined)) {
    add(`Watch ${vesselName} and alert me if ETA slips`);
  }
  if (!/compare|which shipment|both/i.test(combined) && messages.filter((m) => m.role === "user").length >= 2) {
    add("Compare this with my other active shipment");
  }
  if (!/demurrage|free days|storage|clearance/i.test(combined) && /eta|arrival|delay|late/i.test(combined)) {
    add("Could demurrage become a risk here?");
  }
  if (/where|position|location|track|map/i.test(combined) && !/trend|speed|graph|history/i.test(combined)) {
    add("Show speed trend over recent observations");
  }
  if (/anchor|anchorage/i.test(combined)) {
    add("How long has the vessel been at anchor?");
  }
  if (/eta|arrive|arrival|when/i.test(combined) && !/what could|risk|cause/i.test(combined)) {
    add("What could cause the ETA to slip further?");
  }
  if (/evidence|source|reliable|confidence/i.test(combined)) {
    add("Which data source has the freshest position?");
  }
  if (!/timeline|changed since|history|event/i.test(combined)) {
    add("Show what changed since yesterday");
  }

  add(`Is ${vesselName} running on schedule?`);
  add("What's the biggest risk right now?");

  // Add sparkle icon to each suggestion
  return suggestions.slice(0, 2).map((s) => `✨ ${s}`);
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 px-1 py-1">
      {[0, 200, 400].map((delay) => (
        <span key={delay} className="h-2 w-2 rounded-full bg-apple-blue" style={{ animation: `pulse-dot 1.5s ease-in-out ${delay}ms infinite` }} />
      ))}
    </div>
  );
}

function describeTool(toolName?: string): { label: string; emoji: string } {
  switch (toolName) {
    case "get_shipment_status":
      return { emoji: "📦", label: "Checking shipment status and ETA confidence" };
    case "get_shipment_history":
      return { emoji: "📜", label: "Reviewing voyage history" };
    case "get_vessel_position":
      return { emoji: "📍", label: "Pulling latest vessel position" };
    case "search_knowledge_base":
      return { emoji: "📚", label: "Searching internal evidence" };
    case "get_eta_revisions":
      return { emoji: "⏱️", label: "Checking carrier ETA revisions" };
    case "get_port_context":
      return { emoji: "🏗️", label: "Reviewing port context" };
    case "list_shipments":
      return { emoji: "📋", label: "Loading available shipments" };
    case "web_search":
      return { emoji: "🌐", label: "Searching the web for context" };
    case "search_supporting_context":
      return { emoji: "🌐", label: "Combining internal and web context" };
    default:
      return { emoji: "⚙️", label: "Running backend tool" };
  }
}

function formatSourceLabel(value: string) {
  return value.replace(/_/g, " ");
}

function formatWebDate(date?: string | null) {
  if (!date) {
    return null;
  }

  return new Date(date).toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function getWebFreshnessLabel(result: WebSearchResult) {
  return result.updated ? `updated ${formatWebDate(result.updated)}` : result.published ? `published ${formatWebDate(result.published)}` : "date unknown";
}

function formatCurrency(value: number, currency: "NGN" | "USD") {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatShortDateTime(value?: string | null) {
  if (!value) {
    return null;
  }

  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getFreshnessTone(shipment: Shipment): "fresh" | "aging" | "stale" {
  if (shipment.freshnessWarning) {
    return "stale";
  }

  const freshness = shipment.etaConfidence?.freshness?.toLowerCase() ?? "";
  if (freshness.includes("stale") || freshness.includes("old")) {
    return "stale";
  }
  if (freshness.includes("aging") || freshness.includes("moderate") || freshness.includes("warn")) {
    return "aging";
  }
  return "fresh";
}

function buildMessageContext(messages: ChatMessage[], assistantText: string) {
  const latestUserText = [...messages].reverse().find((message) => message.role === "user")?.content ?? "";
  const lower = `${latestUserText} ${assistantText}`.toLowerCase();
  return { latestUserText, lower };
}

function shouldShowStandbyCard(messages: ChatMessage[], assistantText: string) {
  const { lower } = buildMessageContext(messages, assistantText);
  return /(watch|watcher|monitor|notify|alert|let me know|standby|when .*?(arriv|anchor|eta|delay|demurrage|fresh))/i.test(lower);
}

function shouldShowDemurrageCard(messages: ChatMessage[], assistantText: string) {
  const { lower } = buildMessageContext(messages, assistantText);
  return /(demurrage|free days|storage|clearance|exposure|projected cost|avoid this)/i.test(lower);
}

function shouldShowShipmentComparison(messages: ChatMessage[], assistantText: string) {
  const { lower } = buildMessageContext(messages, assistantText);
  return /(compare|comparison|which shipment|which one|rank|needs attention|priority across shipments|active shipments)/i.test(lower);
}

function shouldShowVoyageTimelineCard(messages: ChatMessage[], assistantText: string, richComponents: RichComponent[], shipment: Shipment) {
  if (shipment.events.length === 0 && shipment.historyPoints.length === 0) {
    return false;
  }

  const { lower } = buildMessageContext(messages, assistantText);
  const asksForTimeline = /(timeline|history|what changed|changed|since yesterday|voyage|arrival|depart|anchor|anchorage|event)/i.test(lower);
  const trackingNarrative = richComponents.includes("graph") && /(trend|history|pattern|slip|change)/i.test(lower);
  return asksForTimeline || trackingNarrative;
}

function buildStandbySuggestion(messages: ChatMessage[], assistantText: string, shipment: Shipment) {
  const { lower } = buildMessageContext(messages, assistantText);

  if (lower.includes("demurrage")) {
    return {
      label: "Demurrage risk rises",
      conditionText: `Alert me when demurrage exposure increases for ${shipment.bookingReference}.`,
    };
  }
  if (lower.includes("anchor")) {
    return {
      label: "Vessel anchors",
      conditionText: `Alert me when ${shipment.bookingReference} reaches anchorage.`,
    };
  }
  if (lower.includes("eta")) {
    return {
      label: "ETA shifts",
      conditionText: `Alert me when the ETA changes materially for ${shipment.bookingReference}.`,
    };
  }
  return {
    label: "Lagos arrival detected",
    conditionText: `Alert me when ${shipment.bookingReference} arrives Lagos.`,
  };
}

function usesWebSearch(toolName?: string) {
  return toolName === "web_search" || toolName === "search_supporting_context";
}

function splitEventEmoji(label: string): { emoji: string; text: string } {
  const chars = [...label];
  const first = chars[0] ?? "";
  const cp = first.codePointAt(0) ?? 0;
  if (cp > 0x2000) {
    return { emoji: first, text: label.slice(first.length).trimStart() };
  }
  return { emoji: "·", text: label };
}

function AgentStatusPill({
  status,
  elapsedSeconds,
  eventLog,
  hasText,
}: {
  status: StreamStatus | null;
  elapsedSeconds: number;
  eventLog: StreamEventItem[];
  hasText: boolean;
}) {
  const ROW_H = 30;
  const VISIBLE = 3;
  const translateY = Math.max(0, eventLog.length - VISIBLE) * ROW_H;
  const visibleRows = Math.min(eventLog.length, VISIBLE);

  const stageLabel = hasText
    ? "Writing response"
    : status?.title?.replace(/^[\u{1F300}-\u{1FFFF}\u{2600}-\u{27FF}]\s*/u, "").trim() ?? "Working";

  return (
    <div className="mb-3 flex justify-start">
      <div style={{ maxWidth: "75%" }}>
        {/* Stage summary + dots */}
        <div className="mb-2 flex items-center gap-2">
          <TypingIndicator />
          <span
            key={stageLabel}
            className="text-[13px] text-apple-secondary"
            style={{ animation: "fade-in 0.3s ease both" }}
          >
            {stageLabel}
          </span>
          {elapsedSeconds > 1 && (
            <span className="text-[11px] tabular-nums text-apple-secondary/40">{elapsedSeconds}s</span>
          )}
        </div>

        {/* Sliding 3-item event window */}
        {eventLog.length > 0 && (
          <div
            className="overflow-hidden"
            style={{
              height: `${visibleRows * ROW_H}px`,
              transition: "height 0.3s ease",
            }}
          >
            <div
              style={{
                transform: `translateY(-${translateY}px)`,
                transition: "transform 0.35s cubic-bezier(0.4, 0, 0.2, 1)",
              }}
            >
              {eventLog.map((event, i) => {
                const { emoji, text } = splitEventEmoji(event.label);
                const isLast = i === eventLog.length - 1;
                return (
                  <div
                    key={event.id}
                    className="flex items-start gap-2.5"
                    style={{ height: `${ROW_H}px`, animation: "fade-in 0.25s ease both" }}
                  >
                    {/* Icon + vertical line to next item */}
                    <div className="relative flex shrink-0 flex-col items-center" style={{ width: 16 }}>
                      <span className="mt-0.5 text-[13px] leading-none">{emoji}</span>
                      {!isLast && (
                        <div
                          className="absolute w-px bg-apple-divider"
                          style={{ top: 20, height: ROW_H - 18 }}
                        />
                      )}
                    </div>
                    {/* Label text */}
                    <span className="truncate pt-[3px] text-[13px] leading-tight text-apple-secondary">
                      {text}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function detectIntentKind(text: string) {
  const lower = text.toLowerCase();
  if (/(where|position|location|track|tracking|map|heading|speed|where is it now|where is my shipment now)/i.test(lower)) {
    return "shipment_location";
  }
  if (/(eta|arrival|arrive|when will|when does it get|delay)/i.test(lower)) {
    return "eta_check";
  }
  if (/(evidence|confidence|source|reliable|why|what changed)/i.test(lower)) {
    return "evidence_review";
  }
  if (/(demurrage|free days|storage|clearance|projected cost)/i.test(lower)) {
    return "demurrage_check";
  }
  if (/(compare|which shipment|needs attention)/i.test(lower)) {
    return "shipment_comparison";
  }
  return "general_follow_up";
}

function buildRepeatedIntentState(
  text: string,
  shipmentId: string,
  previousIntent: RecentIntentSnapshot | null,
): Record<string, unknown> {
  const intentKind = detectIntentKind(text);
  if (!previousIntent || previousIntent.shipmentId !== shipmentId || previousIntent.intentKind !== intentKind) {
    return {};
  }

  const ageSeconds = Math.round((Date.now() - previousIntent.recordedAt) / 1000);
  if (ageSeconds > 120) {
    return {};
  }

  if (intentKind === "general_follow_up") {
    return {};
  }

  return {
    recent_intent_kind: intentKind,
    recent_intent_repeated: true,
    recent_intent_age_seconds: ageSeconds,
  };
}

function shouldShowTrackingTable(messages: ChatMessage[], assistantText: string) {
  const { lower } = buildMessageContext(messages, assistantText);
  return /(status|summary|eta|arrival|speed|heading|origin|destination|location|position|vessel|tracking)/i.test(lower);
}

function shouldShowTrackingProgress(messages: ChatMessage[], assistantText: string) {
  const { lower } = buildMessageContext(messages, assistantText);
  return /(eta|arrival|arrive|days left|how long|schedule|slip|delay|progress|on track|late)/i.test(lower);
}

function ShipmentDetailCard({
  shipment,
  showTable = true,
  showProgress = true,
}: {
  shipment: Shipment;
  showTable?: boolean;
  showProgress?: boolean;
}) {
  const vessel = shipment.candidateVessels[0];
  const position = shipment.currentPosition;
  const progress = getProgressPercent(shipment.declaredDepartureDate, shipment.declaredEtaDate);
  const days = getDaysRemaining(shipment.declaredEtaDate);
  const isActiveTransit = shipment.status === "in_transit" || shipment.status === "open";
  const hasTimeline = Boolean(shipment.declaredDepartureDate && shipment.declaredEtaDate);

  return (
    <div className="apple-card p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium text-apple-secondary">#{shipment.bookingReference}</span>
        <span className="apple-badge-blue">{formatStatus(shipment.status)}</span>
      </div>
      <p className="mt-1 text-sm font-semibold text-apple-text">{vessel?.name ?? "Vessel not assigned"}</p>
      {showTable ? (
        <div className="mt-4 overflow-hidden rounded-[16px] border border-apple-divider bg-apple-surface/70">
          <table className="w-full text-left text-xs">
            <tbody>
              {[
                ["Vessel", vessel?.name ?? "TBD"],
                ["Location", position ? `${position.latitude.toFixed(2)}°, ${position.longitude.toFixed(2)}°` : "N/A"],
                ["Origin", shipment.loadPort ?? "TBD"],
                ["Destination", shipment.dischargePort ?? "TBD"],
                ["ETA", shipment.declaredEtaDate ? new Date(shipment.declaredEtaDate).toLocaleDateString() : "TBD"],
                ["Speed", position?.speedKnots ? `${position.speedKnots} kn` : "N/A"],
              ].map(([label, value], index) => (
                <tr key={label} className={index < 5 ? "border-b border-apple-divider" : undefined}>
                  <th className="w-[38%] px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-apple-secondary">
                    {label}
                  </th>
                  <td className="px-4 py-3 font-medium text-apple-text">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mt-4 flex flex-wrap gap-2">
          <span className="rounded-full bg-apple-surface px-3 py-1 text-[11px] font-medium text-apple-secondary">
            {position ? `${position.latitude.toFixed(2)}°, ${position.longitude.toFixed(2)}°` : shipment.dischargePort ?? "Location pending"}
          </span>
          <span className="rounded-full bg-apple-surface px-3 py-1 text-[11px] font-medium text-apple-secondary">
            ETA {shipment.declaredEtaDate ? new Date(shipment.declaredEtaDate).toLocaleDateString() : "TBD"}
          </span>
          {position?.speedKnots != null && (
            <span className="rounded-full bg-apple-surface px-3 py-1 text-[11px] font-medium text-apple-secondary">
              {position.speedKnots} kn
            </span>
          )}
        </div>
      )}
      {showProgress && isActiveTransit && hasTimeline && (
        <div className="mt-4">
          <div className="h-1 rounded-full bg-apple-divider">
            <div className="h-full rounded-full bg-apple-blue transition-all" style={{ width: `${progress}%` }} />
          </div>
          <p className="mt-1.5 text-right text-xs font-medium text-apple-blue">{progress}% • {days} days left</p>
        </div>
      )}
      {shipment.freshnessWarning && <p className="mt-4 text-xs text-apple-red">{shipment.freshnessWarning}</p>}
    </div>
  );
}
function TrackingCompositeCard({
  shipment,
  showTable = true,
  showProgress = true,
}: {
  shipment: Shipment;
  showTable?: boolean;
  showProgress?: boolean;
}) {
  return (
    <div className="space-y-3">
      <ShipmentDetailCard shipment={shipment} showTable={showTable} showProgress={showProgress} />
      {shipment.currentPosition && (
        <div className="apple-card overflow-hidden p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.1em] text-apple-secondary">Map</p>
            <span className="text-[11px] text-apple-secondary">
              {shipment.currentPosition.latitude.toFixed(2)}°, {shipment.currentPosition.longitude.toFixed(2)}°
            </span>
          </div>
          <ShipmentMap shipment={shipment} compact compactHeightClass="h-[320px]" />
        </div>
      )}
    </div>
  );
}

function SourceBadgeStrip({
  webSearchResults,
  knowledgeSnippets,
}: {
  webSearchResults: WebSearchResult[];
  knowledgeSnippets: KnowledgeSnippet[];
}) {
  const [showMobileDetails, setShowMobileDetails] = useState(false);
  const sourceItems = useMemo(() => {
    const seen = new Set<string>();
    const items: { key: string; label: string; detail: string }[] = [];

    for (const result of webSearchResults) {
      const key = `web-${result.sourceId}`;
      if (seen.has(key)) continue;
      seen.add(key);
      items.push({ key, label: result.source, detail: getWebFreshnessLabel(result) });
    }

    for (const snippet of knowledgeSnippets) {
      const key = `kb-${snippet.sourceName}-${snippet.sourceType}`;
      if (seen.has(key)) continue;
      seen.add(key);
      items.push({ key, label: snippet.sourceName, detail: snippet.sourceType.replace(/_/g, " ") });
    }

    return items.slice(0, 6);
  }, [knowledgeSnippets, webSearchResults]);

  if (sourceItems.length === 0) {
    return null;
  }

  return (
    <div className="rounded-[16px] border border-apple-divider/80 bg-white/75 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-apple-secondary">Sources</span>
          <div className="flex -space-x-2">
            {sourceItems.map((source) => (
              <div
                key={source.key}
                title={source.label}
                className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-[#eef6ff] text-xs font-semibold text-apple-blue shadow-sm"
              >
                {source.label.charAt(0).toUpperCase()}
              </div>
            ))}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setShowMobileDetails((current) => !current)}
          className="rounded-full bg-apple-surface px-3 py-1 text-[11px] font-medium text-apple-secondary xl:hidden"
        >
          {showMobileDetails ? "Hide" : "View"}
        </button>
      </div>
      {(showMobileDetails || typeof window === "undefined") && (
        <div className="mt-3 space-y-2 xl:hidden">
          {sourceItems.map((source) => (
            <div key={source.key} className="rounded-[12px] bg-apple-surface px-3 py-2">
              <p className="text-sm font-medium text-apple-text">{source.label}</p>
              <p className="text-xs text-apple-secondary">{source.detail}</p>
            </div>
          ))}
        </div>
      )}
      <p className="mt-2 hidden text-[11px] text-apple-secondary xl:block">
        Detailed source context stays on the right rail on desktop.
      </p>
    </div>
  );
}

function ResponseMetaBar({
  shipment,
  webSearchResults,
}: {
  shipment: Shipment;
  webSearchResults: WebSearchResult[];
}) {
  const observedAt = shipment.currentPosition?.observedAt
    ? new Date(shipment.currentPosition.observedAt).toLocaleString()
    : null;
  const freshnessTone = getFreshnessTone(shipment);
  const freshnessClass = freshnessTone === "fresh"
    ? "bg-[#eaf3de] text-[#27500a]"
    : freshnessTone === "aging"
      ? "bg-[#faeeda] text-[#633806]"
      : "bg-[#fcebeb] text-[#791f1f]";
  const confidenceLabel = shipment.etaConfidence?.score != null
    ? shipment.etaConfidence.score.toFixed(2)
    : null;

  return (
    <div className="rounded-[16px] border border-apple-divider/80 bg-white/80 p-3">
      <div className="flex flex-wrap gap-2">
        <span className={`rounded-full px-3 py-1 text-[11px] font-medium uppercase tracking-[0.12em] ${freshnessClass}`}>
          {freshnessTone} context
          {shipment.etaConfidence?.freshness ? ` · ${shipment.etaConfidence.freshness}` : ""}
        </span>
        <span className="rounded-full bg-apple-surface px-3 py-1 text-[11px] font-medium uppercase tracking-[0.12em] text-apple-secondary">
          source: {shipment.currentPosition?.source ?? "declared_only"}
        </span>
        {confidenceLabel && (
          <span className={`rounded-full px-3 py-1 text-[11px] font-medium ${freshnessClass}`}>
            ETA confidence {confidenceLabel}
          </span>
        )}
        {webSearchResults.length > 0 && (
          <span className="rounded-full bg-[#eef6ff] px-3 py-1 text-[11px] font-medium text-apple-blue">
            {webSearchResults.length} cited web source{webSearchResults.length === 1 ? "" : "s"}
          </span>
        )}
        {shipment.evidenceCount != null && (
          <span className="rounded-full bg-apple-surface px-3 py-1 text-[11px] font-medium text-apple-secondary">
            {shipment.evidenceCount} evidence item{shipment.evidenceCount === 1 ? "" : "s"}
          </span>
        )}
        {shipment.freshnessWarning && (
          <span className="rounded-full bg-apple-red/10 px-3 py-1 text-[11px] font-medium text-apple-red">
            stale-data warning
          </span>
        )}
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-apple-divider">
        <div
          className={`h-full rounded-full transition-all ${
            freshnessTone === "fresh" ? "bg-[#639922]" : freshnessTone === "aging" ? "bg-[#ba7517]" : "bg-[#e24b4a]"
          }`}
          style={{ width: `${Math.max(15, Math.round((shipment.etaConfidence?.score ?? 0.35) * 100))}%` }}
        />
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-apple-secondary">
        {observedAt && <span>Observed {observedAt}</span>}
        {shipment.currentPosition?.destination && <span>Destination {shipment.currentPosition.destination}</span>}
        {webSearchResults[0]?.updated && <span>Latest web update {formatWebDate(webSearchResults[0].updated)}</span>}
      </div>
    </div>
  );
}

function EvidenceCard({ shipment }: { shipment: Shipment }) {
  const evidenceItems = shipment.evidence.slice(0, 3);

  if (evidenceItems.length === 0) {
    return (
      <div className="apple-card p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-apple-secondary">Evidence</p>
        <p className="mt-3 text-sm leading-relaxed text-apple-secondary">
          No supporting evidence snippets are available for this shipment yet.
        </p>
      </div>
    );
  }

  return (
    <div className="apple-card p-5">
      <p className="text-xs font-semibold uppercase tracking-[0.1em] text-apple-secondary">Evidence</p>
      <div className="mt-3 space-y-3">
        {evidenceItems.map((evidence) => (
          <div key={`${evidence.source}-${evidence.capturedAt}`} className="rounded-[14px] bg-apple-surface p-3">
            <div className="flex items-center justify-between gap-3 text-[11px] uppercase tracking-[0.1em] text-apple-secondary">
              <span>{evidence.source}</span>
              <span>{new Date(evidence.capturedAt).toLocaleDateString()}</span>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-apple-text">{evidence.claim}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function TrendGraphCard({ shipment }: { shipment: Shipment }) {
  const points = shipment.historyPoints
    .filter((point) => point.speedKnots != null)
    .slice(-8);

  if (points.length < 2) {
    return (
      <div className="apple-card p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-apple-secondary">Trend Graph</p>
        <p className="mt-3 text-sm leading-relaxed text-apple-secondary">
          Not enough history points are available yet to render a useful movement trend.
        </p>
      </div>
    );
  }

  const values = points.map((point) => point.speedKnots ?? 0);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const chartWidth = 400;
  const chartHeight = 100;
  const leftPad = 8;
  const rightPad = 4;
  const topPad = 10;
  const bottomPad = 14;
  const usableWidth = chartWidth - leftPad - rightPad;
  const usableHeight = chartHeight - topPad - bottomPad;
  const coordinates = points.map((point, index) => {
    const x = leftPad + (index / (points.length - 1)) * usableWidth;
    const value = point.speedKnots ?? min;
    const y = topPad + (1 - ((value - min) / range)) * usableHeight;
    return `${x},${y}`;
  }).join(" ");
  const areaCoordinates = `${leftPad},${chartHeight - bottomPad} ${coordinates} ${leftPad + usableWidth},${chartHeight - bottomPad}`;
  const latest = points[points.length - 1];
  const earliest = points[0];
  const gridValues = [max, min + range * 0.5, min];

  return (
    <div className="apple-card p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-apple-secondary">Trend Graph</p>
        <span className="text-[11px] text-apple-secondary">Speed over recent observations</span>
      </div>
      <div className="mt-4 rounded-[16px] border border-apple-divider bg-white p-3">
        <div style={{ aspectRatio: "4/1" }} className="w-full">
        <svg viewBox="0 0 400 100" className="h-full w-full overflow-visible" preserveAspectRatio="none" aria-label="Shipment trend graph">
          {gridValues.map((gridValue, index) => {
            const y = topPad + (1 - ((gridValue - min) / range)) * usableHeight;
            return (
              <g key={`${gridValue}-${index}`}>
                <line x1={leftPad} x2={leftPad + usableWidth} y1={y} y2={y} stroke="#e5e5ea" strokeWidth="0.4" strokeDasharray="4 6" />
                <text x={0} y={y + 1.5} fontSize="5.5" fill="#6e6e73">
                  {gridValue.toFixed(1)}
                </text>
              </g>
            );
          })}
          <polygon
            points={areaCoordinates}
            fill="rgba(0, 113, 227, 0.08)"
          />
          <polyline
            fill="none"
            stroke="#0071e3"
            strokeWidth="0.9"
            strokeLinejoin="round"
            strokeLinecap="round"
            points={coordinates}
          />
          {points.map((point, index) => {
            const x = leftPad + (index / (points.length - 1)) * usableWidth;
            const value = point.speedKnots ?? min;
            const y = topPad + (1 - ((value - min) / range)) * usableHeight;
            return (
              <g key={`${point.observedAt}-${index}`}>
                <circle cx={x} cy={y} r="2.2" fill="#ffffff" stroke="#0071e3" strokeWidth="0.7" />
                <line x1={x} x2={x} y1={chartHeight - bottomPad + 1.5} y2={chartHeight - bottomPad + 4.5} stroke="#c7c7cc" strokeWidth="0.4" />
              </g>
            );
          })}
          <line x1={leftPad} x2={leftPad + usableWidth} y1={chartHeight - bottomPad} y2={chartHeight - bottomPad} stroke="#d1d1d6" strokeWidth="0.4" />
        </svg>
        </div>
        <div className="mt-2 flex items-center justify-between text-[11px] text-apple-secondary">
          <span>{new Date(earliest.observedAt).toLocaleDateString([], { month: "short", day: "numeric" })}</span>
          <span>{new Date(latest.observedAt).toLocaleDateString([], { month: "short", day: "numeric" })}</span>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
        <div className="rounded-[14px] bg-apple-surface p-3">
          <p className="text-apple-secondary">Latest speed</p>
          <p className="mt-1 font-semibold text-apple-text">{latest.speedKnots?.toFixed(1)} kn</p>
        </div>
        <div className="rounded-[14px] bg-apple-surface p-3">
          <p className="text-apple-secondary">Observed range</p>
          <p className="mt-1 font-semibold text-apple-text">{min.toFixed(1)} - {max.toFixed(1)} kn</p>
        </div>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-apple-secondary">
        From {new Date(earliest.observedAt).toLocaleString()} to {new Date(latest.observedAt).toLocaleString()} via recent vessel history.
      </p>
    </div>
  );
}

function InlineStandbyCreatorCard({
  shipment,
  messages,
  assistantText,
  onCreateStandbyAgent,
}: {
  shipment: Shipment;
  messages: ChatMessage[];
  assistantText: string;
  onCreateStandbyAgent?: (draft: StandbyAgentDraft) => void | Promise<void>;
}) {
  const suggestion = buildStandbySuggestion(messages, assistantText, shipment);
  const [conditionText, setConditionText] = useState(suggestion.conditionText);
  const [action, setAction] = useState<StandbyAction>("notify");
  const [intervalSeconds, setIntervalSeconds] = useState(3600);
  const [isCreating, setIsCreating] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const parsed = useMemo(() => parseStandbyCondition(conditionText), [conditionText]);

  useEffect(() => {
    setConditionText(suggestion.conditionText);
  }, [suggestion.conditionText]);

  const handleCreate = useCallback(async () => {
    if (!onCreateStandbyAgent || !conditionText.trim() || isCreating) {
      return;
    }

    setIsCreating(true);
    setStatusText("Creating watcher...");
    try {
      await onCreateStandbyAgent(createStandbyAgentDraft(conditionText, action, intervalSeconds, shipment.shipmentId));
      setStatusText("Watcher active");
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : "Watcher creation failed");
    } finally {
      setIsCreating(false);
    }
  }, [action, conditionText, intervalSeconds, isCreating, onCreateStandbyAgent, shipment.shipmentId]);

  return (
    <div className="apple-card p-5">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
        <p className="text-sm font-semibold text-apple-text">Watch this shipment</p>
        <span className="ml-auto text-xs text-apple-secondary">{shipment.bookingReference}</span>
      </div>
      <p className="mt-2 text-sm text-apple-secondary">Create a standby watcher from this conversation without leaving chat.</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="text-xs font-semibold uppercase tracking-[0.08em] text-apple-secondary">
          Action
          <select
            value={action}
            onChange={(event) => setAction(event.target.value as StandbyAction)}
            className="apple-input mt-2 w-full px-3 py-2.5 text-sm font-medium text-apple-text"
          >
            <option value="notify">In-app notification</option>
            <option value="email">Email update</option>
            <option value="digest">Digest item</option>
            <option value="report">Report draft</option>
            <option value="spreadsheet">Spreadsheet output</option>
            <option value="document">Document draft</option>
          </select>
        </label>
        <label className="text-xs font-semibold uppercase tracking-[0.08em] text-apple-secondary">
          Check every
          <select
            value={intervalSeconds}
            onChange={(event) => setIntervalSeconds(Number(event.target.value))}
            className="apple-input mt-2 w-full px-3 py-2.5 text-sm font-medium text-apple-text"
          >
            <option value={60}>1 minute</option>
            <option value={300}>5 minutes</option>
            <option value={3600}>1 hour</option>
            <option value={21600}>6 hours</option>
            <option value={86400}>24 hours</option>
          </select>
        </label>
      </div>
      <textarea
        value={conditionText}
        onChange={(event) => setConditionText(event.target.value)}
        rows={3}
        className="apple-input mt-4 w-full px-4 py-3 text-sm text-apple-text"
      />
      <div className="mt-3 rounded-[16px] border border-[#d8e8ff] bg-[#f7fbff] p-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-apple-blue">Watcher preview</p>
        <div className="mt-2 space-y-1.5 text-sm text-apple-text">
          <p><span className="text-apple-secondary">Shipment:</span> {shipment.bookingReference}</p>
          <p><span className="text-apple-secondary">Trigger:</span> {parsed.trigger}</p>
          <p><span className="text-apple-secondary">Outcome:</span> {describeStandbyAction(action)}</p>
          <p><span className="text-apple-secondary">Cadence:</span> {formatStandbyInterval(intervalSeconds)}</p>
        </div>
        <p className="mt-2 text-xs text-apple-secondary">{parsed.summary}</p>
      </div>
      <div className="mt-4 flex items-center gap-2">
        <button
          type="button"
          onClick={() => void handleCreate()}
          disabled={!onCreateStandbyAgent || isCreating || !conditionText.trim()}
          className="rounded-full bg-apple-blue px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {isCreating ? "Creating..." : "Create watcher"}
        </button>
        <span className="text-xs text-apple-secondary">{statusText ?? `Suggested from the latest answer: ${suggestion.label}.`}</span>
      </div>
    </div>
  );
}

function DemurrageRiskCard({
  shipment,
  exposure,
  onAsk,
}: {
  shipment: Shipment;
  exposure: DemurrageExposure;
  onAsk: (text: string) => void;
}) {
  const riskClass = exposure.riskLevel === "high"
    ? "border-[#a32d2d] bg-[#fcebeb] text-[#791f1f]"
    : exposure.riskLevel === "medium"
      ? "border-[#854f0b] bg-[#faeeda] text-[#633806]"
      : "border-[#3b6d11] bg-[#eaf3de] text-[#27500a]";
  const progressWidth = Math.min(100, Math.max(18, Math.round((exposure.projectedCostNgn / 2_000_000) * 100)));

  return (
    <div className="apple-card overflow-hidden p-0">
      <div className="flex items-center justify-between border-b border-apple-divider px-5 py-4">
        <div>
          <p className="text-sm font-semibold text-apple-text">Demurrage exposure</p>
          <p className="mt-1 text-xs text-apple-secondary">{exposure.terminalLocode ?? shipment.dischargePort ?? "Terminal"} · {shipment.bookingReference}</p>
        </div>
        <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] ${riskClass}`}>
          {exposure.riskLevel} risk
        </span>
      </div>
      <div className="p-5">
        <div className="overflow-hidden rounded-[16px] border border-apple-divider bg-apple-surface/70">
          <table className="w-full text-left text-xs">
            <tbody>
              {[
                ["Free days left", `${exposure.freeDays}`],
                ["Daily rate", formatCurrency(exposure.dailyRateNgn, "NGN")],
                ["Projected cost", formatCurrency(exposure.projectedCostNgn, "NGN")],
                ["Clearance risk days", `${exposure.clearanceRiskDays}`],
              ].map(([label, value], index) => (
                <tr key={label} className={index < 3 ? "border-b border-apple-divider" : undefined}>
                  <th className="w-[42%] px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-apple-secondary">
                    {label}
                  </th>
                  <td className="px-4 py-3 font-medium text-apple-text">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-xs text-apple-secondary">Risk accumulation based on clearance and congestion assumptions</p>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-apple-divider">
          <div
            className={`h-full rounded-full ${exposure.riskLevel === "high" ? "bg-[#e24b4a]" : exposure.riskLevel === "medium" ? "bg-[#ba7517]" : "bg-[#639922]"}`}
            style={{ width: `${progressWidth}%` }}
          />
        </div>
        <div className="mt-4 rounded-[14px] border border-amber-200 bg-amber-50 p-3">
          <p className="text-xs leading-relaxed text-amber-900">
            Free period ends <strong>{formatWebDate(exposure.freeDaysEnd) ?? "soon"}</strong>. Clearance risk adds {exposure.clearanceRiskDays} extra day{exposure.clearanceRiskDays === 1 ? "" : "s"}.
          </p>
          {exposure.notes[0] && <p className="mt-2 text-xs leading-relaxed text-amber-900">{exposure.notes[0]}</p>}
        </div>
        <div className="mt-4 flex gap-2">
          <button type="button" onClick={() => onAsk(`What do I need to do to avoid demurrage on ${shipment.bookingReference}?`)} className="apple-btn-secondary flex-1 px-4 py-2 text-xs">
            How to avoid this
          </button>
          <button type="button" onClick={() => onAsk(`Show me the clearance checklist for ${shipment.bookingReference}`)} className="apple-btn-secondary flex-1 px-4 py-2 text-xs">
            Clearance checklist
          </button>
        </div>
      </div>
    </div>
  );
}

function VoyageTimelineCard({
  shipment,
  onAsk,
}: {
  shipment: Shipment;
  onAsk: (text: string) => void;
}) {
  const derivedPositionEvent = shipment.currentPosition
    ? {
        key: `position-${shipment.currentPosition.observedAt}`,
        title: "Last known position",
        meta: `${formatShortDateTime(shipment.currentPosition.observedAt) ?? "recent"} · ${shipment.currentPosition.speedKnots ?? "N/A"} kn · ${shipment.currentPosition.latitude.toFixed(2)}°, ${shipment.currentPosition.longitude.toFixed(2)}°`,
        source: `${shipment.currentPosition.source}${shipment.freshnessWarning ? " · aging" : ""}`,
        tone: shipment.freshnessWarning ? "aging" : "fresh",
      }
    : null;

  const eventRows = shipment.events.slice(-4).map((event) => ({
    key: `${event.eventType}-${event.eventAt}`,
    title: formatStatus(event.eventType),
    meta: formatShortDateTime(event.eventAt) ?? "Unknown time",
    source: event.source ?? "shipment event",
    tone: "fresh" as const,
  }));

  const rows = [...eventRows, ...(derivedPositionEvent ? [derivedPositionEvent] : [])].slice(-5);
  if (rows.length === 0) {
    return null;
  }

  return (
    <div className="apple-card p-5">
      <div className="flex items-center justify-between gap-3 border-b border-apple-divider pb-3">
        <span className="text-sm font-semibold text-apple-text">Voyage events</span>
        <span className="text-xs text-apple-secondary">{shipment.candidateVessels[0]?.name ?? shipment.bookingReference}</span>
      </div>
      <div className="mt-2 space-y-1">
        {rows.map((row, index) => (
          <div key={row.key} className="flex gap-3 py-3">
            <div className="flex flex-col items-center">
              <span className={`h-2.5 w-2.5 rounded-full ${row.tone === "aging" ? "bg-[#ba7517]" : "bg-[#639922]"}`} />
              {index < rows.length - 1 && <span className="mt-1 h-full w-px bg-apple-divider" />}
            </div>
            <div className="min-w-0">
              <p className={`text-sm font-medium ${row.tone === "aging" ? "text-[#ba7517]" : "text-apple-text"}`}>{row.title}</p>
              <p className="mt-1 text-xs text-apple-secondary">{row.meta}</p>
              <span className="mt-2 inline-block rounded-full bg-apple-surface px-2.5 py-1 text-[11px] text-apple-secondary">{row.source}</span>
            </div>
          </div>
        ))}
      </div>
      <button type="button" onClick={() => onAsk(`What changed on ${shipment.bookingReference} since yesterday?`)} className="apple-btn-secondary mt-3 w-full px-4 py-2 text-xs">
        What changed since yesterday?
      </button>
    </div>
  );
}

function StandbyAlertCard({
  notification,
  onAsk,
}: {
  notification: AgentNotification;
  onAsk: (text: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-[18px] border border-[#185fa5] bg-white">
      <div className="flex items-center gap-2 bg-[#e6f1fb] px-4 py-3">
        <ShieldCheck className="h-4 w-4 text-[#185fa5]" strokeWidth={1.5} />
        <span className="text-sm font-semibold text-[#0c447c]">Standby agent fired</span>
        <span className="ml-auto text-[11px] text-[#185fa5]">
          {notification.createdAt ? formatShortDateTime(notification.createdAt) : "just now"}
        </span>
      </div>
      <div className="p-4">
        <p className="text-sm font-semibold text-apple-text">{notification.title}</p>
        <p className="mt-2 text-sm leading-relaxed text-apple-secondary">{notification.detail}</p>
        <div className="mt-4 flex gap-2">
          <button type="button" onClick={() => onAsk("What should I do now?")} className="rounded-full bg-apple-blue px-4 py-2 text-xs font-medium text-white">
            What do I do now?
          </button>
          <button type="button" onClick={() => onAsk("Show demurrage exposure for this shipment")} className="apple-btn-secondary px-4 py-2 text-xs">
            Check demurrage
          </button>
        </div>
      </div>
    </div>
  );
}

function TrackingMapCard({ shipment }: { shipment: Shipment }) {
  if (!shipment.currentPosition) {
    return null;
  }

  return (
    <div className="apple-card overflow-hidden p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-apple-secondary">Map</p>
        <span className="text-[11px] text-apple-secondary">
          {shipment.currentPosition.latitude.toFixed(2)}°, {shipment.currentPosition.longitude.toFixed(2)}°
        </span>
      </div>
      <ShipmentMap shipment={shipment} compact compactHeightClass="h-[320px]" />
    </div>
  );
}

function AgentOutputPreviewCard({
  output,
  onOpen,
}: {
  output: AgentOutput;
  onOpen?: (outputId: string) => void;
}) {
  const truncatedContent = output.content.length > 240
    ? `${output.content.slice(0, 240).trimEnd()}...`
    : output.content;

  return (
    <div className="apple-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-apple-text">{output.title}</p>
          <p className="mt-2 text-sm leading-relaxed text-apple-secondary">{output.previewText}</p>
        </div>
        <span className="apple-badge-blue">{output.outputType}</span>
      </div>
      <div className="mt-4 rounded-[14px] bg-apple-surface p-4">
        <p className="line-clamp-4 whitespace-pre-wrap text-sm leading-relaxed text-apple-text">{truncatedContent}</p>
      </div>
      <div className="mt-4 flex items-center justify-between gap-3">
        <span className="text-[11px] text-apple-secondary/70">
          {output.createdAt ? new Date(output.createdAt).toLocaleString() : "Pending"}
        </span>
        {onOpen && (
          <button
            type="button"
            onClick={() => onOpen(output.id)}
            className="rounded-full border border-apple-divider bg-white px-3 py-1.5 text-xs font-medium text-apple-blue transition-colors hover:bg-[#eef6ff]"
          >
            Open full output
          </button>
        )}
      </div>
    </div>
  );
}

function ShipmentComparisonStrip({
  comparison,
  shipments,
  selectedShipmentId,
  onSelectShipment,
  onAsk,
}: {
  comparison: ShipmentComparison;
  shipments: Shipment[];
  selectedShipmentId: string;
  onSelectShipment?: (shipmentId: string) => void;
  onAsk: (text: string) => void;
}) {
  if (comparison.shipments.length < 2) {
    return null;
  }

  const comparedItems = comparison.shipments.slice(0, 2);
  const fullShipments = comparedItems
    .map((item) => shipments.find((s) => s.shipmentId === item.shipmentId))
    .filter((s): s is Shipment => Boolean(s));

  return (
    <div className="space-y-3 rounded-[20px] border border-apple-divider bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-apple-secondary">Shipment comparison</p>

      {/* Comparison table */}
      <div className="overflow-hidden rounded-[14px] border border-apple-divider">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-apple-divider bg-apple-surface/70">
              <th className="w-[30%] px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-apple-secondary">Field</th>
              {comparedItems.map((item) => (
                <th key={item.shipmentId} className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-apple-text">
                  #{item.bookingReference}
                  {item.shipmentId === selectedShipmentId && (
                    <span className="ml-2 rounded-full bg-apple-blue px-1.5 py-0.5 text-[10px] font-medium text-white">active</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-apple-divider">
              <td className="px-4 py-3 font-medium text-apple-secondary">Risk</td>
              {comparedItems.map((item) => (
                <td key={item.shipmentId} className="px-4 py-3">
                  <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${item.riskScore >= 0.7 ? "bg-[#fcebeb] text-[#791f1f]" : item.riskScore >= 0.4 ? "bg-[#faeeda] text-[#633806]" : "bg-[#eaf3de] text-[#27500a]"}`}>
                    {item.riskScore >= 0.7 ? "High" : item.riskScore >= 0.4 ? "Medium" : "Low"}
                  </span>
                </td>
              ))}
            </tr>
            <tr className="border-b border-apple-divider">
              <td className="px-4 py-3 font-medium text-apple-secondary">Status</td>
              {comparedItems.map((item) => (
                <td key={item.shipmentId} className="px-4 py-3 font-medium text-apple-text">{formatStatus(item.status)}</td>
              ))}
            </tr>
            {fullShipments.length === 2 && (
              <tr className="border-b border-apple-divider">
                <td className="px-4 py-3 font-medium text-apple-secondary">ETA</td>
                {fullShipments.map((s) => (
                  <td key={s.shipmentId} className="px-4 py-3 font-medium text-apple-text">
                    {s.declaredEtaDate ? new Date(s.declaredEtaDate).toLocaleDateString() : "TBD"}
                  </td>
                ))}
              </tr>
            )}
            {fullShipments.length === 2 && (
              <tr className="border-b border-apple-divider">
                <td className="px-4 py-3 font-medium text-apple-secondary">Vessel</td>
                {fullShipments.map((s) => (
                  <td key={s.shipmentId} className="px-4 py-3 text-apple-text">{s.candidateVessels[0]?.name ?? "TBD"}</td>
                ))}
              </tr>
            )}
            <tr className="border-b border-apple-divider">
              <td className="px-4 py-3 font-medium text-apple-secondary">Freshness</td>
              {comparedItems.map((item) => (
                <td key={item.shipmentId} className="px-4 py-3 text-apple-secondary">{item.freshness}</td>
              ))}
            </tr>
            <tr>
              <td className="px-4 py-3 font-medium text-apple-secondary">Summary</td>
              {comparedItems.map((item) => (
                <td key={item.shipmentId} className="px-4 py-3 text-apple-secondary">{item.summary}</td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      {/* Recommendation */}
      {comparison.recommendation && (
        <div className="rounded-[14px] bg-[#eef6ff] px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-apple-blue">Recommendation</p>
          <p className="mt-1 text-xs leading-relaxed text-apple-blue">{comparison.recommendation}</p>
        </div>
      )}

      {/* Map with both shipments */}
      {fullShipments.length >= 2 && fullShipments.some((s) => s.currentPosition) && (
        <div className="overflow-hidden rounded-[14px] border border-apple-divider">
          <p className="border-b border-apple-divider px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-apple-secondary">Live positions</p>
          <ShipmentMap
            shipment={fullShipments[0]}
            shipments={fullShipments}
            selectedShipmentId={selectedShipmentId}
            compact
            compactHeightClass="h-[280px]"
          />
        </div>
      )}

      {/* Switch buttons */}
      <div className="grid gap-2 md:grid-cols-2">
        {comparedItems.map((item) => {
          const isActive = item.shipmentId === selectedShipmentId;
          return (
            <button
              key={item.shipmentId}
              type="button"
              onClick={() => onSelectShipment?.(item.shipmentId)}
              className={`rounded-[14px] border px-4 py-2.5 text-left text-xs font-medium transition-colors ${isActive ? "border-apple-blue bg-[#eef6ff] text-apple-blue" : "border-apple-divider bg-apple-surface text-apple-text hover:bg-white"}`}
            >
              {isActive ? `Viewing #${item.bookingReference}` : `Switch to #${item.bookingReference}`}
            </button>
          );
        })}
      </div>

      <button type="button" onClick={() => onAsk("Compare my two active shipments and tell me which needs more attention")} className="apple-btn-secondary w-full px-4 py-2 text-xs">
        Ask for full comparison
      </button>
    </div>
  );
}

function VoiceComposer({
  isVoiceMode,
  isRecording,
  transcriptPreview,
  onToggleVoiceMode,
}: {
  isVoiceMode: boolean;
  isRecording: boolean;
  transcriptPreview: string;
  onToggleVoiceMode: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={onToggleVoiceMode}
          className={`flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-medium transition-colors ${isVoiceMode ? "border-[#185fa5] bg-[#e6f1fb] text-[#0c447c]" : "border-apple-divider bg-apple-surface text-apple-secondary"}`}
        >
          <Mic className="h-3.5 w-3.5" strokeWidth={1.5} />
          {isVoiceMode ? "Voice mode on" : "Voice mode off"}
        </button>
        <span className="text-[11px] text-apple-secondary">Brief spoken responses</span>
      </div>
      {(isVoiceMode || isRecording) && (
        <div className="rounded-[16px] border border-apple-divider bg-white px-4 py-3">
          <div className="flex h-10 items-end gap-1">
            {[8, 18, 10, 24, 14, 28, 9].map((base, index) => (
              <span
                key={`${base}-${index}`}
                className={`w-1 rounded-full bg-apple-blue transition-all duration-200 ${isRecording ? "opacity-100" : "opacity-60"}`}
                style={{ height: `${isRecording ? base + ((index % 2 === 0) ? 10 : 0) : 6}px` }}
              />
            ))}
          </div>
          <p className="mt-3 min-h-5 text-sm italic text-apple-secondary">{transcriptPreview || "Tap the mic and speak naturally."}</p>
        </div>
      )}
    </div>
  );
}

function WebSearchResultsCard({
  results,
  notice,
}: {
  results: WebSearchResult[];
  notice: string | null;
}) {
  if (results.length === 0 && !notice) {
    return null;
  }

  return (
    <div className="apple-card p-5">
      <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
        <Radar className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
        Web sources
      </div>
      {notice && (
        <div className="mt-3 rounded-[14px] border border-amber-200 bg-amber-50 px-3 py-2">
          <p className="text-xs leading-relaxed text-amber-900">{notice}</p>
        </div>
      )}
      <div className="mt-3 space-y-3">
        {results.map((result) => (
          <a
            key={`${result.sourceId}-${result.id}`}
            href={result.url}
            target="_blank"
            rel="noreferrer"
            className="block rounded-[14px] bg-apple-surface p-3 transition-colors hover:bg-[#eef6ff]"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <span className="text-xs font-semibold uppercase tracking-[0.1em] text-apple-blue">{result.source}</span>
                <p className="mt-1 text-[11px] uppercase tracking-[0.12em] text-apple-secondary">
                  cited via {formatSourceLabel(result.sourceClass)}
                </p>
              </div>
              <div className="flex flex-wrap justify-end gap-1.5">
                <span className="rounded-full bg-white px-2.5 py-1 text-[11px] uppercase tracking-[0.08em] text-apple-secondary">
                  {formatSourceLabel(result.trustLevel)}
                </span>
                <span className="rounded-full bg-white px-2.5 py-1 text-[11px] text-apple-secondary">
                  {getWebFreshnessLabel(result)}
                </span>
              </div>
            </div>
            <p className="mt-2 text-sm font-medium text-apple-text">{result.title}</p>
            <p className="mt-1 text-sm leading-relaxed text-apple-secondary">{result.snippet || result.summary}</p>
            <p className="mt-2 text-[11px] leading-relaxed text-apple-secondary">
              Why this matched: {result.matchReason}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {result.tags.slice(0, 3).map((tag) => (
                <span key={`${result.id}-${tag}`} className="rounded-full bg-white px-2.5 py-1 text-[11px] text-apple-secondary">
                  #{tag}
                </span>
              ))}
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}

function AgentContextRail({
  shipment,
  sourceReadiness,
  knowledgeSnippets,
  webSearchResults,
  webSearchPlanSources,
  preferredTab,
}: {
  shipment: Shipment;
  sourceReadiness: SourceReadiness[];
  knowledgeSnippets: KnowledgeSnippet[];
  webSearchResults: WebSearchResult[];
  webSearchPlanSources: WebSearchSourcePlan[];
  preferredTab: RailTab;
}) {
  const [activeTab, setActiveTab] = useState<RailTab>(preferredTab);
  const topSources = sourceReadiness.slice(0, 4);
  const topEvidence = shipment.evidence.slice(0, 2);

  useEffect(() => {
    setActiveTab(preferredTab);
  }, [preferredTab]);

  return (
    <aside className="hidden w-[320px] shrink-0 border-l border-apple-divider/70 bg-white xl:flex xl:flex-col">
      <div className="overflow-y-auto p-5 scrollbar-thin">
        <div className="rounded-[20px] border border-apple-divider bg-white p-5 shadow-apple">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-apple-secondary">
            <Radar className="h-3.5 w-3.5 text-apple-blue" strokeWidth={1.5} />
            Live Agent Context
          </div>
          <h4 className="mt-3 text-lg font-semibold text-apple-text">{shipment.bookingReference}</h4>
          <p className="mt-2 text-sm text-apple-secondary">
            {shipment.currentPosition
              ? `Latest position from ${shipment.currentPosition.source} at ${new Date(shipment.currentPosition.observedAt).toLocaleString()}.`
              : "No live position overlay yet. The agent is relying on declared shipment context."}
          </p>
        </div>

        <div className="mt-4 rounded-[18px] border border-apple-divider bg-white p-2">
          <div className="grid grid-cols-3 gap-2">
            {([
              ["confidence", "Confidence"],
              ["evidence", "Evidence"],
              ["sources", "Sources"],
            ] as [RailTab, string][]).map(([tab, label]) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`rounded-[12px] px-3 py-2 text-xs font-medium transition-colors ${
                  activeTab === tab ? "bg-apple-blue text-white" : "bg-apple-surface text-apple-secondary"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {activeTab === "confidence" && (
          <div className="mt-4 rounded-[18px] border border-apple-divider bg-white p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
              <ShieldCheck className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
              Confidence
            </div>
            <p className="mt-3 text-2xl font-semibold text-apple-text">
              {shipment.etaConfidence ? `${Math.round(shipment.etaConfidence.score * 100)}%` : "N/A"}
            </p>
            <p className="mt-1 text-xs uppercase tracking-[0.12em] text-apple-secondary">
              {shipment.etaConfidence?.freshness ?? "unknown"}
            </p>
            <p className="mt-3 text-sm leading-relaxed text-apple-secondary">
              {shipment.etaConfidence?.explanation ?? shipment.freshnessWarning ?? "Waiting for stronger corroboration."}
            </p>
          </div>
        )}

        {activeTab === "evidence" && (
          <div className="mt-4 rounded-[18px] border border-apple-divider bg-white p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
              <BookOpenText className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
              Retrieved Context
            </div>
            <div className="mt-3 space-y-3">
              {knowledgeSnippets.length === 0 && topEvidence.length === 0 && (
                <p className="text-sm text-apple-secondary">Ask a question to load relevant evidence and operational context.</p>
              )}
              {knowledgeSnippets.map((snippet) => (
                <div key={`${snippet.sourceName}-${snippet.sourceType}-${snippet.content.slice(0, 24)}`} className="rounded-[14px] bg-apple-surface p-3">
                  <div className="flex items-center justify-between gap-3 text-[11px] uppercase tracking-[0.12em] text-apple-secondary">
                    <span>{snippet.sourceName}</span>
                    <span>{Math.round(snippet.relevanceScore * 10) / 10}</span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-apple-text">{snippet.content}</p>
                </div>
              ))}
              {knowledgeSnippets.length === 0 && topEvidence.map((evidence) => (
                <div key={`${evidence.source}-${evidence.capturedAt}`} className="rounded-[14px] bg-apple-surface p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.1em] text-apple-secondary">{evidence.source}</p>
                  <p className="mt-1 text-sm text-apple-text">{evidence.claim}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "sources" && (
          <div className="mt-4 rounded-[18px] border border-apple-divider bg-white p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
              <AlertTriangle className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
              Source Readiness
            </div>
            <div className="mt-3 space-y-3">
              {webSearchPlanSources.map((source) => (
                <div key={source.id} className="rounded-[14px] border border-[#d8e8ff] bg-[#f7fbff] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-apple-text">{source.name}</span>
                    <span className={source.status === "done" ? "apple-badge-green" : "apple-badge-blue"}>
                      {source.status === "done" ? "searched" : "queued"}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-apple-secondary">
                    {source.matchReason ?? `${formatSourceLabel(source.sourceClass)} source`}
                  </p>
                </div>
              ))}
              {webSearchResults.map((result) => (
                <a
                  key={`${result.sourceId}-${result.id}`}
                  href={result.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-[14px] bg-[#eef6ff] p-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-apple-text">{result.source}</span>
                    <span className="text-[11px] uppercase tracking-[0.12em] text-apple-blue">{getWebFreshnessLabel(result)}</span>
                  </div>
                  <p className="mt-1 text-xs text-apple-secondary">{result.title}</p>
                </a>
              ))}
              {topSources.map((source) => (
                <div key={source.source} className="rounded-[14px] bg-apple-surface p-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium capitalize text-apple-text">{source.source.replace(/_/g, " ")}</span>
                    <span className={`text-[11px] uppercase tracking-[0.12em] ${source.configured ? "text-apple-blue" : "text-apple-secondary"}`}>
                      {source.mode}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-apple-secondary">{source.detail}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

function VoicePlaybackBubble({ text }: { text: string }) {
  const [playing, setPlaying] = useState(false);

  const toggle = useCallback(() => {
    if (!("speechSynthesis" in window)) {
      return;
    }

    if (playing) {
      window.speechSynthesis.cancel();
      setPlaying(false);
      return;
    }

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.onend = () => setPlaying(false);
    window.speechSynthesis.speak(utterance);
    setPlaying(true);
  }, [playing, text]);

  useEffect(() => {
    return () => {
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  return (
    <button onClick={toggle} className="flex items-center gap-2.5 rounded-pill apple-card px-4 py-2.5 transition-all duration-150 active:scale-[0.97]">
      <div className={`flex h-8 w-8 items-center justify-center rounded-full ${playing ? "bg-apple-red/10" : "bg-apple-blue/10"}`}>
        {playing ? <Pause className="h-4 w-4 text-apple-red" strokeWidth={1.5} /> : <Play className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />}
      </div>
      <div className="flex flex-col items-start">
        <span className="text-xs font-medium text-apple-text">{playing ? "Playing..." : "Voice Response"}</span>
        <span className="text-[11px] text-apple-secondary">Tap to {playing ? "stop" : "listen"}</span>
      </div>
    </button>
  );
}

function renderInlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    if (token.startsWith("**") && token.endsWith("**")) {
      nodes.push(<strong key={`${keyPrefix}-bold-${match.index}`}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("*") && token.endsWith("*")) {
      nodes.push(<em key={`${keyPrefix}-italic-${match.index}`}>{token.slice(1, -1)}</em>);
    } else {
      nodes.push(token);
    }

    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}

function renderMessageContent(text: string, showCaret = false): ReactNode {
  const lines = text.split("\n");

  return (
    <>
      {lines.map((line, index) => (
        <Fragment key={`line-${index}`}>
          {renderInlineMarkdown(line, `line-${index}`)}
          {index < lines.length - 1 && <br />}
        </Fragment>
      ))}
      {showCaret && <span className="stream-caret" />}
    </>
  );
}

function parseRichDirective(text: string): { cleanText: string; components: RichComponent[] } {
  const directiveMatch = text.match(/<ui>([\s\S]*?)<\/ui>/i);
  if (!directiveMatch) {
    return { cleanText: text, components: [] };
  }

  const cleanText = text.replace(directiveMatch[0], "").trim();

  try {
    const parsed = JSON.parse(directiveMatch[1]) as { components?: string[] };
    const components = (parsed.components ?? []).filter((item): item is RichComponent =>
      item === "map" || item === "tracking" || item === "evidence" || item === "graph",
    );
    return { cleanText, components };
  } catch {
    return { cleanText, components: [] };
  }
}

function normalizeResponseMode(value: unknown): ResponseMode {
  return value === "concise" || value === "verbose" ? value : "balanced";
}

function selectVisibleRichComponents(
  components: RichComponent[],
  shipment: Shipment,
  messages: ChatMessage[],
  assistantText: string,
  responseMode: ResponseMode,
): RichComponent[] {
  const { lower } = buildMessageContext(messages, assistantText);
  const requested: RichComponent[] = [];

  if ((components.includes("tracking") || components.includes("map")) && /(where|position|location|track|map|eta|arrival|heading|speed|vessel)/i.test(lower)) {
    requested.push("tracking");
  }

  if (components.includes("evidence") && /(evidence|why|confidence|reliable|source|trust|proof)/i.test(lower)) {
    requested.push("evidence");
  }

  if (components.includes("graph") && shipment.historyPoints.length > 1) {
    requested.push("graph");
  }

  const visible = [...new Set(requested)];
  if (responseMode === "concise") {
    return visible.includes("tracking") ? ["tracking"] : visible.slice(0, 1);
  }
  if (responseMode === "verbose") {
    return visible;
  }
  return visible.slice(0, 2);
}

function toUserFacingKnowledge(snippets: KnowledgeSnippet[]) {
  return snippets.filter((snippet) => snippet.sourceType === "shipment_evidence" || snippet.sourceType === "voyage_event");
}

function getVoiceCapabilities() {
  const recognition = typeof window !== "undefined"
    && ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);
  const synthesis = typeof window !== "undefined" && "speechSynthesis" in window;

  return {
    recognition,
    synthesis,
    inputLabel: recognition ? "Voice input ready" : "Voice input unavailable",
    playbackLabel: synthesis ? "Speech playback ready" : "Speech playback unavailable",
  };
}

function buildAgentPrompt(shipment: Shipment, userText: string, voiceMode = false, responseMode: ResponseMode = "balanced") {
  const vesselName = shipment.candidateVessels[0]?.name ?? shipment.bookingReference;
  const lengthGuidance = voiceMode
    ? "Reply in 2-3 sentences maximum. Be direct and easy to speak aloud."
    : responseMode === "concise"
      ? "Reply in 2-3 sentences maximum. Be direct, cut everything non-essential."
      : responseMode === "verbose"
        ? "Provide a thorough explanation with full context, reasoning, and all relevant details. Use structured prose."
        : "Reply in 3-6 sentences. Be focused and useful without padding.";
  return [
    `Focus on shipment ${shipment.shipmentId}. The vessel is named "${vesselName}".`,
    `Booking reference: ${shipment.bookingReference}. Carrier: ${shipment.carrier}.`,
    `Always refer to this shipment by the vessel name "${vesselName}", not by shipment ID.`,
    `If the user asks an ambiguous question, prioritize this shipment before discussing others.`,
    `Do not compare against other shipments unless the user explicitly asks to compare.`,
    `When comparing shipments, only highlight the key differences — the UI will show the full table. Do not repeat every detail for each shipment.`,
    `If rich UI would help, append a final hidden directive like <ui>{"components":["map","tracking"]}</ui> using only map, tracking, evidence, and graph.`,
    `Include graph in the directive when the user asks for a trend, history, speed over time, a graph/chart, or a summary of tracking updates.`,
    lengthGuidance,
    `Do not mention the ui directive in the visible answer text.`,
    `User request: ${userText}`,
  ].join(" ");
}

export default function ChatPanel({
  shipment,
  shipments = [],
  notifications = [],
  agentOutputs = [],
  threadId,
  messages,
  onMessagesChange,
  onCreateStandbyAgent,
  onSelectShipment,
  onOpenOutput,
  pendingPrompt = null,
  onPendingPromptConsumed,
}: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isVoiceMode, setIsVoiceMode] = useState(false);
  const [voiceTranscriptPreview, setVoiceTranscriptPreview] = useState("");
  const [isStandbyMode, setIsStandbyMode] = useState(false);
  const [standbyAction, setStandbyAction] = useState<StandbyAction>("notify");
  const [standbyIntervalSeconds, setStandbyIntervalSeconds] = useState(3600);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [sourceReadiness, setSourceReadiness] = useState<SourceReadiness[]>([]);
  const [knowledgeSnippets, setKnowledgeSnippets] = useState<KnowledgeSnippet[]>([]);
  const [webSearchResults, setWebSearchResults] = useState<WebSearchResult[]>([]);
  const [webSearchNotice, setWebSearchNotice] = useState<string | null>(null);
  const [webSearchPlanSources, setWebSearchPlanSources] = useState<WebSearchSourcePlan[]>([]);
  const [demurrageExposure, setDemurrageExposure] = useState<DemurrageExposure | null>(null);
  const [shipmentComparison, setShipmentComparison] = useState<ShipmentComparison | null>(null);
  const [streamStatus, setStreamStatus] = useState<StreamStatus | null>(null);
  const [responseMode, setResponseMode] = useState<ResponseMode>("balanced");
  const [toolProgress, setToolProgress] = useState<ToolProgressItem[]>([]);
  const [streamEvents, setStreamEvents] = useState<StreamEventItem[]>([]);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [hasStreamingText, setHasStreamingText] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const latestMessagesRef = useRef<ChatMessage[]>(messages);
  const streamTargetRef = useRef("");
  const streamDisplayedRef = useRef("");
  const streamMessageIdRef = useRef<string | null>(null);
  const recentIntentRef = useRef<RecentIntentSnapshot | null>(null);
  const currentRepeatedIntentRef = useRef<string | null>(null);
  const webSearchUsedRef = useRef(false);
  const knowledgeSearchUsedRef = useRef(false);
  const currentPromptRef = useRef("");
  const turnFetchKeysRef = useRef<Set<string>>(new Set());
  const revealTimerRef = useRef<number | null>(null);
  const outputById = useMemo(() => new Map(agentOutputs.map((output) => [output.id, output])), [agentOutputs]);

  useEffect(() => {
    latestMessagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSubmitting]);

  useEffect(() => {
    if (!isSubmitting || !streamStatus) {
      setElapsedSeconds(0);
      return;
    }

    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - streamStatus.startedAt) / 1000));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [isSubmitting, streamStatus]);

  useEffect(() => {
    return () => {
      if (revealTimerRef.current !== null) {
        window.clearInterval(revealTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!pendingPrompt || isSubmitting) {
      return;
    }
    void sendMessage(pendingPrompt).finally(() => {
      onPendingPromptConsumed?.();
    });
  }, [isSubmitting, onPendingPromptConsumed, pendingPrompt]);

  const quickQuestions = useMemo(
    () => [
      "Where is this shipment now?",
      "How reliable is the current ETA?",
      "Which vessel is carrying this shipment?",
      "Summarize the latest tracking update.",
    ],
    [],
  );

  const latestAssistantMessage = useMemo(
    () => [...messages].reverse().find((message) => message.role === "assistant" && message.content),
    [messages],
  );
  const latestAssistantParsed = useMemo(
    () => parseRichDirective(latestAssistantMessage?.content ?? ""),
    [latestAssistantMessage?.content],
  );
  const latestAssistantComponents = latestAssistantMessage?.richComponents ?? latestAssistantParsed.components;
  const showStandbyCreator = latestAssistantMessage
    ? shouldShowStandbyCard(messages, latestAssistantParsed.cleanText)
    : false;
  const showDemurrageCard = latestAssistantMessage
    ? shouldShowDemurrageCard(messages, latestAssistantParsed.cleanText)
    : false;
  const showVoyageTimeline = latestAssistantMessage
    ? shouldShowVoyageTimelineCard(messages, latestAssistantParsed.cleanText, latestAssistantComponents, shipment)
    : false;
  const showShipmentComparison = latestAssistantMessage
    ? shouldShowShipmentComparison(messages, latestAssistantParsed.cleanText)
    : false;
  const latestShipmentNotification = useMemo(
    () =>
      notifications.find((item) =>
        item.detail.toLowerCase().includes(shipment.bookingReference.toLowerCase())
        || item.title.toLowerCase().includes(shipment.bookingReference.toLowerCase()),
      ) ?? null,
    [notifications, shipment.bookingReference],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadAgentContext() {
      try {
        const readiness = await getSourceReadiness();
        if (!cancelled) {
          setSourceReadiness(readiness);
        }
      } catch {
        if (!cancelled) {
          setSourceReadiness([]);
        }
      }
    }

    void loadAgentContext();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    if (!latestAssistantMessage || !showDemurrageCard) {
      setDemurrageExposure(null);
      return;
    }

    void getDemurrageExposure(shipment.shipmentId)
      .then((payload) => {
        if (!cancelled) {
          setDemurrageExposure(payload);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDemurrageExposure(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [latestAssistantMessage?.id, shipment.shipmentId, showDemurrageCard]);

  useEffect(() => {
    let cancelled = false;

    if (shipments.length < 2 || !showShipmentComparison) {
      setShipmentComparison(null);
      return;
    }

    void compareShipments(shipments.map((item) => item.shipmentId))
      .then((payload) => {
        if (!cancelled) {
          setShipmentComparison(payload);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setShipmentComparison(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [shipments, showShipmentComparison]);

  const commitMessages = useCallback((nextMessages: ChatMessage[]) => {
    latestMessagesRef.current = nextMessages;
    onMessagesChange(nextMessages);
  }, [onMessagesChange]);

  const patchMessage = useCallback((messageId: string, patch: Partial<ChatMessage>) => {
    commitMessages(
      latestMessagesRef.current.map((message) =>
        message.id === messageId ? { ...message, ...patch } : message,
      ),
    );
  }, [commitMessages]);

  const updateStreamingAssistant = useCallback((content: string, messageId: string) => {
    const parsed = parseRichDirective(content);
    patchMessage(messageId, {
      content,
      richComponents: parsed.components,
      showMap: parsed.components.includes("map") && !!shipment.currentPosition,
    });
  }, [patchMessage, shipment.currentPosition]);

  const ensureRevealLoop = useCallback(() => {
    if (revealTimerRef.current !== null) return;

    revealTimerRef.current = window.setInterval(() => {
      const messageId = streamMessageIdRef.current;
      const target = streamTargetRef.current;
      const displayed = streamDisplayedRef.current;

      if (!messageId || displayed.length >= target.length) {
        if (displayed.length >= target.length && revealTimerRef.current !== null) {
          window.clearInterval(revealTimerRef.current);
          revealTimerRef.current = null;
        }
        return;
      }

      const remaining = target.length - displayed.length;
      const step = Math.min(Math.max(remaining > 180 ? 22 : remaining > 90 ? 12 : 4, Math.ceil(remaining / 10)), 28);
      const nextContent = target.slice(0, displayed.length + step);
      streamDisplayedRef.current = nextContent;
      updateStreamingAssistant(nextContent, messageId);
    }, 45);
  }, [updateStreamingAssistant]);

  const flushStreamContent = useCallback(async (forceFull = false) => {
    const messageId = streamMessageIdRef.current;
    if (!messageId) return;

    if (forceFull) {
      streamDisplayedRef.current = streamTargetRef.current;
      updateStreamingAssistant(streamDisplayedRef.current, messageId);
      return;
    }

    while (streamDisplayedRef.current.length < streamTargetRef.current.length) {
      await new Promise((resolve) => window.setTimeout(resolve, 20));
    }
  }, [updateStreamingAssistant]);

  const handleAgentEvent = useCallback((event: AgentStreamEvent) => {
    if (event.type === "RUN_STARTED") {
      const repeatedIntentKind = currentRepeatedIntentRef.current;
      setStreamEvents([{
        id: crypto.randomUUID(),
        label: repeatedIntentKind
          ? `♻️ Reusing recent ${repeatedIntentKind.replace(/_/g, " ")} workflow`
          : "🧠 Reading request and loading context",
        kind: "thinking",
      }]);
      setStreamStatus({
        title: repeatedIntentKind ? "Reusing recent shipment path" : "Dockie agent is working",
        detail: repeatedIntentKind
          ? "Skipping a fresh planning pass and jumping back into the relevant shipment tools."
          : "Reading the request, loading context, and deciding which checks to run first.",
        startedAt: Date.now(),
      });
      return;
    }

    if (event.type === "TOOL_CALL_START") {
      const { emoji, label } = describeTool(event.toolCallName);
      const fullLabel = `${emoji} ${label}`;
      if (event.toolCallName === "search_knowledge_base" || event.toolCallName === "search_supporting_context") {
        knowledgeSearchUsedRef.current = true;
      }
      if (usesWebSearch(event.toolCallName)) {
        webSearchUsedRef.current = true;
        const promptForPlan = currentPromptRef.current.trim();
        const planKey = `web-plan:${promptForPlan.toLowerCase()}`;
        if (promptForPlan && !turnFetchKeysRef.current.has(planKey)) {
          turnFetchKeysRef.current.add(planKey);
          void searchFakeWebPlan(promptForPlan)
            .then((payload) => {
              setWebSearchPlanSources(payload.candidateSources);
              setStreamEvents((current) => [
                ...current.slice(-5),
                { id: crypto.randomUUID(), label: `🌐 Planning checks across ${payload.candidateSources.length} remote sources`, kind: "source" },
              ]);
            })
            .catch(() => setWebSearchPlanSources([]));
        }
      }
      setStreamEvents((current) => [...current.slice(-5), { id: crypto.randomUUID(), label: fullLabel, kind: "tool" }]);
      setStreamStatus((current) => ({
        title: usesWebSearch(event.toolCallName) ? "🌐 Searching external sources" : "Running checks",
        detail: fullLabel,
        startedAt: current?.startedAt ?? Date.now(),
      }));
      setToolProgress((current) => {
        const toolId = event.toolCallId ?? crypto.randomUUID();
        const existing = current.find((item) => item.id === toolId);
        if (existing) {
          return current.map((item) => (item.id === toolId ? { ...item, label: fullLabel, status: "active" } : item));
        }
        return [...current, { id: toolId, label: fullLabel, status: "active" }];
      });
      return;
    }

    if (event.type === "TOOL_CALL_END" && event.toolCallId) {
      setStreamEvents((current) => [...current.slice(-5), { id: crypto.randomUUID(), label: "✅ Results received", kind: "thinking" }]);
      setToolProgress((current) =>
        current.map((item) => (item.id === event.toolCallId ? { ...item, status: "done" } : item)),
      );
      setStreamStatus((current) => ({
        title: "Grounding the response",
        detail: "✅ Results in — composing the answer.",
        startedAt: current?.startedAt ?? Date.now(),
      }));
      return;
    }

    if (event.type === "TEXT_MESSAGE_START") {
      setStreamEvents((current) => [...current.slice(-5), { id: crypto.randomUUID(), label: "✍️ Drafting response", kind: "writing" }]);
      setStreamStatus((current) => ({
        title: "Writing the response",
        detail: "✍️ Drafting response now that checks are complete.",
        startedAt: current?.startedAt ?? Date.now(),
      }));
      return;
    }

    if (event.type === "TEXT_MESSAGE_CONTENT") {
      setHasStreamingText(true);
      setStreamEvents((current) => current.length === 0 ? [{ id: crypto.randomUUID(), label: "✍️ Streaming response", kind: "writing" }] : current);
      setStreamStatus((current) => ({
        title: "✍️ Writing...",
        detail: "Streaming response.",
        startedAt: current?.startedAt ?? Date.now(),
      }));
      return;
    }

    if (event.type === "RUN_ERROR") {
      setStreamEvents((current) => [...current.slice(-5), { id: crypto.randomUUID(), label: "❌ Run could not complete", kind: "thinking" }]);
      setStreamStatus((current) => ({
        title: event.code === "MODEL_UNAVAILABLE" ? "Model temporarily busy" : "Run interrupted",
        detail: event.message ?? "The shipment agent could not complete this request.",
        startedAt: current?.startedAt ?? Date.now(),
      }));
    }
  }, []);

  const sendMessage = useCallback(async (text: string, isVoice = false) => {
    if (!text.trim() || isSubmitting) return;

    const timestamp = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      timestamp,
      isVoice,
      responseMode,
    };
    const assistantMessageId = crypto.randomUUID();
    const assistantPlaceholder: ChatMessage = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      timestamp,
      isVoice,
      responseMode,
    };

    streamTargetRef.current = "";
    streamDisplayedRef.current = "";
    streamMessageIdRef.current = assistantMessageId;
    const repeatedIntentState = buildRepeatedIntentState(text, shipment.shipmentId, recentIntentRef.current);
    setStreamStatus({
      title: repeatedIntentState.recent_intent_repeated ? "Reusing recent shipment path" : "Preparing request",
      detail: repeatedIntentState.recent_intent_repeated
        ? "This looks like a recent follow-up, so the agent will skip a full planning pass and go straight to the relevant tools."
        : "Sending your question to the grounded shipment agent.",
      startedAt: Date.now(),
    });
    currentPromptRef.current = text;
    webSearchUsedRef.current = false;
    knowledgeSearchUsedRef.current = false;
    setToolProgress([]);
    setElapsedSeconds(0);
    setHasStreamingText(false);
    turnFetchKeysRef.current = new Set();
    setStreamEvents([{ id: crypto.randomUUID(), label: "Preparing request payload", kind: "thinking" }]);
    setWebSearchResults([]);
    setWebSearchNotice(null);
    setWebSearchPlanSources([]);
    setDemurrageExposure(null);
    currentRepeatedIntentRef.current = typeof repeatedIntentState.recent_intent_kind === "string"
      ? repeatedIntentState.recent_intent_kind
      : null;
    commitMessages([...latestMessagesRef.current, userMessage, assistantPlaceholder]);
    setInput("");
    setIsSubmitting(true);
    setStreamingMessageId(assistantMessageId);

    try {
      await runAgentStream({
        threadId,
        prompt: buildAgentPrompt(shipment, text, isVoiceMode || isVoice, responseMode),
        state: {
          selected_shipment_id: shipment.shipmentId,
          response_mode: responseMode,
          ...repeatedIntentState,
        },
        onEvent: handleAgentEvent,
        onAssistantDelta: (delta, messageId) => {
          if (messageId && messageId !== streamMessageIdRef.current) {
            const previousId = streamMessageIdRef.current;
            streamMessageIdRef.current = messageId;
            setStreamingMessageId(messageId);
            if (previousId) {
              commitMessages(
                latestMessagesRef.current.map((message) =>
                  message.id === previousId ? { ...message, id: messageId } : message,
                ),
              );
            }
          }

          streamTargetRef.current += delta;
          ensureRevealLoop();
        },
      });

      await flushStreamContent();
      if (!knowledgeSearchUsedRef.current) {
        const knowledgeKey = `knowledge:${shipment.shipmentId}:${text.trim().toLowerCase()}`;
        if (!turnFetchKeysRef.current.has(knowledgeKey)) {
          turnFetchKeysRef.current.add(knowledgeKey);
          const snippets = await searchKnowledgeBase(text, shipment.shipmentId);
          const userFacingSnippets = toUserFacingKnowledge(snippets);
          setKnowledgeSnippets(userFacingSnippets);
          patchMessage(streamMessageIdRef.current ?? assistantMessageId, {
            knowledgeSnippets: userFacingSnippets,
          });
        }
      }
      if (webSearchUsedRef.current) {
        try {
          const webKey = `web:${text.trim().toLowerCase()}`;
          if (!turnFetchKeysRef.current.has(webKey)) {
            turnFetchKeysRef.current.add(webKey);
            const webPayload = await searchFakeWeb(text, 4);
            const nextNotice = webPayload.results.length === 0
              ? "Web search ran, but no matching remote source articles were retrieved for this question."
              : null;
            setWebSearchResults(webPayload.results);
            setWebSearchNotice(nextNotice);
            patchMessage(streamMessageIdRef.current ?? assistantMessageId, {
              webSearchResults: webPayload.results,
              webSearchNotice: nextNotice,
            });
            setWebSearchPlanSources((current) =>
              current.map((source) => ({
                ...source,
                status: webPayload.results.some((result) => result.sourceId === source.id) ? "done" : source.status,
              })),
            );
          }
        } catch (webError) {
          const errorText = webError instanceof Error ? webError.message : "Web search enrichment failed";
          setWebSearchResults([]);
          const nextNotice = `External web context was only partially available: ${errorText}. Internal evidence may still be complete.`;
          setWebSearchNotice(nextNotice);
          patchMessage(streamMessageIdRef.current ?? assistantMessageId, {
            webSearchResults: [],
            webSearchNotice: nextNotice,
          });
        }
      }
      recentIntentRef.current = {
        intentKind: detectIntentKind(text),
        shipmentId: shipment.shipmentId,
        recordedAt: Date.now(),
      };
    } catch (error) {
      const errorText = error instanceof Error ? error.message : "Agent request failed";
      const userFacingError = error instanceof AgentRunError && error.code === "MODEL_UNAVAILABLE"
        ? "The model is temporarily overloaded right now. Please try again in a moment."
        : errorText;
      streamTargetRef.current = "";
      streamDisplayedRef.current = "";
      commitMessages(
        latestMessagesRef.current.map((message) =>
          message.id === (streamMessageIdRef.current ?? assistantMessageId)
            ? { ...message, content: `I could not reach the shipment agent just now. ${userFacingError}` }
            : message,
        ),
      );
    } finally {
      if (streamTargetRef.current || streamDisplayedRef.current) {
        await flushStreamContent(true);
      }
      setIsSubmitting(false);
      setStreamingMessageId(null);
      setStreamStatus(null);
      setToolProgress([]);
      setStreamEvents([]);
      setHasStreamingText(false);
      webSearchUsedRef.current = false;
      knowledgeSearchUsedRef.current = false;
      turnFetchKeysRef.current.clear();
      currentPromptRef.current = "";
      currentRepeatedIntentRef.current = null;
      streamTargetRef.current = "";
      streamDisplayedRef.current = "";
      streamMessageIdRef.current = null;
    }
  }, [commitMessages, ensureRevealLoop, flushStreamContent, handleAgentEvent, isSubmitting, isVoiceMode, patchMessage, responseMode, shipment, threadId]);

  const handleSend = () => {
    if (isStandbyMode) {
      if (!input.trim() || !onCreateStandbyAgent) return;
      const conditionText = input.trim();
      const actionLabel =
        standbyAction === "log"
          ? "log entry"
          : standbyAction === "email"
            ? "email alert"
            : standbyAction === "digest"
              ? "digest item"
              : standbyAction === "report"
                ? "report draft"
                : standbyAction === "spreadsheet"
                  ? "spreadsheet output"
                  : standbyAction === "document"
                    ? "document draft"
                    : "in-app notification";
      const frequencyLabel =
        standbyIntervalSeconds < 60
          ? `${standbyIntervalSeconds}s`
          : standbyIntervalSeconds % 3600 === 0
            ? `${standbyIntervalSeconds / 3600}h`
            : `${standbyIntervalSeconds / 60}m`;
      void onCreateStandbyAgent(createStandbyAgentDraft(conditionText, standbyAction, standbyIntervalSeconds, shipment.shipmentId));
      commitMessages([
        ...latestMessagesRef.current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `Standby agent added for **${shipment.bookingReference}**. I will watch for "${conditionText}" and create a ${actionLabel} every ${frequencyLabel} when needed.`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          richComponents: [],
        },
      ]);
      setInput("");
      setIsStandbyMode(false);
      setStandbyAction("notify");
      setStandbyIntervalSeconds(3600);
      return;
    }
    void sendMessage(input);
  };

  const handleVoice = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      commitMessages([
        ...latestMessagesRef.current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "Voice input is unavailable in this browser. Chrome or Edge is recommended for microphone input.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          richComponents: [],
        },
      ]);
      return;
    }

    if (isRecording && recognitionRef.current) {
      recognitionRef.current.stop();
      setIsRecording(false);
      setVoiceTranscriptPreview("");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognitionRef.current = recognition;
    recognition.onstart = () => {
      setIsRecording(true);
      setVoiceTranscriptPreview("Listening...");
    };
    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setVoiceTranscriptPreview(`"${transcript}"`);
      void sendMessage(transcript, true);
    };
    recognition.onerror = () => {
      setIsRecording(false);
      setVoiceTranscriptPreview("");
    };
    recognition.onend = () => setIsRecording(false);
    recognition.start();
  };

  const vesselName = shipment.candidateVessels[0]?.name ?? shipment.bookingReference;
  const voiceCapabilities = getVoiceCapabilities();
  const preferredRailTab: RailTab = latestAssistantComponents.includes("evidence")
    ? "evidence"
    : latestAssistantComponents.includes("map") || latestAssistantComponents.includes("tracking")
      ? "confidence"
      : "sources";

  return (
    <div className="flex h-full bg-white">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-apple-divider/70 px-6 py-4">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <h3 className="text-lg font-semibold text-apple-text">{vesselName}</h3>
              <span className="apple-badge-blue">{formatStatus(shipment.status)}</span>
            </div>
            <div className="hidden items-center gap-2 lg:flex">
              <span className="rounded-full bg-[#eef6ff] px-3 py-1 text-[11px] font-medium uppercase tracking-[0.12em] text-apple-blue">
                {shipment.etaConfidence?.freshness ?? "unknown"}
              </span>
              <span className="rounded-full bg-apple-surface px-3 py-1 text-[11px] font-medium uppercase tracking-[0.12em] text-apple-secondary">
                {shipment.currentPosition?.source ?? "declared_only"}
              </span>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 scrollbar-thin">
          {messages.map((message, index) => {
            const isStreaming = streamingMessageId === message.id && isSubmitting && !message.content;
            const isStreamingMessage = streamingMessageId === message.id && isSubmitting;
            const parsedMessage = parseRichDirective(message.content);
            const richComponents = message.richComponents ?? parsedMessage.components;
            const messageResponseMode = normalizeResponseMode(message.responseMode);
            const visibleRichComponents = selectVisibleRichComponents(
              richComponents,
              shipment,
              messages,
              parsedMessage.cleanText,
              messageResponseMode,
            );
            const outputPreview = message.agentOutputId ? outputById.get(message.agentOutputId) ?? null : null;
            const messageKnowledgeSnippets = message.knowledgeSnippets ?? (index === messages.length - 1 ? knowledgeSnippets : []);
            const messageWebSearchResults = message.webSearchResults ?? (index === messages.length - 1 ? webSearchResults : []);
            const messageWebSearchNotice = message.webSearchNotice ?? (index === messages.length - 1 ? webSearchNotice : null);
            const hasMessageSources = messageKnowledgeSnippets.length > 0 || messageWebSearchResults.length > 0 || Boolean(messageWebSearchNotice);
            const showTable = messageResponseMode !== "concise" && shouldShowTrackingTable(messages, parsedMessage.cleanText);
            const showProgress = messageResponseMode === "verbose" || (messageResponseMode === "balanced" && shouldShowTrackingProgress(messages, parsedMessage.cleanText));
            const renderedContent = isStreaming
              ? renderMessageContent(streamStatus?.detail ?? "Following tools and composing the answer...")
              : renderMessageContent(parsedMessage.cleanText, isStreamingMessage && Boolean(parsedMessage.cleanText));
            return (
              <Fragment key={message.id}>
                {message.role === "assistant" && isStreamingMessage && (
                  <AgentStatusPill
                    status={streamStatus}
                    elapsedSeconds={elapsedSeconds}
                    eventLog={streamEvents}
                    hasText={hasStreamingText}
                  />
                )}
                <div className={`mb-5 flex animate-fade-in ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className="max-w-[75%] space-y-2">
                    {message.content && (
                      <div
                        className={`px-4 py-3 text-sm leading-relaxed ${message.role === "user" ? "rounded-[18px] rounded-br-[6px] bg-apple-blue text-white" : "apple-card rounded-[18px] rounded-bl-[6px] p-4 text-apple-text"}`}
                      >
                        {renderedContent}
                      </div>
                    )}
                    {message.role === "assistant" && message.content && !isStreamingMessage && (
                      <div className="space-y-3">
                        {index === messages.length - 1 && latestShipmentNotification && latestShipmentNotification.unread && (
                          <div className="animate-fade-in" style={{ animationDelay: "0ms" }}>
                            <StandbyAlertCard notification={latestShipmentNotification} onAsk={(text) => void sendMessage(text)} />
                          </div>
                        )}
                        {index === messages.length - 1 && showShipmentComparison && shipmentComparison && (
                          <div className="animate-fade-in" style={{ animationDelay: "100ms" }}>
                            <ShipmentComparisonStrip
                              comparison={shipmentComparison}
                              shipments={shipments}
                              selectedShipmentId={shipment.shipmentId}
                              onSelectShipment={onSelectShipment}
                              onAsk={(text) => void sendMessage(text)}
                            />
                          </div>
                        )}
                        {visibleRichComponents.length > 0 && (
                          <div className="space-y-3">
                            {visibleRichComponents.includes("tracking") && (
                              <div className="animate-fade-in" style={{ animationDelay: "180ms" }}>
                                {messageResponseMode === "concise"
                                  ? <TrackingMapCard shipment={shipment} />
                                  : <TrackingCompositeCard shipment={shipment} showTable={showTable} showProgress={showProgress} />}
                              </div>
                            )}
                            {messageResponseMode !== "concise" && visibleRichComponents.includes("evidence") && (
                              <div className="animate-fade-in" style={{ animationDelay: "280ms" }}>
                                <EvidenceCard shipment={shipment} />
                              </div>
                            )}
                            {messageResponseMode !== "concise" && visibleRichComponents.includes("graph") && (
                              <div className="animate-fade-in" style={{ animationDelay: "380ms" }}>
                                <TrendGraphCard shipment={shipment} />
                              </div>
                            )}
                          </div>
                        )}
                        {messageResponseMode !== "concise" && (index === messages.length - 1 || hasMessageSources) && (
                          <div className="animate-fade-in" style={{ animationDelay: "480ms" }}>
                            <ResponseMetaBar shipment={shipment} webSearchResults={messageWebSearchResults} />
                          </div>
                        )}
                        {messageResponseMode === "verbose" && (index === messages.length - 1 || hasMessageSources) && (
                          <div className="animate-fade-in" style={{ animationDelay: "580ms" }}>
                            <SourceBadgeStrip webSearchResults={messageWebSearchResults} knowledgeSnippets={messageKnowledgeSnippets} />
                          </div>
                        )}
                        {messageResponseMode !== "concise" && (messageWebSearchResults.length > 0 || messageWebSearchNotice) && (
                          <div className="animate-fade-in" style={{ animationDelay: "680ms" }}>
                            <WebSearchResultsCard results={messageWebSearchResults} notice={messageWebSearchNotice} />
                          </div>
                        )}
                        {index === messages.length - 1 && showStandbyCreator && (
                          <div className="animate-fade-in" style={{ animationDelay: "780ms" }}>
                            <InlineStandbyCreatorCard
                              shipment={shipment}
                              messages={messages}
                              assistantText={parsedMessage.cleanText}
                              onCreateStandbyAgent={onCreateStandbyAgent}
                            />
                          </div>
                        )}
                        {index === messages.length - 1 && demurrageExposure && (
                          <div className="animate-fade-in" style={{ animationDelay: "880ms" }}>
                            <DemurrageRiskCard shipment={shipment} exposure={demurrageExposure} onAsk={(text) => void sendMessage(text)} />
                          </div>
                        )}
                        {index === messages.length - 1 && showVoyageTimeline && (
                          <div className="animate-fade-in" style={{ animationDelay: "980ms" }}>
                            <VoyageTimelineCard shipment={shipment} onAsk={(text) => void sendMessage(text)} />
                          </div>
                        )}
                        {outputPreview && (
                          <AgentOutputPreviewCard output={outputPreview} onOpen={onOpenOutput} />
                        )}
                      </div>
                    )}
                    {message.role === "assistant" && message.content && index === messages.length - 1 && !isSubmitting && (
                      <div className="flex flex-wrap gap-2">
                        {buildFollowUpQuestions(shipment, messages, parsedMessage.cleanText).map((question) => (
                          <button
                            key={`${message.id}-${question}`}
                            onClick={() => void sendMessage(question)}
                            className="apple-btn-secondary px-4 py-2 text-xs transition-all duration-150 active:scale-[0.97]"
                          >
                            {question}
                          </button>
                        ))}
                      </div>
                    )}
                    {message.shipmentCard && <ShipmentDetailCard shipment={shipment} />}
                    {message.role === "assistant" && message.content && index === messages.length - 1 && (
                      <VoicePlaybackBubble text={parsedMessage.cleanText.replace(/\*\*/g, "").replace(/\*/g, "").replace(/\n/g, " ")} />
                    )}
                    {message.timestamp && <p className="text-[11px] text-apple-secondary">{message.timestamp}</p>}
                  </div>
                </div>
              </Fragment>
            );
          })}
          <div ref={messagesEndRef} />
        </div>

        {messages.length <= 1 && (
          <div className="flex flex-wrap gap-2 px-6 pb-3">
            {quickQuestions.map((question) => (
              <button key={question} onClick={() => void sendMessage(question)} className="apple-btn-secondary px-4 py-2 text-xs transition-all duration-150 active:scale-[0.97]">
                {question}
              </button>
            ))}
          </div>
        )}

        <div className="border-t border-apple-divider/50 px-5 pb-4 pt-3">
          {isStandbyMode && (
            <div className="mb-3 flex flex-wrap items-center gap-2 rounded-[14px] bg-[#eef6ff] px-4 py-2.5">
              <span className="text-xs font-semibold text-apple-blue">Watcher</span>
              <select value={standbyAction} onChange={(event) => setStandbyAction(event.target.value as StandbyAction)} className="apple-input h-8 px-2.5 text-xs text-apple-text">
                <option value="notify">Notify</option>
                <option value="log">Log</option>
                <option value="email">Email</option>
                <option value="digest">Digest</option>
                <option value="report">Report</option>
                <option value="spreadsheet">Spreadsheet</option>
                <option value="document">Document</option>
              </select>
              <select value={standbyIntervalSeconds} onChange={(event) => setStandbyIntervalSeconds(Number(event.target.value))} className="apple-input h-8 px-2.5 text-xs text-apple-text">
                <option value={10}>10s</option>
                <option value={60}>1m</option>
                <option value={300}>5m</option>
                <option value={3600}>1h</option>
                <option value={21600}>6h</option>
                <option value={86400}>24h</option>
              </select>
            </div>
          )}
          {/* @ mention dropdown */}
          {mentionQuery !== null && shipments.length > 0 && (
            <div
              className="mb-2 overflow-hidden rounded-[14px] border border-apple-divider bg-white shadow-apple-lg"
              style={{ animation: "mention-roll 0.2s ease both" }}
            >
              {shipments
                .filter((s) => {
                  const name = (s.candidateVessels[0]?.name ?? s.bookingReference).toLowerCase();
                  return mentionQuery === "" || name.includes(mentionQuery.toLowerCase());
                })
                .slice(0, 5)
                .map((s, i) => {
                  const name = s.candidateVessels[0]?.name ?? s.bookingReference;
                  return (
                    <button
                      key={s.shipmentId}
                      type="button"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        setInput((prev) => prev.replace(/@\S*$/, `@${name} `));
                        setMentionQuery(null);
                      }}
                      className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-apple-surface"
                      style={{ animationDelay: `${i * 30}ms` }}
                    >
                      <span className="text-base">🚢</span>
                      <div className="min-w-0">
                        <p className="font-medium text-apple-text">{name}</p>
                        <p className="text-[11px] text-apple-secondary">#{s.bookingReference} · {formatStatus(s.status)}</p>
                      </div>
                    </button>
                  );
                })}
            </div>
          )}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsStandbyMode((current) => !current)}
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-all duration-150 hover:bg-apple-hover active:scale-[0.97] ${isStandbyMode ? "bg-[#eef6ff] text-apple-blue" : "bg-apple-surface text-apple-secondary"}`}
            >
              <Plus className="h-4 w-4" strokeWidth={1.8} />
            </button>
            <div className="relative flex-1">
              <input
                type="text"
                value={input}
                onChange={(event) => {
                  const value = event.target.value;
                  setInput(value);
                  const atMatch = value.match(/@(\S*)$/);
                  setMentionQuery(atMatch ? atMatch[1] : null);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Escape") { setMentionQuery(null); return; }
                  if (event.key === "Enter") handleSend();
                }}
                placeholder={isStandbyMode ? "When this shipment shows... (type condition)" : "Ask anything · Type @ to mention a vessel"}
                className="apple-input h-11 w-full px-4 pr-12 text-sm text-apple-text placeholder:text-apple-secondary/70"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isSubmitting}
                className="absolute right-1.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-apple-blue text-white transition-all duration-150 active:scale-[0.97] disabled:opacity-30"
              >
                <Send className="h-3.5 w-3.5" strokeWidth={1.8} />
              </button>
            </div>
            <button
              onClick={handleVoice}
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-all duration-150 active:scale-[0.97] ${isRecording ? "bg-white shadow-apple text-apple-red" : "bg-apple-surface text-apple-secondary hover:bg-apple-hover"}`}
              style={isRecording ? { animation: "pulse-ring 1.5s ease-out infinite" } : {}}
            >
              <Mic className="h-4 w-4" strokeWidth={1.8} />
            </button>
          </div>
          <div className="mt-2.5 flex items-center gap-1.5">
            {(["concise", "balanced", "verbose"] as ResponseMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setResponseMode(mode)}
                className={`rounded-full px-3 py-1 text-[11px] font-medium capitalize transition-all duration-150 active:scale-[0.97] ${responseMode === mode ? "bg-apple-blue/10 text-apple-blue" : "text-apple-secondary hover:text-apple-text"}`}
              >
                {mode}
              </button>
            ))}
            <span className="ml-auto text-[11px] text-apple-secondary/60">
              {isVoiceMode ? "🎙 Voice on" : ""}
            </span>
            <button
              type="button"
              onClick={() => setIsVoiceMode((c) => !c)}
              className={`rounded-full px-2.5 py-1 text-[11px] transition-colors ${isVoiceMode ? "text-apple-blue" : "text-apple-secondary/50 hover:text-apple-secondary"}`}
            >
              🎙
            </button>
          </div>
        </div>
      </div>
      <AgentContextRail
        shipment={shipment}
        sourceReadiness={sourceReadiness}
        knowledgeSnippets={knowledgeSnippets}
        webSearchResults={webSearchResults}
        webSearchPlanSources={webSearchPlanSources}
        preferredTab={preferredRailTab}
      />
    </div>
  );
}


