export type StandbyAction = "notify" | "email" | "digest" | "log" | "report" | "spreadsheet" | "document";
export type StandbyStatus = "active" | "paused" | "fired";

export interface StandbyAgent {
  id: string;
  userId: string;
  userEmail: string | null;
  shipmentId: string | null;
  conditionText: string;
  triggerType: string;
  action: StandbyAction;
  intervalSeconds: number;
  cooldownSeconds: number;
  status: StandbyStatus;
  createdAt: string;
  updatedAt: string | null;
  lastCheckedAt: string | null;
  nextRunAt: string | null;
  lastFiredAt: string | null;
  fireCount: number;
  lastResult: string | null;
}

export interface StandbyAgentDraft {
  conditionText: string;
  action: StandbyAction;
  intervalSeconds: number;
  shipmentId?: string | null;
}

export interface AgentNotification {
  id: string;
  userId: string;
  agentId: string | null;
  outputId?: string | null;
  channel: string;
  title: string;
  detail: string;
  unread: boolean;
  readAt: string | null;
  createdAt: string | null;
}

export interface AgentOutput {
  id: string;
  userId: string;
  agentId: string | null;
  shipmentId: string | null;
  outputType: string;
  title: string;
  previewText: string;
  content: string;
  metadata?: Record<string, string | number | boolean | null> | null;
  createdAt: string | null;
}

export function createStandbyAgentDraft(
  conditionText: string,
  action: StandbyAction,
  intervalSeconds: number,
  shipmentId?: string | null,
): StandbyAgentDraft {
  return {
    conditionText: conditionText.trim(),
    action,
    intervalSeconds,
    shipmentId: shipmentId ?? null,
  };
}

export function parseStandbyCondition(conditionText: string) {
  const lower = conditionText.toLowerCase();
  let trigger = "general watch";
  if (lower.includes("fresh")) trigger = "freshness";
  else if (lower.includes("eta")) trigger = "eta shift";
  else if (lower.includes("anchor")) trigger = "anchorage status";
  else if (lower.includes("lagos")) trigger = "lagos arrival";
  else if (lower.includes("demurrage")) trigger = "financial exposure";

  return {
    trigger,
    summary: `Watching for ${trigger} when matched.`,
  };
}

export function describeStandbyAction(action: StandbyAction): string {
  switch (action) {
    case "digest":
      return "queue a digest";
    case "email":
      return "send an email";
    case "log":
      return "write a log entry";
    case "report":
      return "draft a report";
    case "spreadsheet":
      return "build a spreadsheet";
    case "document":
      return "draft a document";
    default:
      return "send an in-app notification";
  }
}

export function formatStandbyInterval(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds % 3600 === 0) return `${seconds / 3600}h`;
  if (seconds % 60 === 0) return `${seconds / 60}m`;
  return `${seconds}s`;
}
