import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Shipment, ShipmentEvent } from "@/lib/shipment-ui";

interface ShipmentMapProps {
  shipment: Shipment;
  shipments?: Shipment[];
  selectedShipmentId?: string;
  compact?: boolean;
  compactHeightClass?: string;
}

type TrackPoint = {
  latitude: number;
  longitude: number;
  observedAt: string;
  source: string;
};

type EventCluster = {
  index: number;
  latitude: number;
  longitude: number;
  color: string;
  label: string;
  events: ShipmentEvent[];
};

const SELECTED_BASE_COLOR = "#0071e3";
const OTHER_MARKER_COLORS = ["#90a7c1", "#7ea0b8", "#8ba98c", "#b7a280", "#9fa8b5"];

function toTitleCase(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function eventTone(events: ShipmentEvent[]): string {
  const combined = events
    .map((event) => `${event.eventType} ${event.details ?? ""}`.toLowerCase())
    .join(" ");

  if (/delay|slip|extended|wait|stale|hold|risk|demurrage|swap|anomaly/.test(combined)) {
    return "#e24b4a";
  }
  if (/anchor|anchorage|berth|queue|inspection/.test(combined)) {
    return "#d8891c";
  }
  if (/depart|underway|released|sailed|cleared/.test(combined)) {
    return "#4c9b55";
  }
  if (/arrival|arrive|destination|lagos|tin can|apapa|tema|takoradi|abidjan|dakar/.test(combined)) {
    return "#0c7c8c";
  }

  return SELECTED_BASE_COLOR;
}

function stampLabel(events: ShipmentEvent[]): string {
  if (events.length > 1) {
    return `${events.length}`;
  }

  const event = events[0];
  if (!event) {
    return "•";
  }

  return event.eventType
    .split("_")
    .filter(Boolean)
    .slice(0, 1)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("") || "•";
}

function buildTrackPoints(shipment: Shipment): TrackPoint[] {
  const points = [...shipment.historyPoints]
    .sort((left, right) => new Date(left.observedAt).getTime() - new Date(right.observedAt).getTime())
    .map((point) => ({
      latitude: point.latitude,
      longitude: point.longitude,
      observedAt: point.observedAt,
      source: point.source,
    }));

  if (shipment.currentPosition) {
    const latest = points[points.length - 1];
    const shouldAppend = !latest
      || latest.observedAt !== shipment.currentPosition.observedAt
      || latest.latitude !== shipment.currentPosition.latitude
      || latest.longitude !== shipment.currentPosition.longitude;

    if (shouldAppend) {
      points.push({
        latitude: shipment.currentPosition.latitude,
        longitude: shipment.currentPosition.longitude,
        observedAt: shipment.currentPosition.observedAt,
        source: shipment.currentPosition.source,
      });
    }
  }

  return points;
}

function nearestTrackIndex(eventAt: string, points: TrackPoint[]): number {
  const eventTime = new Date(eventAt).getTime();
  let nearestIndex = 0;
  let nearestDistance = Number.POSITIVE_INFINITY;

  points.forEach((point, index) => {
    const distance = Math.abs(new Date(point.observedAt).getTime() - eventTime);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestIndex = index;
    }
  });

  return nearestIndex;
}

function buildEventClusters(shipment: Shipment, points: TrackPoint[]): EventCluster[] {
  if (points.length === 0 || shipment.events.length === 0) {
    return [];
  }

  const byIndex = new Map<number, ShipmentEvent[]>();
  for (const event of shipment.events) {
    const index = nearestTrackIndex(event.eventAt, points);
    byIndex.set(index, [...(byIndex.get(index) ?? []), event]);
  }

  return [...byIndex.entries()]
    .sort((left, right) => left[0] - right[0])
    .map(([index, events]) => ({
      index,
      latitude: points[index].latitude,
      longitude: points[index].longitude,
      color: eventTone(events),
      label: stampLabel(events),
      events,
    }));
}

function buildSegmentColors(points: TrackPoint[], clusters: EventCluster[]): string[] {
  if (points.length < 2) {
    return [];
  }

  const clusterByIndex = new Map(clusters.map((cluster) => [cluster.index, cluster]));
  const colors: string[] = [];
  let activeColor = SELECTED_BASE_COLOR;

  for (let index = 0; index < points.length - 1; index += 1) {
    const startCluster = clusterByIndex.get(index);
    const endCluster = clusterByIndex.get(index + 1);

    if (startCluster) {
      activeColor = startCluster.color;
    }

    colors.push(endCluster?.color ?? activeColor);

    if (endCluster) {
      activeColor = endCluster.color;
    }
  }

  return colors;
}

function eventPopupHtml(shipment: Shipment, cluster: EventCluster) {
  const lines = cluster.events
    .map((event) => {
      const details = event.details ? `: ${event.details}` : "";
      return `<div style="margin-top:6px"><strong>${toTitleCase(event.eventType)}</strong>${details}<br/><span style="color:#6e6e73">${new Date(event.eventAt).toLocaleString()}</span></div>`;
    })
    .join("");

  return `<div style="font-family:-apple-system,sans-serif;font-size:12px;line-height:1.4;min-width:180px"><strong>${shipment.bookingReference}</strong>${lines}</div>`;
}

function vesselPopupHtml(shipment: Shipment) {
  const position = shipment.currentPosition;
  if (!position) {
    return `<div style="font-family:-apple-system,sans-serif;font-size:13px"><strong>${shipment.bookingReference}</strong></div>`;
  }

  const speedText = position.speedKnots != null ? `${position.speedKnots} kn` : "speed unavailable";
  const courseText = position.courseDegrees != null ? `${position.courseDegrees}°` : "course unavailable";

  return `<div style="font-family:-apple-system,sans-serif;font-size:13px"><strong>${position.vesselName ?? shipment.bookingReference}</strong><br/>${speedText} • ${courseText}<br/><span style="color:#6e6e73">via ${position.source}</span></div>`;
}

function eventStampIcon(label: string, color: string, count: number) {
  const badge = count > 1
    ? `<span class="dockie-event-stamp-badge">${count}</span>`
    : "";

  return L.divIcon({
    html: `<div class="dockie-event-stamp" style="background:${color};">${label}${badge}</div>`,
    className: "dockie-event-stamp-wrapper",
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

function vesselIcon(color: string, compact: boolean, subtle = false) {
  const size = compact ? 28 : 34;
  const border = subtle ? 2 : 3;
  const opacity = subtle ? 0.88 : 1;

  return L.divIcon({
    html: `<div style="background:${color};opacity:${opacity};width:${size}px;height:${size}px;border-radius:50%;border:${border}px solid white;box-shadow:0 4px 16px rgba(0,0,0,0.22);display:flex;align-items:center;justify-content:center;">
      <svg width="${compact ? 13 : 16}" height="${compact ? 13 : 16}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M2 21c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1 .6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/><path d="M19.38 20A11.6 11.6 0 0 0 21 14l-9-4-9 4c0 2.9.94 5.34 2.81 7.76"/><path d="M19 13V7a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v6"/><path d="M12 10V4.5"/></svg>
    </div>`,
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

export default function ShipmentMap({
  shipment,
  shipments,
  selectedShipmentId,
  compact = false,
  compactHeightClass = "h-[200px]",
}: ShipmentMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const layerGroupRef = useRef<L.LayerGroup | null>(null);
  const didFitBoundsRef = useRef(false);
  const lastSelectedShipmentIdRef = useRef<string | null>(null);

  const displayedShipments = useMemo(() => {
    const merged = new Map<string, Shipment>();

    for (const item of shipments ?? []) {
      merged.set(item.shipmentId, item);
    }
    merged.set(shipment.shipmentId, shipment);

    return [...merged.values()];
  }, [shipment, shipments]);

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) {
      return;
    }

    const map = L.map(mapRef.current, {
      center: [6.45, 3.39],
      zoom: compact ? 4 : 5,
      zoomControl: !compact,
      attributionControl: false,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(map);

    mapInstanceRef.current = map;
    layerGroupRef.current = L.layerGroup().addTo(map);
    window.setTimeout(() => map.invalidateSize(), 100);

    const resizeObserver = typeof ResizeObserver !== "undefined"
      ? new ResizeObserver(() => {
        window.requestAnimationFrame(() => {
          map.invalidateSize();
        });
      })
      : null;

    if (resizeObserver && mapRef.current) {
      resizeObserver.observe(mapRef.current);
    }

    return () => {
      resizeObserver?.disconnect();
      map.remove();
      mapInstanceRef.current = null;
      layerGroupRef.current = null;
      didFitBoundsRef.current = false;
      lastSelectedShipmentIdRef.current = null;
    };
  }, [compact]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    const layerGroup = layerGroupRef.current;
    if (!map || !layerGroup) {
      return;
    }

    layerGroup.clearLayers();

    const shipmentsWithTrack = displayedShipments
      .map((item) => ({
        shipment: item,
        points: buildTrackPoints(item),
      }))
      .filter((item) => item.points.length > 0 || item.shipment.currentPosition);

    if (shipmentsWithTrack.length === 0) {
      return;
    }

    const selectedId = selectedShipmentId ?? shipment.shipmentId;
    const bounds = L.latLngBounds([]);

    shipmentsWithTrack.forEach(({ shipment: item, points }, index) => {
      const isSelected = item.shipmentId === selectedId;
      const markerColor = isSelected ? SELECTED_BASE_COLOR : OTHER_MARKER_COLORS[index % OTHER_MARKER_COLORS.length];

      points.forEach((point) => bounds.extend([point.latitude, point.longitude]));

      if (isSelected && points.length > 1) {
        const latLngs = points.map((point) => [point.latitude, point.longitude] as [number, number]);
        L.polyline(latLngs, {
          color: "#dce8f7",
          weight: compact ? 6 : 8,
          opacity: 0.96,
          lineCap: "round",
          lineJoin: "round",
        }).addTo(layerGroup);

        const clusters = buildEventClusters(item, points);
        const segmentColors = buildSegmentColors(points, clusters);

        for (let segmentIndex = 0; segmentIndex < points.length - 1; segmentIndex += 1) {
          L.polyline(
            [
              [points[segmentIndex].latitude, points[segmentIndex].longitude],
              [points[segmentIndex + 1].latitude, points[segmentIndex + 1].longitude],
            ],
            {
              color: segmentColors[segmentIndex] ?? SELECTED_BASE_COLOR,
              weight: compact ? 5 : 7,
              opacity: 0.99,
              lineCap: "round",
              lineJoin: "round",
            },
          ).addTo(layerGroup);
        }

        clusters.forEach((cluster) => {
          L.marker([cluster.latitude, cluster.longitude], {
            icon: eventStampIcon(cluster.label, cluster.color, cluster.events.length),
            zIndexOffset: 1200,
            riseOnHover: true,
          })
            .addTo(layerGroup)
            .bindPopup(eventPopupHtml(item, cluster));
        });
      }

      if (item.currentPosition) {
        bounds.extend([item.currentPosition.latitude, item.currentPosition.longitude]);
        L.marker([item.currentPosition.latitude, item.currentPosition.longitude], {
          icon: vesselIcon(markerColor, compact, !isSelected),
          zIndexOffset: isSelected ? 4000 : 2600,
          riseOnHover: true,
        })
          .addTo(layerGroup)
          .bindPopup(vesselPopupHtml(item));
      }
    });

    const selectedShipment = shipmentsWithTrack.find((item) => item.shipment.shipmentId === selectedId) ?? null;
    const selectedBounds = L.latLngBounds([]);

    if (selectedShipment) {
      selectedShipment.points.forEach((point) => selectedBounds.extend([point.latitude, point.longitude]));
      if (selectedShipment.shipment.currentPosition) {
        selectedBounds.extend([selectedShipment.shipment.currentPosition.latitude, selectedShipment.shipment.currentPosition.longitude]);
      }
    }

    const selectedChanged = lastSelectedShipmentIdRef.current !== selectedId;
    const boundsToFit = selectedBounds.isValid() ? selectedBounds : bounds;

    if (boundsToFit.isValid() && (!didFitBoundsRef.current || selectedChanged)) {
      map.fitBounds(boundsToFit.pad(compact ? 0.14 : 0.18));
      didFitBoundsRef.current = true;
    }

    lastSelectedShipmentIdRef.current = selectedId;
    window.setTimeout(() => map.invalidateSize(), 50);
  }, [compact, displayedShipments, selectedShipmentId, shipment.shipmentId]);

  const hasAnyMapData = displayedShipments.some((item) => item.currentPosition || item.historyPoints.length > 0);

  return (
    <div className={`relative overflow-hidden rounded-[12px] ${compact ? compactHeightClass : "flex-1 min-h-[420px]"}`}>
      <div ref={mapRef} className="h-full w-full" />
      {!hasAnyMapData && (
        <div className="absolute inset-0 flex items-center justify-center bg-apple-surface">
          <p className="text-sm text-apple-secondary">No position data available</p>
        </div>
      )}
    </div>
  );
}
