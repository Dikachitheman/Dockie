import { Shipment } from "./mockData";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  showMap?: boolean;
  shipmentCard?: boolean;
}

export function generateResponse(question: string, shipment: Shipment): ChatMessage {
  const q = question.toLowerCase();
  const pos = shipment.currentPosition;
  const vessel = shipment.candidateVessels[0];
  const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  let content = "";
  let showMap = false;
  let shipmentCard = false;

  if (q.includes("where") || q.includes("location") || q.includes("position")) {
    if (pos) {
      content = `Your shipment **${shipment.bookingReference}** is currently aboard the **${pos.vesselName}**.\n\n📍 **Current Position:** ${pos.latitude.toFixed(4)}°N, ${pos.longitude.toFixed(4)}°${pos.longitude >= 0 ? "E" : "W"}\n⚡ **Speed:** ${pos.speedKnots} knots\n🧭 **Course:** ${pos.courseDegrees ?? "N/A"}°\n📡 **Source:** ${pos.source}\n🕐 **Last Updated:** ${new Date(pos.observedAt).toLocaleString()}\n\nThe vessel is heading toward **${shipment.dischargePort}**.`;
      showMap = true;
    } else {
      content = `Your shipment **${shipment.bookingReference}** is currently in **${shipment.status}** status. No live position data is available yet. The vessel has not departed.`;
    }
  } else if (q.includes("vessel") || q.includes("ship") || q.includes("boat")) {
    if (vessel) {
      content = `Your shipment is assigned to the **${vessel.name}**.\n\n🚢 **IMO:** ${vessel.imo}\n📡 **MMSI:** ${vessel.mmsi}\n🏷️ **Carrier:** ${shipment.carrier.toUpperCase()}\n📦 **Cargo:** ${shipment.units} units of ${shipment.cargoType}`;
      showMap = !!pos;
    } else {
      content = "No vessel has been assigned to this shipment yet.";
    }
  } else if (q.includes("fast") || q.includes("speed")) {
    if (pos) {
      content = `The **${pos.vesselName}** is currently moving at **${pos.speedKnots} knots** (approximately ${(pos.speedKnots * 1.852).toFixed(1)} km/h).\n\n🧭 Course: ${pos.courseDegrees ?? "N/A"}°\n📡 Source: ${pos.source}\n🕐 Last observed: ${new Date(pos.observedAt).toLocaleString()}`;
      showMap = true;
    } else {
      content = "No speed data is currently available. The vessel may not have departed yet.";
    }
  } else if (q.includes("arrive") || q.includes("eta") || q.includes("when")) {
    content = `The declared ETA for shipment **${shipment.bookingReference}** to **${shipment.dischargePort}** is **${new Date(shipment.declaredEtaDate).toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}**.\n\n⚠️ *Note: ETAs are based on carrier schedules and may change. Source: ${shipment.evidence[0]?.source ?? "carrier_schedule"}*`;
    shipmentCard = true;
    showMap = !!pos;
  } else if (q.includes("changed") || q.includes("update") || q.includes("yesterday") || q.includes("history")) {
    const events = shipment.events.slice(-3);
    content = `Here are the latest events for **${shipment.bookingReference}**:\n\n${events.map(e => `• **${e.eventType.replace(/_/g, " ")}** — ${new Date(e.eventAt).toLocaleString()}\n  ${e.details}`).join("\n\n")}`;
  } else if (q.includes("reliable") || q.includes("confidence") || q.includes("trust")) {
    if (pos) {
      content = `**Data Reliability Assessment:**\n\n📡 **Position Source:** ${pos.source}\n🕐 **Last Observed:** ${new Date(pos.observedAt).toLocaleString()}\n⚠️ **Freshness:** Position data is ${Math.round((Date.now() - new Date(pos.observedAt).getTime()) / (1000 * 60 * 60))} hours old\n\nThe ${pos.source} source is classified as a **public API** with moderate automation safety. Position data should be considered **best-effort** and may lag behind real-time by several hours.`;
    } else {
      content = "No live data available to assess reliability. The shipment has not departed yet.";
    }
  } else {
    content = `I can help with your shipment **${shipment.bookingReference}**. You can ask me:\n\n• "Where is my shipment right now?"\n• "What vessel is it on?"\n• "How fast is it moving?"\n• "When will it arrive?"\n• "What changed recently?"\n• "How reliable is this data?"`;
    shipmentCard = true;
  }

  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content,
    timestamp: now,
    showMap,
    shipmentCard,
  };
}
