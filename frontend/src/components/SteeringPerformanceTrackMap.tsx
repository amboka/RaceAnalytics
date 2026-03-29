import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  padBounds,
  type TrackBounds,
  type TrackMapData,
  useTrackMapData,
} from "@/lib/track-map";
import {
  fetchTrajectories,
  type OverUnderSteerResponse,
  type SlipCoachingResponse,
  type SteeringAngleResponse,
  type TrajectoriesResponse,
} from "@/lib/api";

interface ViewBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface SteeringPerformanceTrackMapProps {
  className?: string;
  steeringData: SteeringAngleResponse | null;
  overUnderData: OverUnderSteerResponse | null;
  slipData: SlipCoachingResponse | null;
  cursorProgress?: number;
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

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

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

const getPointAtProgress = (
  points: { x_m: number; y_m: number }[],
  progress: number,
): { x: number; y: number } | null => {
  if (points.length < 2) return null;
  const clamped = clamp01(progress);
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

const buildSegmentPerformance = (
  data: TrackMapData,
  steeringData: SteeringAngleResponse | null,
  overUnderData: OverUnderSteerResponse | null,
  slipData: SlipCoachingResponse | null,
): Record<number, number> => {
  const segmentCount = data.segments.length;
  if (segmentCount === 0) return {};

  const slowSteering = steeringData?.races.find((r) => r.raceId === "slow");
  const fastSteering = steeringData?.races.find((r) => r.raceId === "fast");
  const balanceRace =
    overUnderData?.races.find((r) => r.raceId === "slow") ??
    overUnderData?.races[0];
  const slipRace =
    slipData?.races.find((r) => r.raceId === "slow") ?? slipData?.races[0];

  const sampleCount =
    slowSteering?.sampleCount ??
    balanceRace?.sampleCount ??
    slipRace?.sampleCount ??
    0;

  if (sampleCount === 0) {
    return Object.fromEntries(data.segments.map((s) => [s.segmentId, 0]));
  }

  const targetSlip = slipData?.config?.targetSlipDeg ?? 6;
  const slipWindow = slipData?.config?.slipWindowDeg ?? 2;

  const classPenalty: Record<string, number> = {
    oversteer: 0.7,
    understeer: 0.65,
    neutral: 0.08,
    not_cornering: 0.03,
  };

  const sums = new Array<number>(segmentCount).fill(0);
  const counts = new Array<number>(segmentCount).fill(0);

  for (let i = 0; i < sampleCount; i += 1) {
    const progress = sampleCount > 1 ? i / (sampleCount - 1) : 0;
    const segIdx = Math.min(
      Math.floor(clamp01(progress) * segmentCount),
      segmentCount - 1,
    );

    const parts: Array<{ value: number; weight: number }> = [];

    const slowDeg = slowSteering?.series.steeringAngleDeg[i];
    const fastDeg = fastSteering?.series.steeringAngleDeg[i];
    if (Number.isFinite(slowDeg) && Number.isFinite(fastDeg)) {
      const steeringPenalty = clamp01(
        Math.abs((slowDeg as number) - (fastDeg as number)) / 32,
      );
      parts.push({ value: steeringPenalty, weight: 0.3 });
    }

    const balanceScore = balanceRace?.series.balanceScore[i];
    const balanceClass = balanceRace?.series.balanceClass[i] ?? "not_cornering";
    const isCornering = balanceRace?.series.isCornering[i] ?? false;
    if (Number.isFinite(balanceScore)) {
      const scorePenalty = clamp01(Math.abs(balanceScore as number) / 0.35);
      const statePenalty = classPenalty[balanceClass] ?? 0.25;
      const combined = scorePenalty * 0.65 + statePenalty * 0.35;
      parts.push({
        value: isCornering ? combined : combined * 0.35,
        weight: 0.35,
      });
    }

    const maxSlip = slipRace?.series.maxSlipDeg[i];
    const coachingState = (
      slipRace?.series.coachingState[i] ?? ""
    ).toLowerCase();
    if (Number.isFinite(maxSlip)) {
      const slipValue = maxSlip as number;
      let slipPenalty = 0;
      if (slipValue < targetSlip - slipWindow) {
        slipPenalty = clamp01(
          (targetSlip - slipWindow - slipValue) / Math.max(targetSlip, 1),
        );
      } else if (slipValue > targetSlip + slipWindow) {
        slipPenalty = clamp01(
          (slipValue - (targetSlip + slipWindow)) /
            (targetSlip + slipWindow + 2),
        );
      } else {
        slipPenalty =
          clamp01(
            Math.abs(slipValue - targetSlip) / Math.max(slipWindow * 2, 1),
          ) * 0.25;
      }

      let stateBoost = 0;
      if (coachingState.includes("over") || coachingState.includes("limit"))
        stateBoost = 0.35;
      else if (coachingState.includes("below")) stateBoost = 0.2;
      else if (coachingState.includes("optimal")) stateBoost = 0.03;

      parts.push({ value: clamp01(slipPenalty + stateBoost), weight: 0.35 });
    }

    if (parts.length === 0) continue;

    const weightSum = parts.reduce((sum, p) => sum + p.weight, 0);
    const score =
      parts.reduce((sum, p) => sum + p.value * p.weight, 0) / weightSum;
    sums[segIdx] += score;
    counts[segIdx] += 1;
  }

  const perSegment = sums.map((sum, idx) =>
    counts[idx] > 0 ? sum / counts[idx] : 0,
  );
  const smoothed = perSegment.map((value, idx) => {
    const prev = perSegment[Math.max(0, idx - 1)];
    const next = perSegment[Math.min(perSegment.length - 1, idx + 1)];
    return prev * 0.25 + value * 0.5 + next * 0.25;
  });

  const maxValue = Math.max(...smoothed, 0.01);
  const output: Record<number, number> = {};
  for (let i = 0; i < segmentCount; i += 1) {
    output[data.segments[i].segmentId] = clamp01(smoothed[i] / maxValue);
  }

  return output;
};

const SteeringPerformanceGraphic = ({
  data,
  className,
  steeringData,
  overUnderData,
  slipData,
  cursorProgress = 0,
}: {
  data: TrackMapData;
  className?: string;
  steeringData: SteeringAngleResponse | null;
  overUnderData: OverUnderSteerResponse | null;
  slipData: SlipCoachingResponse | null;
  cursorProgress?: number;
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
  const trajectories = useTrackTrajectories();
  const currentLapPoints = trajectories?.currentLap.points ?? [];
  const bestLapPoints = trajectories?.bestLap.points ?? [];

  const segmentPerformance = useMemo(
    () => buildSegmentPerformance(data, steeringData, overUnderData, slipData),
    [data, steeringData, overUnderData, slipData],
  );

  const carPos = useMemo(() => {
    if (currentLapPoints.length > 1) {
      return getPointAtProgress(currentLapPoints, cursorProgress);
    }
    return null;
  }, [currentLapPoints, cursorProgress]);

  const hasData = Boolean(steeringData || overUnderData || slipData);

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

      {!hasData && (
        <div className="pointer-events-none absolute left-4 top-4 z-20 rounded-md border border-white/10 bg-black/45 px-2.5 py-1.5 text-[10px] text-slate-400 backdrop-blur">
          Waiting for steering telemetry...
        </div>
      )}

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
          ) {
            return;
          }
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
          <filter
            id="steeringCurrentGlow"
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
            id="steeringBestGlow"
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
          <filter
            id="steeringMarkerGlow"
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
          <polygon
            points={pointsToString(data.trackPolygon)}
            fill="rgba(15, 23, 42, 0.4)"
            stroke="rgba(255, 255, 255, 0.18)"
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
          />

          {data.segments.map((segment) => {
            const score = segmentPerformance[segment.segmentId] ?? 0;
            return (
              <polygon
                key={segment.segmentId}
                points={pointsToString(segment.polygon)}
                fill={heatToColor(score)}
                stroke="rgba(255,255,255,0.12)"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
            );
          })}

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
              filter="url(#steeringBestGlow)"
              className="pointer-events-none"
            />
          )}

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
              filter="url(#steeringCurrentGlow)"
              className="pointer-events-none"
            />
          )}

          {carPos && (
            <g
              filter="url(#steeringMarkerGlow)"
              className="pointer-events-none"
            >
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

const SteeringPerformanceTrackMap = ({
  className,
  steeringData,
  overUnderData,
  slipData,
  cursorProgress = 0,
}: SteeringPerformanceTrackMapProps) => {
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

  return (
    <SteeringPerformanceGraphic
      data={data}
      className={className}
      steeringData={steeringData}
      overUnderData={overUnderData}
      slipData={slipData}
      cursorProgress={cursorProgress}
    />
  );
};

export default SteeringPerformanceTrackMap;
