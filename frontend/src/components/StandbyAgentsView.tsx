import { useMemo, useState } from "react";
import { BookOpen, Bot, FileText, Mail, Plus, Radio, Sparkles, Table2, Zap } from "lucide-react";
import {
  type AgentOutput,
  createStandbyAgentDraft,
  describeStandbyAction,
  formatStandbyInterval,
  parseStandbyCondition,
  type StandbyAction,
  type StandbyAgent,
  type StandbyAgentDraft,
} from "@/lib/standby-agents";
import type { Shipment } from "@/lib/shipment-ui";

interface StandbyAgentsViewProps {
  agents: StandbyAgent[];
  outputs: AgentOutput[];
  shipments: Shipment[];
  activePanel: "agents" | "email" | "report" | "spreadsheet" | "document";
  onActivePanelChange: (panel: "agents" | "email" | "report" | "spreadsheet" | "document") => void;
  onCreateAgent: (draft: StandbyAgentDraft) => void | Promise<void>;
  onRunAgent: (agentId: string) => void | Promise<void>;
  onDeleteAgent: (agentId: string) => void | Promise<void>;
  onUpdateAgent: (agentId: string, patch: Partial<Pick<StandbyAgent, "status">>) => void | Promise<void>;
  onOpenOutput?: (outputId: string) => void;
}

export default function StandbyAgentsView({
  agents,
  outputs,
  shipments,
  activePanel,
  onActivePanelChange,
  onCreateAgent,
  onRunAgent,
  onDeleteAgent,
  onUpdateAgent,
  onOpenOutput,
}: StandbyAgentsViewProps) {
  const [conditionText, setConditionText] = useState("");
  const [action, setAction] = useState<StandbyAction>("notify");
  const [intervalSeconds, setIntervalSeconds] = useState(3600);
  const [shipmentId, setShipmentId] = useState<string>("all");
  const [isCreating, setIsCreating] = useState(false);
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());

  const parsed = useMemo(
    () => (conditionText.trim() ? parseStandbyCondition(conditionText) : null),
    [conditionText],
  );
  const selectedShipment = useMemo(
    () => shipments.find((shipment) => shipment.shipmentId === shipmentId) ?? null,
    [shipmentId, shipments],
  );
  const filteredOutputs = useMemo(
    () => (activePanel === "agents" ? [] : outputs.filter((output) => output.outputType === activePanel)),
    [activePanel, outputs],
  );

  const buildCheckSummary = (agent: StandbyAgent) => {
    if (!agent.lastCheckedAt) return null;
    if (!agent.lastFiredAt) return "Latest check did not create a fire yet.";
    const checkedAt = new Date(agent.lastCheckedAt).getTime();
    const firedAt = new Date(agent.lastFiredAt).getTime();
    if (checkedAt > firedAt) {
      return "Latest check matched again, but it was not a new fire.";
    }
    return "Latest check created the current fired state.";
  };

  const handleCreate = async () => {
    if (!conditionText.trim() || isCreating) return;
    const draft = createStandbyAgentDraft(conditionText, action, intervalSeconds, shipmentId === "all" ? null : shipmentId);
    setIsCreating(true);
    try {
      await onCreateAgent(draft);
      setConditionText("");
      setAction("notify");
      setIntervalSeconds(3600);
      setShipmentId("all");
    } finally {
      setIsCreating(false);
    }
  };

  const handleDelete = async (agentId: string) => {
    if (deletingIds.has(agentId)) return;
    setDeletingIds((prev) => new Set(prev).add(agentId));
    try {
      await onDeleteAgent(agentId);
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(agentId);
        return next;
      });
    }
  };

  return (
    <div className="flex flex-1 overflow-y-auto bg-[#f5f5f7] scrollbar-thin">
      <div className="mx-auto flex w-full max-w-6xl gap-0 p-0 lg:gap-0">
        {/* Left nav panel */}
        <div className="hidden w-[240px] shrink-0 border-r border-apple-divider bg-white lg:flex lg:flex-col">
          <div className="border-b border-apple-divider px-5 py-5">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-[#07111f]">
                <Bot className="h-4 w-4 text-white" strokeWidth={1.5} />
              </div>
              <div>
                <p className="text-sm font-semibold text-apple-text">Dockie Agents</p>
                <p className="text-[11px] text-apple-secondary">Reactive copilots</p>
              </div>
            </div>
          </div>
          <nav className="flex-1 overflow-y-auto px-3 py-4">
            <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-apple-secondary">Workspace</p>
            <button
              type="button"
              onClick={() => onActivePanelChange("agents")}
              className={`flex w-full items-center gap-3 rounded-[12px] px-3 py-2.5 text-left transition-colors ${activePanel === "agents" ? "bg-apple-blue text-white" : "text-apple-secondary hover:bg-apple-surface hover:text-apple-text"}`}
            >
              <Radio className="h-4 w-4 shrink-0" strokeWidth={1.5} />
              <div className="min-w-0">
                <p className="text-sm font-medium">Active Agents</p>
                <p className={`text-[11px] ${activePanel === "agents" ? "text-white/70" : "text-apple-secondary"}`}>{agents.length} configured</p>
              </div>
            </button>

            <p className="mt-5 px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-apple-secondary">Outputs</p>
            {([
              { panel: "email" as const, label: "Email", sub: "Drafted updates", icon: Mail },
              { panel: "report" as const, label: "Reports", sub: "Generated reports", icon: FileText },
              { panel: "spreadsheet" as const, label: "Spreadsheets", sub: "Data exports", icon: Table2 },
              { panel: "document" as const, label: "Documents", sub: "Drafted docs", icon: BookOpen },
            ]).map(({ panel, label, sub, icon: Icon }) => {
              const count = outputs.filter((o) => o.outputType === panel).length;
              return (
                <button
                  key={panel}
                  type="button"
                  onClick={() => onActivePanelChange(panel)}
                  className={`mt-1 flex w-full items-center gap-3 rounded-[12px] px-3 py-2.5 text-left transition-colors ${activePanel === panel ? "bg-apple-blue text-white" : "text-apple-secondary hover:bg-apple-surface hover:text-apple-text"}`}
                >
                  <Icon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{label}</p>
                    <p className={`text-[11px] ${activePanel === panel ? "text-white/70" : "text-apple-secondary"}`}>{sub}</p>
                  </div>
                  {count > 0 && (
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${activePanel === panel ? "bg-white/20 text-white" : "bg-apple-surface text-apple-secondary"}`}>
                      {count}
                    </span>
                  )}
                </button>
              );
            })}

            <div className="mt-6 rounded-[14px] border border-apple-divider/60 bg-apple-surface/60 p-4">
              <div className="flex items-center gap-2">
                <Zap className="h-3.5 w-3.5 text-apple-blue" strokeWidth={1.5} />
                <p className="text-[11px] font-semibold text-apple-text">Quick tip</p>
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-apple-secondary">
                Agents fire automatically when conditions are met. Check the chat to set one up.
              </p>
            </div>
          </nav>
        </div>

        <div className="min-w-0 flex-1 space-y-4 overflow-y-auto p-4 sm:space-y-6 sm:p-6">
          {/* Mobile nav */}
          <div className="flex gap-2 overflow-x-auto pb-1 lg:hidden">
            {([
              { panel: "agents" as const, label: "Agents" },
              { panel: "email" as const, label: "Email" },
              { panel: "report" as const, label: "Reports" },
              { panel: "spreadsheet" as const, label: "Sheets" },
              { panel: "document" as const, label: "Docs" },
            ]).map(({ panel, label }) => (
              <button
                key={panel}
                type="button"
                onClick={() => onActivePanelChange(panel)}
                className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium transition-colors ${activePanel === panel ? "bg-apple-blue text-white" : "bg-white text-apple-secondary border border-apple-divider"}`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="rounded-[20px] bg-[linear-gradient(135deg,#07111f_0%,#17334f_100%)] p-6 text-white shadow-apple">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-white/70">
              <Bot className="h-4 w-4" strokeWidth={1.5} />
              {activePanel === "agents" ? "Standby Agents" : `Agent ${activePanel}s`}
            </div>
            <h1 className="mt-2 text-xl font-semibold">
              {activePanel === "agents" ? "Reactive copilots for timing-sensitive logistics" : `${activePanel.charAt(0).toUpperCase() + activePanel.slice(1)} outputs from your agents`}
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-white/70">
              {activePanel === "agents"
                ? "Create natural-language watchers that monitor shipment conditions and fire when something important happens."
                : "Review and act on agent-generated outputs for this category."}
            </p>
          </div>

          {activePanel === "agents" && <div className="apple-card p-6">
            <div className="flex items-center gap-2 text-sm font-semibold text-apple-text">
              <Plus className="h-4 w-4 text-apple-blue" strokeWidth={1.5} />
              New Standby Agent
            </div>
            <textarea
              value={conditionText}
              onChange={(event) => setConditionText(event.target.value)}
              placeholder="When any shipment shows a freshness warning, notify me."
              className="apple-input mt-4 min-h-28 w-full p-4 text-sm text-apple-text placeholder:text-apple-secondary"
            />
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <select value={shipmentId} onChange={(event) => setShipmentId(event.target.value)} className="apple-input h-11 px-3 text-sm text-apple-text">
                <option value="all">All shipments</option>
                {shipments.map((shipment) => (
                  <option key={shipment.shipmentId} value={shipment.shipmentId}>
                    {shipment.bookingReference} | {shipment.shipmentId}
                  </option>
                ))}
              </select>
              <select value={action} onChange={(event) => setAction(event.target.value as StandbyAction)} className="apple-input h-11 px-3 text-sm text-apple-text">
                <option value="notify">In-app notification</option>
                <option value="log">Log entry</option>
                <option value="email">Send email</option>
                <option value="digest">Morning digest</option>
                <option value="report">Draft report</option>
                <option value="spreadsheet">Build spreadsheet</option>
                <option value="document">Draft document</option>
              </select>
              <select value={intervalSeconds} onChange={(event) => setIntervalSeconds(Number(event.target.value))} className="apple-input h-11 px-3 text-sm text-apple-text">
                <option value={10}>Check every 10s</option>
                <option value={60}>Check every 1m</option>
                <option value={300}>Check every 5m</option>
                <option value={3600}>Check every 1h</option>
                <option value={21600}>Check every 6h</option>
                <option value={86400}>Check every 24h</option>
              </select>
            </div>
            <div className="mt-3">
              <button
                onClick={() => void handleCreate()}
                disabled={!conditionText.trim() || isCreating}
                className="apple-btn-secondary h-11 w-full text-sm font-medium disabled:opacity-50"
              >
                {isCreating ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-apple-secondary border-t-transparent" />
                    Creating agent…
                  </span>
                ) : "Save Agent"}
              </button>
            </div>
            {parsed && (
              <div className="mt-4 rounded-[16px] bg-apple-surface p-4">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.12em] text-apple-secondary">
                  <Sparkles className="h-3.5 w-3.5 text-apple-blue" strokeWidth={1.5} />
                  Parsed Preview
                </div>
                <p className="mt-2 text-sm font-medium text-apple-text">{parsed.trigger}</p>
                <p className="mt-1 text-sm leading-relaxed text-apple-secondary">
                  {parsed.summary} Scope: {selectedShipment ? `${selectedShipment.bookingReference} (${selectedShipment.shipmentId})` : "all shipments"}. Action: {describeStandbyAction(action)}. Frequency: every {formatStandbyInterval(intervalSeconds)}.
                </p>
              </div>
            )}
          </div>}

          {activePanel === "agents" ? <div className="space-y-4">
            {agents.length === 0 ? (
              <div className="apple-card p-6 text-center">
                <p className="text-sm font-medium text-apple-text">No standby agents yet</p>
                <p className="mt-2 text-sm leading-relaxed text-apple-secondary">
                  Create one to watch ETA shifts, freshness warnings, anchorage events, or shipment milestones in the background.
                </p>
              </div>
            ) : (
              agents.map((agent) => (
                <div key={agent.id} className="apple-card p-6">
                  <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between sm:gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start gap-2">
                        <Radio className={`mt-0.5 h-4 w-4 shrink-0 ${agent.status === "active" ? "text-apple-blue" : agent.status === "fired" ? "text-apple-amber" : "text-apple-secondary"}`} strokeWidth={1.5} />
                        <span className="text-sm font-semibold text-apple-text">{agent.conditionText}</span>
                      </div>
                      <p className="mt-2 text-xs text-apple-secondary">
                        {agent.action} every {formatStandbyInterval(agent.intervalSeconds)} · created {new Date(agent.createdAt).toLocaleString()}
                      </p>
                      {agent.lastResult && <p className="mt-2 text-sm text-apple-secondary">{agent.lastResult}</p>}
                      {buildCheckSummary(agent) && <p className="mt-2 text-xs font-medium text-apple-secondary/80">{buildCheckSummary(agent)}</p>}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <span className={`rounded-full px-3 py-1 text-[11px] font-medium uppercase tracking-[0.12em] ${
                        agent.status === "active"
                          ? "bg-[#eef6ff] text-apple-blue"
                          : agent.status === "fired"
                            ? "bg-apple-amber/15 text-apple-amber"
                            : "bg-apple-surface text-apple-secondary"
                      }`}>
                        {agent.status}
                      </span>
                      <button onClick={() => void onRunAgent(agent.id)} className="apple-btn-secondary px-3 py-1.5 text-xs">
                        Run check
                      </button>
                      <button
                        onClick={() => void onUpdateAgent(agent.id, { status: agent.status === "paused" ? "active" : "paused" })}
                        className="apple-btn-secondary px-3 py-1.5 text-xs"
                      >
                        {agent.status === "paused" ? "Resume" : "Pause"}
                      </button>
                      <button
                        onClick={() => void handleDelete(agent.id)}
                        disabled={deletingIds.has(agent.id)}
                        className="apple-btn-secondary px-3 py-1.5 text-xs text-apple-red disabled:opacity-50"
                      >
                        {deletingIds.has(agent.id) ? (
                          <span className="flex items-center gap-1.5">
                            <span className="h-3 w-3 animate-spin rounded-full border-2 border-apple-red/40 border-t-apple-red" />
                            Deleting…
                          </span>
                        ) : "Delete"}
                      </button>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4 text-xs">
                    <div className="rounded-[14px] bg-apple-surface p-3">
                      <p className="text-apple-secondary">Last checked</p>
                      <p className="mt-1 font-medium text-apple-text">{agent.lastCheckedAt ? new Date(agent.lastCheckedAt).toLocaleString() : "Never"}</p>
                    </div>
                    <div className="rounded-[14px] bg-apple-surface p-3">
                      <p className="text-apple-secondary">Next run</p>
                      <p className="mt-1 font-medium text-apple-text">{agent.nextRunAt ? new Date(agent.nextRunAt).toLocaleString() : "Pending"}</p>
                    </div>
                    <div className="rounded-[14px] bg-apple-surface p-3">
                      <p className="text-apple-secondary">Last fired</p>
                      <p className="mt-1 font-medium text-apple-text">{agent.lastFiredAt ? new Date(agent.lastFiredAt).toLocaleString() : "Not yet"}</p>
                    </div>
                    <div className="rounded-[14px] bg-apple-surface p-3">
                      <p className="text-apple-secondary">Fire count</p>
                      <p className="mt-1 font-medium text-apple-text">{agent.fireCount}</p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div> : (
            <div className="space-y-4">
              {filteredOutputs.length === 0 ? (
                <div className="apple-card p-6 text-center">
                  <p className="text-sm font-medium text-apple-text">No {activePanel} outputs yet</p>
                  <p className="mt-2 text-sm leading-relaxed text-apple-secondary">
                    Fired standby agents will deposit generated {activePanel} outputs here.
                  </p>
                </div>
              ) : (
                filteredOutputs.map((output) => {
                  const typeConfig = {
                    report:      { icon: FileText,  iconBg: "bg-[#eef6ff]", iconColor: "text-apple-blue",      headerBg: "bg-[#f5f8fc]", accentText: "text-apple-blue",      borderColor: "border-[#d0dff5]" },
                    spreadsheet: { icon: Table2,    iconBg: "bg-[#f5f5f7]", iconColor: "text-[#3c3c43]",       headerBg: "bg-[#f5f5f7]", accentText: "text-[#3c3c43]",       borderColor: "border-[#d2d2d7]" },
                    document:    { icon: BookOpen,  iconBg: "bg-[#f5f5f7]", iconColor: "text-apple-secondary", headerBg: "bg-[#f5f5f7]", accentText: "text-apple-secondary", borderColor: "border-[#d2d2d7]" },
                    email:       { icon: Mail,      iconBg: "bg-[#fff4ec]", iconColor: "text-orange-500",      headerBg: "bg-[#fff8f3]", accentText: "text-orange-500",      borderColor: "border-[#ffd6b8]" },
                  }[output.outputType as string] ?? { icon: FileText, iconBg: "bg-[#f5f5f7]", iconColor: "text-apple-secondary", headerBg: "bg-[#f5f5f7]", accentText: "text-apple-secondary", borderColor: "border-[#d2d2d7]" };
                  const TypeIcon = typeConfig.icon;
                  return (
                  <div key={output.id} className={`overflow-hidden rounded-[20px] border bg-white shadow-apple ${typeConfig.borderColor}`}>
                    {/* Styled header */}
                    <div className={`${typeConfig.headerBg} px-6 py-4`}>
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-center gap-3">
                          <div className={`shrink-0 rounded-[10px] ${typeConfig.iconBg} p-2`}>
                            <TypeIcon className={`h-4 w-4 ${typeConfig.iconColor}`} strokeWidth={1.5} />
                          </div>
                          <div>
                            <p className={`text-[10px] font-semibold uppercase tracking-[0.14em] ${typeConfig.accentText}`}>{output.outputType}</p>
                            <p className="text-sm font-semibold leading-snug text-apple-text">{output.title}</p>
                          </div>
                        </div>
                        {onOpenOutput && (
                          <button
                            type="button"
                            onClick={() => onOpenOutput(output.id)}
                            className="shrink-0 rounded-full border border-apple-divider bg-white/80 px-3 py-1 text-[11px] font-medium text-apple-blue backdrop-blur-sm transition-colors hover:bg-white"
                          >
                            Open
                          </button>
                        )}
                      </div>
                      {output.previewText && (
                        <p className="mt-2 text-[13px] leading-relaxed text-apple-secondary">{output.previewText}</p>
                      )}
                    </div>
                    {/* Content preview */}
                    <div className="px-6 py-5">
                      {output.outputType === "spreadsheet" ? (
                        <div className="overflow-x-auto rounded-[12px] border border-[#d2d2d7] bg-[#f5f5f7]">
                          <pre className="line-clamp-5 whitespace-pre-wrap p-4 font-mono text-[12px] leading-relaxed text-apple-text">{output.content}</pre>
                        </div>
                      ) : output.outputType === "document" ? (
                        <div className="rounded-[12px] border border-[#d2d2d7] bg-white px-4 py-3" style={{ boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.04)" }}>
                          <p className="line-clamp-4 whitespace-pre-wrap text-[13px] leading-[1.7] text-apple-text">{output.content}</p>
                        </div>
                      ) : (
                        <div className={`rounded-[12px] border ${typeConfig.borderColor} bg-[#fafcff] p-4`}>
                          <p className="line-clamp-4 whitespace-pre-wrap text-[13px] leading-relaxed text-apple-text">{output.content}</p>
                        </div>
                      )}
                      <div className="mt-3 flex items-center justify-between">
                        <p className="text-[11px] text-apple-secondary/60">
                          {output.createdAt ? new Date(output.createdAt).toLocaleString() : "Pending"}
                        </p>
                        <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] ${typeConfig.iconBg} ${typeConfig.iconColor}`}>
                          {output.outputType}
                        </span>
                      </div>
                    </div>
                  </div>
                  );
                })
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
