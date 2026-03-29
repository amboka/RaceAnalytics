import { useMemo, useRef, useState } from "react";
import { Loader2, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  padBounds,
  type TrackBounds,
  type TrackMapData,
  useTrackMapData,
} from "@/lib/track-map";

interface ViewBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface MistakeMarker {
  sector: number;
  severity: "critical" | "warning" | "minor";
}

interface HeatmapTrackMapProps {
  className?: string;
  mistakes?: MistakeMarker[];
}

const SEVERITY_WEIGHT: Record<string, number> = {
  critical: 1,
  warning: 0.5,
  minor: 0.18,
};

// Seeded pseudo-random per segment for stable "randomness"
const seededRandom = (seed: number) => {
  const x = Math.sin(seed * 9301 + 49297) * 49297;
  return x - Math.floor(x);
};

// Maps 0-1 heat → color. 0 = transparent (no fill), low = blue tint, mid = yellow, high = red
const heatToColor = (heat: number): string => {
  if (heat <= 0) return "transparent";
  const clamped = Math.min(heat, 1);
  if (clamped <= 0.35) {
    const t = clamped / 0.35;
    return `rgba(96, 165, 250, ${(t * 0.45).toFixed(2)})`;
  }
  if (clamped <= 0.65) {
    const t = (clamped - 0.35) / 0.3;
    const r = Math.round(96 + (250 - 96) * t);
    const g = Math.round(165 + (200 - 165) * t);
    const b = Math.round(250 - (250 - 50) * t);
    return `rgba(${r},${g},${b},0.5)`;
  }
  const t = (clamped - 0.65) / 0.35;
  const r = Math.round(250 - (250 - 239) * t);
  const g = Math.round(200 - (200 - 68) * t);
  const b = Math.round(50 + (68 - 50) * t);
  return `rgba(${r},${g},${b},0.6)`;
};

const boundsToViewBox = (bounds: TrackBounds): ViewBox => ({
  x: bounds.minX,
  y: bounds.minY,
  width: bounds.width,
  height: bounds.height,
});

const pointsToString = (points: [number, number][]) =>
  points.map(([x, y]) => `${x},${y}`).join(" ");

const DRAG_THRESHOLD_PX = 8;

const clampViewBox = (next: ViewBox, base: ViewBox) => {
  const minWidth = base.width * 0.18;
  const maxWidth = base.width * 2.6;
  const width = Math.min(Math.max(next.width, minWidth), maxWidth);
  const height = Math.min(
    Math.max(next.height, minWidth * (base.height / base.width)),
    maxWidth * (base.height / base.width),
  );
  return { x: next.x, y: next.y, width, height };
};

const HeatmapGraphic = ({
  data,
  mistakes = [],
  className,
}: {
  data: TrackMapData;
  mistakes?: MistakeMarker[];
  className?: string;
}) => {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragState = useRef<{
    x: number;
    y: number;
    viewBox: ViewBox;
    hasDragged: boolean;
  } | null>(null);

  const baseViewBox = useMemo(
    () => boundsToViewBox(padBounds(data.bounds, 56)),
    [data.bounds],
  );
  const mirrorAxisY = useMemo(
    () => data.bounds.minY + data.bounds.maxY,
    [data.bounds.maxY, data.bounds.minY],
  );
  const [viewBox, setViewBox] = useState<ViewBox>(baseViewBox);

  // Compute heat per segment — use synthetic per-segment distribution
  const segmentHeats = useMemo(() => {
    // Base heat from actual mistakes mapped to sectors
    const sectorHeats: Record<number, number> = {};
    for (const m of mistakes) {
      sectorHeats[m.sector] = (sectorHeats[m.sector] ?? 0) + (SEVERITY_WEIGHT[m.severity] ?? 0);
    }

    // Distribute across segments with some randomness — not all segments get heat
    const heats: Record<number, number> = {};
    for (const seg of data.segments) {
      const sectorHeat = sectorHeats[seg.segmentId] ?? 0;
      const rand = seededRandom(seg.segmentId * 7 + 3);
      // ~40% of clean segments stay clean
      if (sectorHeat === 0 && rand < 0.4) {
        heats[seg.segmentId] = 0;
      } else if (sectorHeat === 0) {
        // Slight random heat for some segments
        heats[seg.segmentId] = rand * 0.25;
      } else {
        heats[seg.segmentId] = sectorHeat;
      }
    }

    const maxHeat = Math.max(...Object.values(heats), 0.01);
    const normalized: Record<number, number> = {};
    for (const [k, v] of Object.entries(heats)) {
      normalized[Number(k)] = v / maxHeat;
    }
    return normalized;
  }, [mistakes, data.segments]);

  const toWorldPoint = (
    clientX: number,
    clientY: number,
    current = viewBox,
  ) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return null;
    const x = current.x + ((clientX - rect.left) / rect.width) * current.width;
    const y = current.y + ((clientY - rect.top) / rect.height) * current.height;
    return { x, y };
  };

  const setZoom = (factor: number, clientX?: number, clientY?: number) => {
    setViewBox((current) => {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return current;
      const fallback = {
        x: current.x + current.width / 2,
        y: current.y + current.height / 2,
      };
      const wp =
        typeof clientX === "number" && typeof clientY === "number"
          ? (toWorldPoint(clientX, clientY, current) ?? fallback)
          : fallback;
      const width = current.width * factor;
      const height = current.height * factor;
      return clampViewBox(
        {
          x: wp.x - ((wp.x - current.x) / current.width) * width,
          y: wp.y - ((wp.y - current.y) / current.height) * height,
          width,
          height,
        },
        baseViewBox,
      );
    });
  };

  return (
    <div
      className={cn(
        "relative h-full w-full overflow-hidden rounded-[1.25rem] bg-[#06070c]",
        className,
      )}
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.08),transparent_32%),linear-gradient(180deg,rgba(17,24,39,0.92),rgba(4,6,12,1))]" />
      <div className="pointer-events-none absolute inset-0 opacity-30 [background-image:linear-gradient(rgba(148,163,184,0.12)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.12)_1px,transparent_1px)] [background-size:40px_40px]" />

      {/* Reset button */}
      <div className="absolute right-4 top-4 z-20">
        <button
          type="button"
          onClick={() => setViewBox(baseViewBox)}
          className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-black/45 text-slate-100 backdrop-blur transition hover:border-white/25 hover:bg-black/65"
          aria-label="Reset view"
        >
          <RotateCcw className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Legend */}
      <div className="absolute left-4 bottom-4 z-20 flex items-center gap-2 rounded-full border border-white/10 bg-black/45 px-3 py-1.5 backdrop-blur">
        <span className="text-[10px] text-slate-400">Clean</span>
        <div className="h-2 w-20 rounded-full" style={{ background: "linear-gradient(90deg, rgba(255,255,255,0.3), #60a5fa, #facc15, #ef4444)" }} />
        <span className="text-[10px] text-slate-400">Critical</span>
      </div>

      <svg
        ref={svgRef}
        className="relative z-10 h-full w-full touch-none"
        viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
        onWheel={(e) => {
          e.preventDefault();
          setZoom(e.deltaY < 0 ? 0.88 : 1.14, e.clientX, e.clientY);
        }}
        onPointerDown={(e) => {
          dragState.current = {
            x: e.clientX,
            y: e.clientY,
            viewBox,
            hasDragged: false,
          };
          (e.currentTarget as SVGSVGElement).setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (!dragState.current || !svgRef.current) return;
          const dx = e.clientX - dragState.current.x;
          const dy = e.clientY - dragState.current.y;
          if (
            !dragState.current.hasDragged &&
            Math.abs(dx) < DRAG_THRESHOLD_PX &&
            Math.abs(dy) < DRAG_THRESHOLD_PX
          )
            return;
          dragState.current.hasDragged = true;
          const rect = svgRef.current.getBoundingClientRect();
          setViewBox({
            ...dragState.current.viewBox,
            x:
              dragState.current.viewBox.x -
              (dx / rect.width) * dragState.current.viewBox.width,
            y:
              dragState.current.viewBox.y -
              (dy / rect.height) * dragState.current.viewBox.height,
          });
        }}
        onPointerUp={() => {
          dragState.current = null;
        }}
        onPointerLeave={() => {
          dragState.current = null;
        }}
      >
        <g transform={`translate(0 ${mirrorAxisY}) scale(1 -1)`}>
          {/* Base track — subtle fill with white borders */}
          <polygon
            points={pointsToString(data.trackPolygon)}
            fill="rgba(15, 23, 42, 0.4)"
            stroke="rgba(255, 255, 255, 0.18)"
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
          />

          {/* Segment heatmap overlays */}
          {data.segments.map((segment) => {
            const heat = segmentHeats[segment.segmentId] ?? 0;
            return (
              <polygon
                key={segment.segmentId}
                points={pointsToString(segment.polygon)}
                fill={heatToColor(heat)}
                stroke="rgba(255,255,255,0.12)"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
            );
          })}

          {/* White borders */}
          <polyline
            points={pointsToString(data.leftBorder)}
            fill="none"
            stroke="rgba(255,255,255,0.2)"
            strokeWidth={0.6}
            vectorEffect="non-scaling-stroke"
          />
          <polyline
            points={pointsToString(data.rightBorder)}
            fill="none"
            stroke="rgba(255,255,255,0.2)"
            strokeWidth={0.6}
            vectorEffect="non-scaling-stroke"
          />
        </g>
      </svg>
    </div>
  );
};

const HeatmapTrackMap = ({ className, mistakes = [] }: HeatmapTrackMapProps) => {
  const { data, loading, error } = useTrackMapData();

  if (loading) {
    return (
      <div
        className={cn(
          "flex h-full w-full items-center justify-center rounded-[1.25rem] border border-white/10 bg-card/40",
          className,
        )}
      >
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading track map...
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div
        className={cn(
          "flex h-full w-full items-center justify-center rounded-[1.25rem] border border-destructive/20 bg-destructive/5 px-6 text-center",
          className,
        )}
      >
        <p className="max-w-sm text-sm text-destructive">
          {error ?? "Unable to load the track map."}
        </p>
      </div>
    );
  }

  return <HeatmapGraphic data={data} mistakes={mistakes} className={className} />;
};

export default HeatmapTrackMap;
