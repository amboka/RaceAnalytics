import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Map, Minus, Move, Plus, RotateCcw } from "lucide-react";
import { fetchTrajectories, type TrajectoriesResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  padBounds,
  type TrackBounds,
  type TrackMapData,
  type TrackSegment,
  useTrackMapData,
} from "@/lib/track-map";

interface ViewBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface InteractiveTrackMapProps {
  className?: string;
  selectedSegmentId?: number;
  onSegmentSelect?: (segment: TrackSegment) => void;
  zoomPadding?: number;
  modalOpen?: boolean;
}

const boundsToViewBox = (bounds: TrackBounds): ViewBox => ({
  x: bounds.minX,
  y: bounds.minY,
  width: bounds.width,
  height: bounds.height,
});

const pointsToString = (points: [number, number][]) =>
  points.map(([x, y]) => `${x},${y}`).join(" ");
const mirrorY = (y: number, axisY: number) => axisY - y;

const DRAG_THRESHOLD_PX = 8;
const TRAJECTORY_COLORS = {
  current: "#facc15",
  best: "#22d3ee",
};

const getSegmentFill = (
  segment: TrackSegment,
  hovered: boolean,
  selected: boolean,
) => {
  if (selected) return `${segment.accent}dd`;
  if (hovered) return `${segment.accent}b8`;
  return `${segment.accent}82`;
};

const getSegmentStroke = (
  segment: TrackSegment,
  hovered: boolean,
  selected: boolean,
) => {
  if (selected) return "#ffffff";
  if (hovered) return segment.accent;
  return "#f8fafc";
};

const clampViewBox = (next: ViewBox, base: ViewBox) => {
  const minWidth = base.width * 0.18;
  const maxWidth = base.width * 2.6;
  const width = Math.min(Math.max(next.width, minWidth), maxWidth);
  const height = Math.min(
    Math.max(next.height, minWidth * (base.height / base.width)),
    maxWidth * (base.height / base.width),
  );

  return {
    x: next.x,
    y: next.y,
    width,
    height,
  };
};

const useTrackTrajectories = () => {
  const [data, setData] = useState<TrajectoriesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchTrajectories("0", "1")
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
      })
      .catch((reason: Error) => {
        if (cancelled) return;
        console.error("❌ Trajectories fetch failed:", reason);
        setError(reason.message || "Unable to load trajectories.");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { data, error };
};

const TrackMapGraphic = ({
  data,
  selectedSegmentId,
  onSegmentSelect,
  className,
  zoomPadding = 52,
  modalOpen = true,
}: {
  data: TrackMapData;
  selectedSegmentId?: number;
  onSegmentSelect?: (segment: TrackSegment) => void;
  className?: string;
  zoomPadding?: number;
  modalOpen?: boolean;
}) => {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragState = useRef<{
    x: number;
    y: number;
    viewBox: ViewBox;
    hasDragged: boolean;
  } | null>(null);
  const suppressClickRef = useRef(false);
  const pointerDownSegmentIdRef = useRef<number | null>(null);
  const hoveredSegmentIdRef = useRef<number | null>(null);
  const prevModalOpenRef = useRef(modalOpen);
  const [hoveredSegmentId, setHoveredSegmentId] = useState<number | null>(null);
  const { data: trajectories, error: trajectoryError } = useTrackTrajectories();

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

  useEffect(() => {
    const wasModalClosed = !prevModalOpenRef.current;
    const isModalOpenNow = modalOpen;
    const justOpened = wasModalClosed && isModalOpenNow;

    prevModalOpenRef.current = modalOpen;

    // Only recenter when selected segment changes or modal just opened
    if (justOpened || selectedSegmentId !== undefined) {
      const selectedSegment = data.segments.find(
        (segment) => segment.segmentId === selectedSegmentId,
      );
      if (selectedSegment) {
        setViewBox(
          boundsToViewBox(padBounds(selectedSegment.bounds, zoomPadding)),
        );
        return;
      }
    }

    if (!modalOpen) {
      setViewBox(baseViewBox);
    }
  }, [baseViewBox, data.segments, modalOpen, selectedSegmentId, zoomPadding]);

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

      const fallbackCenter = {
        x: current.x + current.width / 2,
        y: current.y + current.height / 2,
      };
      const worldPoint =
        typeof clientX === "number" && typeof clientY === "number"
          ? (toWorldPoint(clientX, clientY, current) ?? fallbackCenter)
          : fallbackCenter;

      const width = current.width * factor;
      const height = current.height * factor;
      const originX =
        worldPoint.x - ((worldPoint.x - current.x) / current.width) * width;
      const originY =
        worldPoint.y - ((worldPoint.y - current.y) / current.height) * height;

      return clampViewBox(
        {
          x: originX,
          y: originY,
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

      <div className="absolute left-4 top-4 z-20 flex flex-wrap items-center gap-2">
        <div className="rounded-full border border-white/10 bg-black/45 px-3 py-1.5 text-[11px] uppercase tracking-[0.18em] text-slate-300 backdrop-blur">
          Yas Marina Explorer
        </div>
        <div className="rounded-full border border-white/10 bg-black/35 px-3 py-1.5 text-[11px] text-slate-400 backdrop-blur">
          Scroll to zoom
        </div>
        <div className="rounded-full border border-white/10 bg-black/35 px-3 py-1.5 text-[11px] text-slate-400 backdrop-blur">
          Drag to pan
        </div>
        <div className="rounded-full border border-white/10 bg-black/35 px-3 py-1.5 text-[11px] text-slate-400 backdrop-blur">
          Race 0 vs Race 1
        </div>
      </div>

      <div className="absolute right-4 top-4 z-20 flex flex-col gap-2">
        <button
          type="button"
          onClick={() => setZoom(0.82)}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-black/45 text-slate-100 backdrop-blur transition hover:border-white/25 hover:bg-black/65"
          aria-label="Zoom in"
        >
          <Plus className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() => setZoom(1.2)}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-black/45 text-slate-100 backdrop-blur transition hover:border-white/25 hover:bg-black/65"
          aria-label="Zoom out"
        >
          <Minus className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() => {
            const selectedSegment = data.segments.find(
              (segment) => segment.segmentId === selectedSegmentId,
            );
            setViewBox(
              selectedSegment
                ? boundsToViewBox(padBounds(selectedSegment.bounds, 52))
                : baseViewBox,
            );
          }}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-black/45 text-slate-100 backdrop-blur transition hover:border-white/25 hover:bg-black/65"
          aria-label="Reset view"
        >
          <RotateCcw className="h-4 w-4" />
        </button>
      </div>

      <div className="absolute bottom-4 left-4 z-20 flex flex-wrap gap-2">
        {data.segments.map((segment) => {
          const active = selectedSegmentId === segment.segmentId;
          return (
            <button
              key={segment.segmentId}
              type="button"
              onClick={() => onSegmentSelect?.(segment)}
              className={cn(
                "rounded-full border px-3 py-1.5 text-xs font-medium backdrop-blur transition",
                active
                  ? "border-white/30 bg-white/12 text-white"
                  : "border-white/10 bg-black/35 text-slate-300 hover:border-white/25 hover:bg-white/8",
              )}
            >
              {segment.label}
            </button>
          );
        })}
      </div>

      <svg
        ref={svgRef}
        className="relative z-10 h-full w-full touch-none"
        viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`}
        onWheel={(event) => {
          event.preventDefault();
          setZoom(event.deltaY < 0 ? 0.88 : 1.14, event.clientX, event.clientY);
        }}
        onPointerDown={(event) => {
          dragState.current = {
            x: event.clientX,
            y: event.clientY,
            viewBox,
            hasDragged: false,
          };
          suppressClickRef.current = false;

          if (event.target === event.currentTarget) {
            pointerDownSegmentIdRef.current = null;
          }

          (event.currentTarget as SVGSVGElement).setPointerCapture(
            event.pointerId,
          );
        }}
        onPointerMove={(event) => {
          if (!dragState.current || !svgRef.current) return;

          const deltaX = event.clientX - dragState.current.x;
          const deltaY = event.clientY - dragState.current.y;
          const movedEnough =
            Math.abs(deltaX) >= DRAG_THRESHOLD_PX ||
            Math.abs(deltaY) >= DRAG_THRESHOLD_PX;

          if (!dragState.current.hasDragged && !movedEnough) {
            return;
          }

          dragState.current.hasDragged = true;
          suppressClickRef.current = true;

          const rect = svgRef.current.getBoundingClientRect();
          const dx = (deltaX / rect.width) * dragState.current.viewBox.width;
          const dy = (deltaY / rect.height) * dragState.current.viewBox.height;
          setViewBox({
            ...dragState.current.viewBox,
            x: dragState.current.viewBox.x - dx,
            y: dragState.current.viewBox.y - dy,
          });
        }}
        onPointerUp={() => {
          const didDrag = dragState.current?.hasDragged ?? false;
          const downSegmentId = pointerDownSegmentIdRef.current;
          dragState.current = null;
          pointerDownSegmentIdRef.current = null;

          if (!didDrag && downSegmentId !== null) {
            const clickedSegment = data.segments.find(
              (segment) => segment.segmentId === downSegmentId,
            );
            if (clickedSegment) {
              suppressClickRef.current = true;
              onSegmentSelect?.(clickedSegment);
              return;
            }
          }

          window.setTimeout(() => {
            suppressClickRef.current = false;
          }, 0);
        }}
        onPointerLeave={() => {
          dragState.current = null;
          pointerDownSegmentIdRef.current = null;
          if (hoveredSegmentIdRef.current !== null) {
            hoveredSegmentIdRef.current = null;
            setHoveredSegmentId(null);
          }
        }}
      >
        <defs>
          <filter id="segmentGlow" x="-40%" y="-40%" width="180%" height="180%">
            <feDropShadow
              dx="0"
              dy="0"
              stdDeviation="18"
              floodColor="#ff5c57"
              floodOpacity="0.22"
            />
          </filter>
          <filter
            id="currentTrajectoryGlow"
            x="-40%"
            y="-40%"
            width="180%"
            height="180%"
          >
            <feDropShadow
              dx="0"
              dy="0"
              stdDeviation="3"
              floodColor="#facc15"
              floodOpacity="0.5"
            />
          </filter>
          <filter
            id="bestTrajectoryGlow"
            x="-40%"
            y="-40%"
            width="180%"
            height="180%"
          >
            <feDropShadow
              dx="0"
              dy="0"
              stdDeviation="3"
              floodColor="#22d3ee"
              floodOpacity="0.5"
            />
          </filter>
        </defs>

        <g transform={`translate(0 ${mirrorAxisY}) scale(1 -1)`}>
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

          {data.segments.map((segment) => {
            const hovered = hoveredSegmentId === segment.segmentId;
            const selected = selectedSegmentId === segment.segmentId;

            return (
              <g
                key={segment.segmentId}
                filter={selected ? "url(#segmentGlow)" : undefined}
              >
                <polygon
                  points={pointsToString(segment.polygon)}
                  fill={getSegmentFill(segment, hovered, selected)}
                  stroke={getSegmentStroke(segment, hovered, selected)}
                  strokeWidth={selected ? 6 : 3}
                  vectorEffect="non-scaling-stroke"
                  className="cursor-pointer transition-all duration-200"
                  onMouseEnter={() => {
                    hoveredSegmentIdRef.current = segment.segmentId;
                    setHoveredSegmentId(segment.segmentId);
                  }}
                  onMouseLeave={() => {
                    hoveredSegmentIdRef.current = null;
                    setHoveredSegmentId(null);
                  }}
                  onPointerDown={() => {
                    pointerDownSegmentIdRef.current = segment.segmentId;
                  }}
                />
              </g>
            );
          })}

          {bestLapPoints.length > 1 && (
            <polyline
              points={pointsToString(
                bestLapPoints.map((point) => [point.x_m, point.y_m]),
              )}
              fill="none"
              stroke={TRAJECTORY_COLORS.best}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
              opacity={0.9}
              filter="url(#bestTrajectoryGlow)"
              className="pointer-events-none"
            />
          )}

          {currentLapPoints.length > 1 && (
            <polyline
              points={pointsToString(
                currentLapPoints.map((point) => [point.x_m, point.y_m]),
              )}
              fill="none"
              stroke={TRAJECTORY_COLORS.current}
              strokeWidth={2}
              strokeDasharray="2 5"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
              opacity={0.95}
              filter="url(#currentTrajectoryGlow)"
              className="pointer-events-none"
            />
          )}
        </g>

        {data.segments.map((segment) => {
          const selected = selectedSegmentId === segment.segmentId;

          return (
            <g
              key={`${segment.segmentId}-label`}
              transform={`translate(${segment.center.x}, ${mirrorY(segment.center.y, mirrorAxisY)})`}
              className="pointer-events-none"
            >
              <circle
                r={selected ? 34 : 28}
                fill="rgba(2, 6, 23, 0.72)"
                stroke={
                  selected ? "rgba(255,255,255,0.32)" : "rgba(255,255,255,0.14)"
                }
                strokeWidth={2}
                vectorEffect="non-scaling-stroke"
              />
              <text
                textAnchor="middle"
                dy="-2"
                fill="#f8fafc"
                fontSize="20"
                fontWeight="700"
                letterSpacing="0.14em"
              >
                {String(segment.segmentId).padStart(2, "0")}
              </text>
              <text
                textAnchor="middle"
                dy="16"
                fill="rgba(226,232,240,0.7)"
                fontSize="8"
                letterSpacing="0.24em"
              >
                ZONE
              </text>
            </g>
          );
        })}
      </svg>

      <div className="pointer-events-none absolute bottom-4 right-4 z-20 rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-[11px] text-slate-300 backdrop-blur">
        <div className="flex items-center gap-2">
          <Map className="h-3.5 w-3.5 text-slate-400" />
          Click a sector to open its page
        </div>
        <div className="mt-1 flex items-center gap-2 text-slate-500">
          <Move className="h-3.5 w-3.5" />
          Interactive canvas
        </div>
        <div className="mt-2 space-y-1 text-slate-400">
          <div className="flex items-center gap-2">
            <span
              className="h-[2px] w-6 rounded-full"
              style={{ background: "#facc15", opacity: 0.95 }}
            />
            Current lap (race 0)
          </div>
          <div className="flex items-center gap-2">
            <span
              className="h-[2px] w-6 rounded-full"
              style={{ background: "#22d3ee" }}
            />
            Best lap (race 1)
          </div>
          {trajectoryError && (
            <div className="max-w-[220px] text-[10px] text-amber-300/85">
              {trajectoryError}
            </div>
          )}
          {!trajectoryError &&
            currentLapPoints.length === 0 &&
            bestLapPoints.length === 0 && (
              <div className="max-w-[220px] text-[10px] text-slate-500">
                No trajectory data loaded in the local database yet.
              </div>
            )}
        </div>
      </div>
    </div>
  );
};

const InteractiveTrackMap = ({
  className,
  selectedSegmentId,
  onSegmentSelect,
  zoomPadding,
  modalOpen,
}: InteractiveTrackMapProps) => {
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
          Loading Yas Marina map...
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
    <TrackMapGraphic
      data={data}
      selectedSegmentId={selectedSegmentId}
      onSegmentSelect={onSegmentSelect}
      className={className}
      zoomPadding={zoomPadding}
      modalOpen={modalOpen}
    />
  );
};

export default InteractiveTrackMap;
