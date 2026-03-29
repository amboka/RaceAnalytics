import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, RotateCcw } from "lucide-react";
import { fetchTrajectories, type TrajectoriesResponse } from "@/lib/api";
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

export interface AnalysisMistakeMarker {
  /** 0-1 position along the lap where the mistake happened */
  lapPosition: number;
  severity: "critical" | "warning" | "minor";
}

interface AnalysisTrackMapProps {
  className?: string;
  /** 0-1 progress along the lap, drives the car marker position */
  lapProgress?: number;
  /** Optional explicit marker position from backend frame metadata */
  currentPosition?: { x: number; y: number } | null;
  /** Mistakes to highlight on the track */
  mistakes?: AnalysisMistakeMarker[];
}

const boundsToViewBox = (bounds: TrackBounds): ViewBox => ({
  x: bounds.minX,
  y: bounds.minY,
  width: bounds.width,
  height: bounds.height,
});

const pointsToString = (points: [number, number][]) =>
  points.map(([x, y]) => `${x},${y}`).join(" ");

const DRAG_THRESHOLD_PX = 8;

const TRAJECTORY_COLORS = {
  current: "#facc15",
  best: "#22d3ee",
};

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

const SEVERITY_COLORS: Record<string, string> = {
  critical: "rgba(239, 68, 68, 0.55)",
  warning: "rgba(250, 204, 21, 0.45)",
  minor: "rgba(96, 165, 250, 0.4)",
};

const useTrackTrajectories = () => {
  const [data, setData] = useState<TrajectoriesResponse | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetchTrajectories("0", "1")
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return data;
};

/** Interpolate a position along a polyline given progress 0-1 */
const getPointAtProgress = (
  points: { x_m: number; y_m: number }[],
  progress: number,
): { x: number; y: number } | null => {
  if (points.length < 2) return null;
  const clamped = Math.max(0, Math.min(1, progress));
  const idx = clamped * (points.length - 1);
  const i = Math.floor(idx);
  const t = idx - i;
  const a = points[Math.min(i, points.length - 1)];
  const b = points[Math.min(i + 1, points.length - 1)];
  return {
    x: a.x_m + (b.x_m - a.x_m) * t,
    y: a.y_m + (b.y_m - a.y_m) * t,
  };
};

const AnalysisTrackMapGraphic = ({
  data,
  className,
  lapProgress = 0,
  currentPosition = null,
  mistakes = [],
}: {
  data: TrackMapData;
  className?: string;
  lapProgress?: number;
  currentPosition?: { x: number; y: number } | null;
  mistakes?: AnalysisMistakeMarker[];
}) => {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragState = useRef<{
    x: number;
    y: number;
    viewBox: ViewBox;
    hasDragged: boolean;
  } | null>(null);

  const trajectories = useTrackTrajectories();

  const baseViewBox = useMemo(
    () => boundsToViewBox(padBounds(data.bounds, 56)),
    [data.bounds],
  );
  const mirrorAxisY = useMemo(
    () => data.bounds.minY + data.bounds.maxY,
    [data.bounds.maxY, data.bounds.minY],
  );
  const [viewBox, setViewBox] = useState<ViewBox>(baseViewBox);

  const currentLapPoints = trajectories?.currentLap.points ?? [];
  const bestLapPoints = trajectories?.bestLap.points ?? [];

  // Map mistakes to segments: each mistake has a lapPosition (0-1),
  // distribute across segments proportionally
  const segmentMistakeColor = useMemo(() => {
    const totalSegments = data.segments.length;
    if (totalSegments === 0) return {};
    const colors: Record<number, string> = {};
    for (const m of mistakes) {
      // Which segment index does this lap position fall into?
      const segIdx = Math.min(
        Math.floor(m.lapPosition * totalSegments),
        totalSegments - 1,
      );
      const segId = data.segments[segIdx].segmentId;
      // Higher severity wins
      const existing = colors[segId];
      if (
        !existing ||
        m.severity === "critical" ||
        (m.severity === "warning" && !existing.includes("239"))
      ) {
        colors[segId] = SEVERITY_COLORS[m.severity];
      }
    }
    return colors;
  }, [mistakes, data.segments]);

  // Car marker position:
  // 1) explicit backend x/y from current frame
  // 2) fallback to trajectory interpolation by lap progress
  const carPos = useMemo(() => {
    if (currentPosition) {
      return currentPosition;
    }
    if (currentLapPoints.length > 1) {
      return getPointAtProgress(currentLapPoints, lapProgress);
    }
    // Fallback: generate a placeholder position along the track polygon
    if (data.trackPolygon.length > 2) {
      const pts = data.trackPolygon;
      const idx = Math.floor(lapProgress * (pts.length - 1));
      const t = lapProgress * (pts.length - 1) - idx;
      const a = pts[Math.min(idx, pts.length - 1)];
      const b = pts[Math.min(idx + 1, pts.length - 1)];
      return { x: a[0] + (b[0] - a[0]) * t, y: a[1] + (b[1] - a[1]) * t };
    }
    return null;
  }, [currentPosition, currentLapPoints, lapProgress, data.trackPolygon]);

  const toWorldPoint = (
    clientX: number,
    clientY: number,
    current = viewBox,
  ) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return null;
    return {
      x: current.x + ((clientX - rect.left) / rect.width) * current.width,
      y: current.y + ((clientY - rect.top) / rect.height) * current.height,
    };
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
      <div className="absolute right-3 top-3 z-20">
        <button
          type="button"
          onClick={() => setViewBox(baseViewBox)}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-black/45 text-slate-100 backdrop-blur transition hover:border-white/25 hover:bg-black/65"
          aria-label="Reset view"
        >
          <RotateCcw className="h-3 w-3" />
        </button>
      </div>

      {/* Legend */}
      <div className="absolute left-3 bottom-3 z-20 space-y-1 rounded-lg border border-white/10 bg-black/45 px-2.5 py-2 backdrop-blur text-[10px]">
        <div className="flex items-center gap-2 text-slate-400">
          <span
            className="h-[2px] w-4 rounded-full"
            style={{ background: TRAJECTORY_COLORS.current, opacity: 0.95 }}
          />
          Your lap
        </div>
        <div className="flex items-center gap-2 text-slate-400">
          <span
            className="h-[2px] w-4 rounded-full"
            style={{ background: TRAJECTORY_COLORS.best }}
          />
          Best lap
        </div>
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
        <defs>
          <filter id="currentGlow" x="-40%" y="-40%" width="180%" height="180%">
            <feDropShadow
              dx="0"
              dy="0"
              stdDeviation="3"
              floodColor="#facc15"
              floodOpacity="0.5"
            />
          </filter>
          <filter id="bestGlow" x="-40%" y="-40%" width="180%" height="180%">
            <feDropShadow
              dx="0"
              dy="0"
              stdDeviation="3"
              floodColor="#22d3ee"
              floodOpacity="0.5"
            />
          </filter>
          <filter
            id="markerGlow"
            x="-100%"
            y="-100%"
            width="300%"
            height="300%"
          >
            <feDropShadow
              dx="0"
              dy="0"
              stdDeviation="6"
              floodColor="#ffffff"
              floodOpacity="0.7"
            />
          </filter>
        </defs>

        <g transform={`translate(0 ${mirrorAxisY}) scale(1 -1)`}>
          {/* Base track */}
          <polygon
            points={pointsToString(data.trackPolygon)}
            fill="rgba(15, 23, 42, 0.52)"
            stroke="rgba(148, 163, 184, 0.16)"
            strokeWidth={3}
            vectorEffect="non-scaling-stroke"
          />
          <polyline
            points={pointsToString(data.leftBorder)}
            fill="none"
            stroke="rgba(255,255,255,0.12)"
            strokeWidth={0.4}
            vectorEffect="non-scaling-stroke"
          />
          <polyline
            points={pointsToString(data.rightBorder)}
            fill="none"
            stroke="rgba(255,255,255,0.12)"
            strokeWidth={0.4}
            vectorEffect="non-scaling-stroke"
          />

          {/* Segments — only colored where mistakes occurred */}
          {data.segments.map((segment) => {
            const mistakeColor = segmentMistakeColor[segment.segmentId];
            return (
              <polygon
                key={segment.segmentId}
                points={pointsToString(segment.polygon)}
                fill={mistakeColor || "transparent"}
                stroke="rgba(255,255,255,0.06)"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
            );
          })}

          {/* Best lap trajectory */}
          {bestLapPoints.length > 1 && (
            <polyline
              points={pointsToString(bestLapPoints.map((p) => [p.x_m, p.y_m]))}
              fill="none"
              stroke={TRAJECTORY_COLORS.best}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
              opacity={0.9}
              filter="url(#bestGlow)"
              className="pointer-events-none"
            />
          )}

          {/* Current lap trajectory */}
          {currentLapPoints.length > 1 && (
            <polyline
              points={pointsToString(
                currentLapPoints.map((p) => [p.x_m, p.y_m]),
              )}
              fill="none"
              stroke={TRAJECTORY_COLORS.current}
              strokeWidth={2}
              strokeDasharray="2 5"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
              opacity={0.95}
              filter="url(#currentGlow)"
              className="pointer-events-none"
            />
          )}

          {/* Car marker */}
          {carPos && (
            <g filter="url(#markerGlow)" className="pointer-events-none">
              <circle
                cx={carPos.x}
                cy={carPos.y}
                r={8}
                fill="#ffffff"
                opacity={0.95}
              />
              <circle
                cx={carPos.x}
                cy={carPos.y}
                r={4}
                fill="hsl(0, 85%, 50%)"
              />
              {/* Pulsing ring */}
              <circle
                cx={carPos.x}
                cy={carPos.y}
                r={14}
                fill="none"
                stroke="#ffffff"
                strokeWidth={1.5}
                opacity={0.3}
                vectorEffect="non-scaling-stroke"
              />
            </g>
          )}
        </g>
      </svg>
    </div>
  );
};

const AnalysisTrackMap = ({
  className,
  lapProgress = 0,
  currentPosition = null,
  mistakes = [],
}: AnalysisTrackMapProps) => {
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
          Loading track…
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

  return (
    <AnalysisTrackMapGraphic
      data={data}
      className={className}
      lapProgress={lapProgress}
      currentPosition={currentPosition}
      mistakes={mistakes}
    />
  );
};

export default AnalysisTrackMap;
