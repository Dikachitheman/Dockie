import type {
  Evidence,
  EtaConfidence,
  HistoryPoint,
  KnowledgeSnippet,
  DemurrageExposure,
  CarrierPerformance,
  EtaRevision,
  Shipment,
  ShipmentComparison,
  ShipmentComparisonItem,
  ShipmentEvent,
  PortCongestionSummary,
  VesselAnomaly,
  SourceHealth,
  SourceReadiness,
  Vessel,
  VesselPosition,
  WebSearchResult,
  WebSearchSource,
  WebSearchSourcePlan,
} from "@/lib/shipment-ui";
import { supabase } from "@/integrations/supabase/client";
import type { AgentNotification, AgentOutput, StandbyAgent, StandbyAgentDraft } from "@/lib/standby-agents";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type ShipmentSummaryApi = {
  id: string;
  booking_ref: string;
  carrier: string;
  service_lane: string | null;
  load_port: string | null;
  discharge_port: string | null;
  cargo_type: string | null;
  units: number | null;
  status: string;
  declared_departure_date: string | null;
  declared_eta_date: string | null;
  candidate_vessels: Array<{
    vessel_id: string;
    imo: string | null;
    mmsi: string | null;
    name: string;
    is_primary: boolean;
  }>;
};

type ShipmentDetailApi = ShipmentSummaryApi & {
  candidate_vessels: Array<{
    vessel_id: string;
    imo: string | null;
    mmsi: string | null;
    name: string;
    is_primary: boolean;
  }>;
  evidence: Array<{
    source: string;
    captured_at: string;
    claim: string;
    url?: string | null;
  }>;
};

type ShipmentStatusApi = {
  shipment_id: string;
  booking_ref: string;
  carrier: string;
  status: string;
  declared_eta: string | null;
  latest_position: {
    mmsi: string;
    imo: string | null;
    vessel_name: string | null;
    latitude: number;
    longitude: number;
    sog_knots: number | null;
    cog_degrees: number | null;
    heading_degrees: number | null;
    navigation_status: string | null;
    destination_text: string | null;
    source: string;
    observed_at: string;
  } | null;
  eta_confidence: {
    confidence: number;
    freshness: string;
    explanation: string;
    declared_eta: string | null;
  };
  candidate_vessels: Array<{
    vessel_id: string;
    imo: string | null;
    mmsi: string | null;
    name: string;
    is_primary: boolean;
  }>;
  evidence_count: number;
  freshness_warning: string | null;
};

type ShipmentHistoryApi = {
  shipment_id: string;
  vessel_mmsi: string | null;
  vessel_name: string | null;
  track: Array<{
    latitude: number;
    longitude: number;
    sog_knots: number | null;
    cog_degrees: number | null;
    observed_at: string;
    source: string;
  }>;
  events: Array<{
    event_type: string;
    event_at: string;
    details: string | null;
    source: string;
  }>;
};

type ShipmentBundleApi = {
  detail: ShipmentDetailApi;
  status: ShipmentStatusApi;
  history: ShipmentHistoryApi;
};

type SourceHealthApi = {
  source: string;
  source_class: string;
  automation_safety: string;
  business_safe_default: boolean;
  source_status: string;
  last_success_at: string | null;
  stale_after_seconds: number;
  degraded_reason: string | null;
  updated_at: string | null;
};

type SourceReadinessApi = {
  source: string;
  enabled: boolean;
  configured: boolean;
  mode: string;
  role: string;
  business_safe_default: boolean;
  detail: string;
};

type KnowledgeSnippetApi = {
  source_name: string;
  source_type: string;
  content: string;
  relevance_score: number;
  metadata: Record<string, string | number | boolean | null | undefined>;
};

type KnowledgeSearchResponseApi = {
  query: string;
  shipment_id: string | null;
  snippets: KnowledgeSnippetApi[];
  retrieved_at: string;
};

type WebSearchSourceApi = {
  id: string;
  name: string;
  base_url: string;
  search_index_url: string;
  source_class: string;
  trust_level: string;
  match_reason?: string | null;
};

type WebSearchResultApi = {
  id: string;
  title: string;
  url: string;
  source: string;
  source_id: string;
  source_type: string;
  source_class: string;
  trust_level: string;
  published?: string | null;
  updated?: string | null;
  summary: string;
  snippet: string;
  tags: string[];
  relevance_score: number;
  match_reason: string;
};

type WebSearchResponseApi = {
  query: string;
  normalized_query: string;
  topics: string[];
  candidate_sources: WebSearchSourceApi[];
  results: WebSearchResultApi[];
  retrieved_at: string;
  search_mode: string;
};

type WebSearchPlanResponseApi = {
  query: string;
  normalized_query: string;
  topics: string[];
  candidate_sources: WebSearchSourceApi[];
  retrieved_at: string;
  search_mode: string;
};

type DemurrageExposureApi = {
  shipment_id: string;
  terminal_locode: string | null;
  free_days: number;
  daily_rate_ngn: number;
  daily_rate_usd: number | null;
  projected_cost_ngn: number;
  projected_cost_usd: number | null;
  clearance_risk_days: number;
  risk_level: string;
  free_days_end: string | null;
  notes: string[];
};

type ETARevisionApi = {
  revision_at: string;
  previous_eta: string | null;
  new_eta: string | null;
  delta_hours: number | null;
  source: string;
};

type ShipmentComparisonItemApi = {
  shipment_id: string;
  booking_ref: string;
  carrier: string;
  status: string;
  risk_score: number;
  summary: string;
  freshness: string;
};

type ShipmentComparisonApi = {
  compared_at: string;
  shipments: ShipmentComparisonItemApi[];
  recommendation: string | null;
};

type PortCongestionPointApi = {
  observed_at: string;
  delay_days: number;
  queue_vessels: number | null;
  source: string;
};

type PortCongestionSummaryApi = {
  shipment_id: string;
  port_locode: string | null;
  current_wait_days: number;
  p75_wait_days: number | null;
  p90_wait_days: number | null;
  seasonal_median_days: number | null;
  above_seasonal_days: number | null;
  recent_readings: PortCongestionPointApi[];
};

type CarrierPerformanceApi = {
  carrier: string;
  service_lane: string;
  year_month: string;
  median_delay_days: number | null;
  on_time_rate: number | null;
  sample_count: number;
  notes: string | null;
};

type VesselAnomalyApi = {
  shipment_id: string;
  severity: string;
  summary: string;
  indicators: string[];
  recommended_action: string | null;
};

type AgentStateApi = {
  threadId: string;
  threadExists: boolean;
  state: string;
  messages: string;
};

type AgUiMessage = {
  id: string;
  role: string;
  content?: string | null;
};

type StandbyAgentApi = {
  id: string;
  user_id: string;
  user_email: string | null;
  shipment_id: string | null;
  condition_text: string;
  trigger_type: string;
  action: "notify" | "email" | "digest" | "log" | "report" | "spreadsheet" | "document";
  interval_seconds: number;
  cooldown_seconds: number;
  status: "active" | "paused" | "fired";
  created_at: string | null;
  updated_at: string | null;
  last_checked_at: string | null;
  next_run_at: string | null;
  last_fired_at: string | null;
  fire_count: number;
  last_result: string | null;
};

type NotificationApi = {
  id: string;
  user_id: string;
  agent_id: string | null;
  output_id: string | null;
  channel: string;
  title: string;
  detail: string;
  unread: boolean;
  read_at: string | null;
  created_at: string | null;
};

type AgentOutputApi = {
  id: string;
  user_id: string;
  agent_id: string | null;
  shipment_id: string | null;
  output_type: string;
  title: string;
  preview_text: string;
  content: string;
  metadata_: Record<string, string | number | boolean | null> | null;
  created_at: string | null;
};

type AppBootstrapApi = {
  shipments: ShipmentSummaryApi[];
  source_health: SourceHealthApi[];
  standby_agents: StandbyAgentApi[];
  notifications: NotificationApi[];
  agent_outputs: AgentOutputApi[];
};

export type UiRichComponent = "map" | "tracking" | "evidence" | "graph";

export type UiChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  showMap?: boolean;
  shipmentCard?: boolean;
  isVoice?: boolean;
  richComponents?: UiRichComponent[];
  agentOutputId?: string | null;
  knowledgeSnippets?: KnowledgeSnippet[];
  webSearchResults?: WebSearchResult[];
  webSearchNotice?: string | null;
  responseMode?: "concise" | "balanced" | "verbose";
  isError?: boolean;
};

export type AppBootstrapPayload = {
  shipments: Shipment[];
  sourceHealth: SourceHealth[];
  standbyAgents: StandbyAgent[];
  notifications: AgentNotification[];
  agentOutputs: AgentOutput[];
};

const SESSION_STORAGE_KEY = "dockie-session-id";

function withBase(path: string): string {
  return `${API_BASE_URL}${path}`;
}

function getSessionId(): string {
  const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) return existing;
  const created = crypto.randomUUID();
  window.localStorage.setItem(SESSION_STORAGE_KEY, created);
  return created;
}

function normalizeRestoredMessageContent(role: string, content: string): string {
  if (role !== "user") {
    return content;
  }

  const match = content.match(/User request:\s*([\s\S]*)$/i);
  if (!match) {
    return content;
  }

  return match[1].trim();
}

function extractRichComponents(content: string): UiRichComponent[] {
  const directiveMatch = content.match(/<ui>([\s\S]*?)<\/ui>/i);
  if (!directiveMatch) {
    return [];
  }

  try {
    const parsed = JSON.parse(directiveMatch[1]) as { components?: string[] };
    return (parsed.components ?? []).filter((item): item is UiRichComponent =>
      item === "map" || item === "tracking" || item === "evidence" || item === "graph",
    );
  } catch {
    return [];
  }
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = await buildApiHeaders(init?.headers);
  const response = await fetch(withBase(path), {
    ...init,
    headers,
  });

  if (response.status === 401) {
    // Token may be stale (e.g. expired before autoRefreshToken completed on first load).
    // Force a refresh and retry once.
    await supabase.auth.refreshSession();
    const retryHeaders = await buildApiHeaders(init?.headers);
    const retryResponse = await fetch(withBase(path), { ...init, headers: retryHeaders });
    if (!retryResponse.ok) {
      throw new Error(`Request failed (${retryResponse.status}) for ${path}`);
    }
    return retryResponse.json() as Promise<T>;
  }

  if (!response.ok) {
    throw new Error(`Request failed (${response.status}) for ${path}`);
  }

  return response.json() as Promise<T>;
}

async function buildApiHeaders(extraHeaders?: HeadersInit): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Session-ID": getSessionId(),
  };

  const { data: sessionData } = await supabase.auth.getSession();
  if (sessionData.session) {
    headers["Authorization"] = `Bearer ${sessionData.session.access_token}`;
    headers["X-User-ID"] = sessionData.session.user.id;
    if (sessionData.session.user.email) {
      headers["X-User-Email"] = sessionData.session.user.email;
    }
  } else {
    const { data } = await supabase.auth.getUser();
    if (data.user?.id) {
      headers["X-User-ID"] = data.user.id;
    }
    if (data.user?.email) {
      headers["X-User-Email"] = data.user.email;
    }
  }

  if (extraHeaders instanceof Headers) {
    extraHeaders.forEach((value, key) => {
      headers[key] = value;
    });
  } else if (Array.isArray(extraHeaders)) {
    for (const [key, value] of extraHeaders) {
      headers[key] = value;
    }
  } else if (extraHeaders) {
    Object.assign(headers, extraHeaders);
  }

  return headers;
}

function toUiVessel(vessel: ShipmentDetailApi["candidate_vessels"][number]): Vessel {
  return {
    vesselId: vessel.vessel_id,
    imo: vessel.imo,
    mmsi: vessel.mmsi,
    name: vessel.name,
    isPrimary: vessel.is_primary,
  };
}

function toUiEvidence(evidence: ShipmentDetailApi["evidence"][number]): Evidence {
  return {
    source: evidence.source,
    capturedAt: evidence.captured_at,
    claim: evidence.claim,
    url: evidence.url ?? null,
  };
}

function toUiPosition(position: ShipmentStatusApi["latest_position"]): VesselPosition | null {
  if (!position) return null;
  return {
    source: position.source,
    observedAt: position.observed_at,
    mmsi: position.mmsi,
    imo: position.imo,
    vesselName: position.vessel_name,
    latitude: position.latitude,
    longitude: position.longitude,
    speedKnots: position.sog_knots,
    courseDegrees: position.cog_degrees,
    headingDegrees: position.heading_degrees,
    navStatus: position.navigation_status,
    destination: position.destination_text,
  };
}

function toUiHistoryPoint(point: ShipmentHistoryApi["track"][number]): HistoryPoint {
  return {
    observedAt: point.observed_at,
    latitude: point.latitude,
    longitude: point.longitude,
    speedKnots: point.sog_knots,
    courseDegrees: point.cog_degrees,
    source: point.source,
  };
}

function toUiEvent(event: ShipmentHistoryApi["events"][number]): ShipmentEvent {
  return {
    eventType: event.event_type,
    eventAt: event.event_at,
    details: event.details,
    source: event.source,
  };
}

function toUiEtaConfidence(conf: ShipmentStatusApi["eta_confidence"]): EtaConfidence {
  return {
    score: conf.confidence,
    freshness: conf.freshness,
    explanation: conf.explanation,
    declaredEta: conf.declared_eta,
  };
}

function summaryToShipment(summary: ShipmentSummaryApi): Shipment {
  return {
    shipmentId: summary.id,
    bookingReference: summary.booking_ref,
    carrier: summary.carrier,
    serviceLane: summary.service_lane,
    loadPort: summary.load_port,
    dischargePort: summary.discharge_port,
    cargoType: summary.cargo_type,
    units: summary.units,
    declaredDepartureDate: summary.declared_departure_date,
    declaredEtaDate: summary.declared_eta_date,
    status: summary.status as Shipment["status"],
    candidateVessels: summary.candidate_vessels.map(toUiVessel),
    evidence: [],
    currentPosition: null,
    historyPoints: [],
    events: [],
  };
}

export async function listShipments(): Promise<Shipment[]> {
  const data = await fetchJson<ShipmentSummaryApi[]>("/shipments");
  return data.map(summaryToShipment);
}

export async function getAppBootstrap(): Promise<AppBootstrapPayload> {
  const data = await fetchJson<AppBootstrapApi>("/app-bootstrap");
  return {
    shipments: data.shipments.map(summaryToShipment),
    sourceHealth: data.source_health.map((row) => ({
      source: row.source,
      sourceClass: row.source_class,
      sourceStatus: row.source_status,
      lastSuccessAt: row.last_success_at,
      staleAfterSeconds: row.stale_after_seconds,
      automationSafety: row.automation_safety,
      businessSafeDefault: row.business_safe_default,
      degradedReason: row.degraded_reason,
      updatedAt: row.updated_at,
    })),
    standbyAgents: data.standby_agents.map(toUiStandbyAgent),
    notifications: data.notifications.map(toUiNotification),
    agentOutputs: data.agent_outputs.map(toUiAgentOutput),
  };
}

export async function getShipmentBundle(shipmentId: string): Promise<Shipment> {
  const { detail, status, history } = await fetchJson<ShipmentBundleApi>(`/shipments/${shipmentId}/bundle`);

  return {
    shipmentId: detail.id,
    bookingReference: detail.booking_ref,
    carrier: detail.carrier,
    serviceLane: detail.service_lane,
    loadPort: detail.load_port,
    dischargePort: detail.discharge_port,
    cargoType: detail.cargo_type,
    units: detail.units,
    declaredDepartureDate: detail.declared_departure_date,
    declaredEtaDate: detail.declared_eta_date,
    status: status.status as Shipment["status"],
    candidateVessels: detail.candidate_vessels.map(toUiVessel),
    evidence: detail.evidence.map(toUiEvidence),
    currentPosition: toUiPosition(status.latest_position),
    historyPoints: history.track.map(toUiHistoryPoint),
    events: history.events.map(toUiEvent),
    evidenceCount: status.evidence_count,
    freshnessWarning: status.freshness_warning,
    etaConfidence: toUiEtaConfidence(status.eta_confidence),
  };
}

export async function getSourceHealth(): Promise<SourceHealth[]> {
  const data = await fetchJson<SourceHealthApi[]>("/source-health");
  return data.map((row) => ({
    source: row.source,
    sourceClass: row.source_class,
    sourceStatus: row.source_status,
    lastSuccessAt: row.last_success_at,
    staleAfterSeconds: row.stale_after_seconds,
    automationSafety: row.automation_safety,
    businessSafeDefault: row.business_safe_default,
    degradedReason: row.degraded_reason,
    updatedAt: row.updated_at,
  }));
}

export async function getSourceReadiness(): Promise<SourceReadiness[]> {
  const data = await fetchJson<SourceReadinessApi[]>("/sources/readiness");
  return data.map((row) => ({
    source: row.source,
    enabled: row.enabled,
    configured: row.configured,
    mode: row.mode,
    role: row.role,
    businessSafeDefault: row.business_safe_default,
    detail: row.detail,
  }));
}

// Standby worker control (dev-only)
export async function startStandbyWorker(): Promise<{ status: string }> {
  return fetchJson<{ status: string }>("/standby-worker/start", { method: "POST" });
}

export async function stopStandbyWorker(): Promise<{ status: string }> {
  return fetchJson<{ status: string }>("/standby-worker/stop", { method: "POST" });
}

export async function getStandbyWorkerStatus(): Promise<{ running: boolean }> {
  return fetchJson<{ running: boolean }>("/standby-worker/status");
}

export async function searchKnowledgeBase(
  query: string,
  shipmentId?: string,
  topK = 4,
): Promise<KnowledgeSnippet[]> {
  const params = new URLSearchParams({ query, top_k: String(topK) });
  if (shipmentId) {
    params.set("shipment_id", shipmentId);
  }
  const data = await fetchJson<KnowledgeSearchResponseApi>(`/knowledge/search?${params.toString()}`);
  return data.snippets.map((snippet) => ({
    sourceName: snippet.source_name,
    sourceType: snippet.source_type,
    content: snippet.content,
    relevanceScore: snippet.relevance_score,
    metadata: snippet.metadata,
  }));
}

export type WebSearchPayload = {
  query: string;
  normalizedQuery: string;
  topics: string[];
  candidateSources: WebSearchSource[];
  results: WebSearchResult[];
  retrievedAt: string;
  searchMode: string;
};

export type WebSearchPlanPayload = {
  query: string;
  normalizedQuery: string;
  topics: string[];
  candidateSources: WebSearchSourcePlan[];
  retrievedAt: string;
  searchMode: string;
};

export async function searchFakeWeb(
  query: string,
  topK = 5,
): Promise<WebSearchPayload> {
  const params = new URLSearchParams({ query, top_k: String(topK) });
  const data = await fetchJson<WebSearchResponseApi>(`/web-search?${params.toString()}`);
  return {
    query: data.query,
    normalizedQuery: data.normalized_query,
    topics: data.topics,
    candidateSources: data.candidate_sources.map((source) => ({
      id: source.id,
      name: source.name,
      baseUrl: source.base_url,
      searchIndexUrl: source.search_index_url,
      sourceClass: source.source_class,
      trustLevel: source.trust_level,
      matchReason: source.match_reason ?? null,
    })),
    results: data.results.map((result) => ({
      id: result.id,
      title: result.title,
      url: result.url,
      source: result.source,
      sourceId: result.source_id,
      sourceType: result.source_type,
      sourceClass: result.source_class,
      trustLevel: result.trust_level,
      published: result.published ?? null,
      updated: result.updated ?? null,
      summary: result.summary,
      snippet: result.snippet,
      tags: result.tags,
      relevanceScore: result.relevance_score,
      matchReason: result.match_reason,
    })),
    retrievedAt: data.retrieved_at,
    searchMode: data.search_mode,
  };
}

export async function searchFakeWebPlan(
  query: string,
): Promise<WebSearchPlanPayload> {
  const params = new URLSearchParams({ query });
  const data = await fetchJson<WebSearchPlanResponseApi>(`/web-search/plan?${params.toString()}`);
  return {
    query: data.query,
    normalizedQuery: data.normalized_query,
    topics: data.topics,
    candidateSources: data.candidate_sources.map((source) => ({
      id: source.id,
      name: source.name,
      baseUrl: source.base_url,
      searchIndexUrl: source.search_index_url,
      sourceClass: source.source_class,
      trustLevel: source.trust_level,
      matchReason: source.match_reason ?? null,
      status: "queued",
    })),
    retrievedAt: data.retrieved_at,
    searchMode: data.search_mode,
  };
}

export async function getDemurrageExposure(shipmentId: string): Promise<DemurrageExposure> {
  const data = await fetchJson<DemurrageExposureApi>(`/shipments/${shipmentId}/demurrage-exposure`);
  return {
    shipmentId: data.shipment_id,
    terminalLocode: data.terminal_locode,
    freeDays: data.free_days,
    dailyRateNgn: data.daily_rate_ngn,
    dailyRateUsd: data.daily_rate_usd,
    projectedCostNgn: data.projected_cost_ngn,
    projectedCostUsd: data.projected_cost_usd,
    clearanceRiskDays: data.clearance_risk_days,
    riskLevel: data.risk_level,
    freeDaysEnd: data.free_days_end,
    notes: data.notes,
  };
}

export async function getEtaRevisions(shipmentId: string): Promise<EtaRevision[]> {
  const data = await fetchJson<ETARevisionApi[]>(`/shipments/${shipmentId}/eta-revisions`);
  return data.map((item) => ({
    revisionAt: item.revision_at,
    previousEta: item.previous_eta,
    newEta: item.new_eta,
    deltaHours: item.delta_hours,
    source: item.source,
  }));
}

export async function compareShipments(shipmentIds?: string[]): Promise<ShipmentComparison> {
  const params = new URLSearchParams();
  if (shipmentIds && shipmentIds.length > 0) {
    params.set("shipment_ids", shipmentIds.join(","));
  }
  const query = params.toString();
  const data = await fetchJson<ShipmentComparisonApi>(`/shipments/compare${query ? `?${query}` : ""}`);
  return {
    comparedAt: data.compared_at,
    shipments: data.shipments.map((item): ShipmentComparisonItem => ({
      shipmentId: item.shipment_id,
      bookingReference: item.booking_ref,
      carrier: item.carrier,
      status: item.status,
      riskScore: item.risk_score,
      summary: item.summary,
      freshness: item.freshness,
    })),
    recommendation: data.recommendation,
  };
}

export async function getPortCongestionSummary(shipmentId: string): Promise<PortCongestionSummary> {
  const data = await fetchJson<PortCongestionSummaryApi>(`/shipments/${shipmentId}/port-congestion`);
  return {
    shipmentId: data.shipment_id,
    portLocode: data.port_locode,
    currentWaitDays: data.current_wait_days,
    p75WaitDays: data.p75_wait_days,
    p90WaitDays: data.p90_wait_days,
    seasonalMedianDays: data.seasonal_median_days,
    aboveSeasonalDays: data.above_seasonal_days,
    recentReadings: data.recent_readings.map((item) => ({
      observedAt: item.observed_at,
      delayDays: item.delay_days,
      queueVessels: item.queue_vessels,
      source: item.source,
    })),
  };
}

export async function listCarrierPerformance(serviceLane?: string | null): Promise<CarrierPerformance[]> {
  const query = serviceLane ? `?service_lane=${encodeURIComponent(serviceLane)}` : "";
  const data = await fetchJson<CarrierPerformanceApi[]>(`/shipments/carrier-performance${query}`);
  return data.map((item) => ({
    carrier: item.carrier,
    serviceLane: item.service_lane,
    yearMonth: item.year_month,
    medianDelayDays: item.median_delay_days,
    onTimeRate: item.on_time_rate,
    sampleCount: item.sample_count,
    notes: item.notes,
  }));
}

export async function getVesselAnomaly(shipmentId: string): Promise<VesselAnomaly> {
  const data = await fetchJson<VesselAnomalyApi>(`/shipments/${shipmentId}/vessel-anomaly`);
  return {
    shipmentId: data.shipment_id,
    severity: data.severity,
    summary: data.summary,
    indicators: data.indicators,
    recommendedAction: data.recommended_action,
  };
}

export async function getThreadMessages(threadId: string): Promise<UiChatMessage[]> {
  const data = await fetchJson<AgentStateApi>("/agent/agents/state", {
    method: "POST",
    body: JSON.stringify({ threadId }),
  });

  const messages = JSON.parse(data.messages || "[]") as AgUiMessage[];
  return messages
    .filter((message) => (message.role === "user" || message.role === "assistant") && message.content)
    .map((message) => ({
      id: message.id,
      role: message.role as "user" | "assistant",
      content: normalizeRestoredMessageContent(message.role, message.content ?? ""),
      timestamp: "",
      richComponents: extractRichComponents(message.content ?? ""),
    }));
}

type AgentRunParams = {
  threadId: string;
  prompt: string;
  state?: Record<string, unknown>;
  onAssistantDelta: (delta: string, messageId: string) => void;
  onEvent?: (event: AgentStreamEvent) => void;
};

export type AgentStreamEvent = {
  type: string;
  delta?: string;
  message?: string;
  code?: string;
  messageId?: string;
  runId?: string;
  threadId?: string;
  toolCallId?: string;
  toolCallName?: string;
};

export class AgentRunError extends Error {
  code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = "AgentRunError";
    this.code = code;
  }
}

export async function runAgentStream({ threadId, prompt, state, onAssistantDelta, onEvent }: AgentRunParams): Promise<void> {
  const runId = crypto.randomUUID();
  const userMessageId = crypto.randomUUID();
  const headers = await buildApiHeaders({
    Accept: "text/event-stream",
  });
  const response = await fetch(withBase("/agent/run"), {
    method: "POST",
    headers,
    body: JSON.stringify({
      thread_id: threadId,
      run_id: runId,
      state: state ?? {},
      messages: [
        {
          id: userMessageId,
          role: "user",
          content: prompt,
        },
      ],
      tools: [],
      context: [],
      forwarded_props: {},
    }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`Agent stream failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let assistantMessageId: string = crypto.randomUUID();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split(/\r?\n\r?\n/);
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      const dataLine = chunk
        .split(/\r?\n/)
        .find((line) => line.startsWith("data: "));

      if (!dataLine) continue;
      const payload = JSON.parse(dataLine.slice(6)) as AgentStreamEvent;
      onEvent?.(payload);

      if (payload.type === "TEXT_MESSAGE_START" && payload.messageId) {
        assistantMessageId = payload.messageId;
      } else if (payload.type === "TEXT_MESSAGE_CONTENT" && payload.delta) {
        onAssistantDelta(payload.delta, assistantMessageId);
      } else if (payload.type === "RUN_ERROR") {
        await reader.cancel();
        throw new AgentRunError(payload.message || "Agent run failed", payload.code);
      }
    }
  }
}

function toUiStandbyAgent(agent: StandbyAgentApi): StandbyAgent {
  return {
    id: agent.id,
    userId: agent.user_id,
    userEmail: agent.user_email,
    shipmentId: agent.shipment_id,
    conditionText: agent.condition_text,
    triggerType: agent.trigger_type,
    action: agent.action,
    intervalSeconds: agent.interval_seconds,
    cooldownSeconds: agent.cooldown_seconds,
    status: agent.status,
    createdAt: agent.created_at ?? "",
    updatedAt: agent.updated_at,
    lastCheckedAt: agent.last_checked_at,
    nextRunAt: agent.next_run_at,
    lastFiredAt: agent.last_fired_at,
    fireCount: agent.fire_count,
    lastResult: agent.last_result,
  };
}

function toUiNotification(notification: NotificationApi): AgentNotification {
  return {
    id: notification.id,
    userId: notification.user_id,
    agentId: notification.agent_id,
    outputId: notification.output_id,
    channel: notification.channel,
    title: notification.title,
    detail: notification.detail,
    unread: notification.unread,
    readAt: notification.read_at,
    createdAt: notification.created_at,
  };
}

function toUiAgentOutput(output: AgentOutputApi): AgentOutput {
  return {
    id: output.id,
    userId: output.user_id,
    agentId: output.agent_id,
    shipmentId: output.shipment_id,
    outputType: output.output_type,
    title: output.title,
    previewText: output.preview_text,
    content: output.content,
    metadata: output.metadata_ ?? null,
    createdAt: output.created_at,
  };
}

export async function listStandbyAgents(): Promise<StandbyAgent[]> {
  const data = await fetchJson<StandbyAgentApi[]>("/standby-agents");
  return data.map(toUiStandbyAgent);
}

export async function createStandbyAgent(draft: StandbyAgentDraft): Promise<StandbyAgent> {
  const data = await fetchJson<StandbyAgentApi>("/standby-agents", {
    method: "POST",
    body: JSON.stringify({
      condition_text: draft.conditionText,
      action: draft.action,
      interval_seconds: draft.intervalSeconds,
      shipment_id: draft.shipmentId ?? null,
    }),
  });
  return toUiStandbyAgent(data);
}

export async function updateStandbyAgent(
  agentId: string,
  patch: Partial<Pick<StandbyAgent, "conditionText" | "action" | "intervalSeconds" | "status">>,
): Promise<StandbyAgent> {
  const data = await fetchJson<StandbyAgentApi>(`/standby-agents/${agentId}`, {
    method: "PATCH",
    body: JSON.stringify({
      condition_text: patch.conditionText,
      action: patch.action,
      interval_seconds: patch.intervalSeconds,
      status: patch.status,
    }),
  });
  return toUiStandbyAgent(data);
}

export async function runStandbyAgent(agentId: string): Promise<StandbyAgent> {
  const data = await fetchJson<StandbyAgentApi>(`/standby-agents/${agentId}/run`, {
    method: "POST",
  });
  return toUiStandbyAgent(data);
}

export async function deleteStandbyAgent(agentId: string): Promise<void> {
  await fetchJson<void>(`/standby-agents/${agentId}`, {
    method: "DELETE",
  });
}

export async function listNotifications(): Promise<AgentNotification[]> {
  const data = await fetchJson<NotificationApi[]>("/notifications");
  return data.map(toUiNotification);
}

export async function markNotificationsRead(notificationIds?: string[]): Promise<AgentNotification[]> {
  const data = await fetchJson<NotificationApi[]>("/notifications/read", {
    method: "POST",
    body: JSON.stringify({ notification_ids: notificationIds ?? [] }),
  });
  return data.map(toUiNotification);
}

export async function listAgentOutputs(outputType?: string): Promise<AgentOutput[]> {
  const query = outputType ? `?output_type=${encodeURIComponent(outputType)}` : "";
  const data = await fetchJson<AgentOutputApi[]>(`/agent-outputs${query}`);
  return data.map(toUiAgentOutput);
}

export async function getAgentOutput(outputId: string): Promise<AgentOutput> {
  const data = await fetchJson<AgentOutputApi>(`/agent-outputs/${outputId}`);
  return toUiAgentOutput(data);
}


// ---------------------------------------------------------------------------
// PostGIS geospatial endpoints
// ---------------------------------------------------------------------------

type NearestPortApi = {
  locode: string;
  name: string;
  country: string;
  latitude: number;
  longitude: number;
  port_type: string;
  geofence_radius_nm: number;
  distance_nm: number | null;
};

type PortProximityApi = {
  within_geofence: boolean;
  locode: string | null;
  name: string | null;
  country: string | null;
  port_latitude: number | null;
  port_longitude: number | null;
  geofence_radius_nm: number | null;
  distance_nm: number | null;
  proximity_status: string | null;
};

type VesselPortProximityApi = {
  mmsi: string;
  imo: string | null;
  vessel_name: string | null;
  latitude: number;
  longitude: number;
  observed_at: string | null;
  port_proximity: PortProximityApi | null;
  nearest_port: NearestPortApi | null;
};

type ShipmentProximityApi = {
  shipment_id: string;
  vessel_proximities: VesselPortProximityApi[];
};

type NearbyVesselApi = {
  mmsi: string;
  imo: string | null;
  vessel_name: string | null;
  latitude: number;
  longitude: number;
  sog_knots: number | null;
  cog_degrees: number | null;
  navigation_status: string | null;
  destination_text: string | null;
  source: string;
  observed_at: string | null;
  distance_nm: number | null;
};

type NearbyVesselsResponseApi = {
  center_latitude: number;
  center_longitude: number;
  radius_nm: number;
  vessel_count: number;
  vessels: NearbyVesselApi[];
};

type ReferencePortApi = {
  locode: string;
  name: string;
  country: string;
  latitude: number;
  longitude: number;
  port_type: string;
  geofence_radius_nm: number;
};

import type {
  NearestPort,
  PortProximity,
  VesselPortProximity,
  NearbyVessel,
  ReferencePort,
} from "@/lib/shipment-ui";

function toUiNearestPort(api: NearestPortApi): NearestPort {
  return {
    locode: api.locode,
    name: api.name,
    country: api.country,
    latitude: api.latitude,
    longitude: api.longitude,
    portType: api.port_type,
    geofenceRadiusNm: api.geofence_radius_nm,
    distanceNm: api.distance_nm,
  };
}

function toUiPortProximity(api: PortProximityApi | null): PortProximity | null {
  if (!api) return null;
  return {
    withinGeofence: api.within_geofence,
    locode: api.locode,
    name: api.name,
    country: api.country,
    portLatitude: api.port_latitude,
    portLongitude: api.port_longitude,
    geofenceRadiusNm: api.geofence_radius_nm,
    distanceNm: api.distance_nm,
    proximityStatus: api.proximity_status,
  };
}

function toUiVesselPortProximity(api: VesselPortProximityApi): VesselPortProximity {
  return {
    mmsi: api.mmsi,
    imo: api.imo,
    vesselName: api.vessel_name,
    latitude: api.latitude,
    longitude: api.longitude,
    observedAt: api.observed_at,
    portProximity: toUiPortProximity(api.port_proximity),
    nearestPort: api.nearest_port ? toUiNearestPort(api.nearest_port) : null,
  };
}

export async function getShipmentPortProximity(shipmentId: string): Promise<{
  shipmentId: string;
  vesselProximities: VesselPortProximity[];
}> {
  const data = await fetchJson<ShipmentProximityApi>(`/geo/shipment-proximity/${shipmentId}`);
  return {
    shipmentId: data.shipment_id,
    vesselProximities: data.vessel_proximities.map(toUiVesselPortProximity),
  };
}

export async function getVesselPortProximity(mmsi: string): Promise<VesselPortProximity> {
  const data = await fetchJson<VesselPortProximityApi>(`/geo/vessel-proximity/${mmsi}`);
  return toUiVesselPortProximity(data);
}

export async function findNearbyVessels(
  latitude: number,
  longitude: number,
  radiusNm = 50,
  limit = 20,
): Promise<{ centerLatitude: number; centerLongitude: number; radiusNm: number; vesselCount: number; vessels: NearbyVessel[] }> {
  const params = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
    radius_nm: String(radiusNm),
    limit: String(limit),
  });
  const data = await fetchJson<NearbyVesselsResponseApi>(`/geo/nearby-vessels?${params}`);
  return {
    centerLatitude: data.center_latitude,
    centerLongitude: data.center_longitude,
    radiusNm: data.radius_nm,
    vesselCount: data.vessel_count,
    vessels: data.vessels.map((v) => ({
      mmsi: v.mmsi,
      imo: v.imo,
      vesselName: v.vessel_name,
      latitude: v.latitude,
      longitude: v.longitude,
      sogKnots: v.sog_knots,
      cogDegrees: v.cog_degrees,
      navigationStatus: v.navigation_status,
      destinationText: v.destination_text,
      source: v.source,
      observedAt: v.observed_at,
      distanceNm: v.distance_nm,
    })),
  };
}

export async function getNearestPort(
  latitude: number,
  longitude: number,
  limit = 3,
): Promise<{ queryLatitude: number; queryLongitude: number; ports: NearestPort[] }> {
  const params = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
    limit: String(limit),
  });
  const data = await fetchJson<{ query_latitude: number; query_longitude: number; ports: NearestPortApi[] }>(
    `/geo/nearest-port?${params}`,
  );
  return {
    queryLatitude: data.query_latitude,
    queryLongitude: data.query_longitude,
    ports: data.ports.map(toUiNearestPort),
  };
}

export async function listReferencePorts(): Promise<ReferencePort[]> {
  const data = await fetchJson<ReferencePortApi[]>("/geo/reference-ports");
  return data.map((p) => ({
    locode: p.locode,
    name: p.name,
    country: p.country,
    latitude: p.latitude,
    longitude: p.longitude,
    portType: p.port_type,
    geofenceRadiusNm: p.geofence_radius_nm,
  }));
}
