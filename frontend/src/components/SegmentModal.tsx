import { useEffect, useState } from "react";
import { Clock, Gauge, Shield, Circle, Timer, X } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import InteractiveTrackMap from "@/components/InteractiveTrackMap";
import type { TrackSegment } from "@/lib/track-map";
import {
  fetchLapTime,
  fetchTopSpeed,
  fetchTimeLostPerSection,
  fetchBrakingEfficiency,
  fetchGripUtilization,
  type LapTimeResponse,
  type TopSpeedResponse,
  type TimeLostPerSectionResponse,
  type BrakingEfficiencyResponse,
  type GripUtilizationResponse,
  type TimeRange,
} from "@/lib/api";

// Segment timing boundaries (nanoseconds)
const SEGMENT_TIMINGS: Record<string, { slow: TimeRange; fast: TimeRange }> = {
  "Sector 02": {
    slow: { start_ns: "1763219627202000000", end_ns: "1763219658762292711" },
    fast: { start_ns: "1763219835170378101", end_ns: "1763219863046608279" },
  },
  "Sector 03": {
    slow: { start_ns: "1763219658762292711", end_ns: "1763219684415923036" },
    fast: { start_ns: "1763219863046608279", end_ns: "1763219887262000000" },
  },
  "Sector 01": {
    slow: { start_ns: "1763219684415923036", end_ns: "1763219699245616802" },
    fast: { start_ns: "1763219887262000000", end_ns: "1763219900130000000" },
  },
};

// Map display labels to backend segment names for /api/getLapTime
const SEGMENT_NAME_MAP: Record<string, string> = {
  "Sector 01": "corner",
  "Sector 02": "snake",
  "Sector 03": "long",
};

interface SegmentModalProps {
  segment: TrackSegment | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSegmentChange: (segment: TrackSegment) => void;
}

const ratingColor = (rating: string) => {
  switch (rating) {
    case "excellent":
      return "text-green-400";
    case "strong":
      return "text-emerald-400";
    case "fair":
      return "text-yellow-400";
    case "needs_work":
      return "text-red-400";
    default:
      return "text-muted-foreground";
  }
};

const formatLapTime = (seconds: number) => {
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(3);
  return `${m}:${s.padStart(6, "0")}`;
};

const normalizeSectionKey = (value: string) =>
  value.toLowerCase().replace(/[^a-z0-9]/g, "");

const SegmentModal = ({
  segment,
  open,
  onOpenChange,
  onSegmentChange,
}: SegmentModalProps) => {
  const [lapTime, setLapTime] = useState<LapTimeResponse | null>(null);
  const [topSpeed, setTopSpeed] = useState<TopSpeedResponse | null>(null);
  const [timeLost, setTimeLost] = useState<TimeLostPerSectionResponse | null>(
    null,
  );
  const [braking, setBraking] = useState<BrakingEfficiencyResponse | null>(
    null,
  );
  const [grip, setGrip] = useState<GripUtilizationResponse | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!segment || !open) return;
    setLoaded(false);
    setLapTime(null);
    setTopSpeed(null);
    setTimeLost(null);
    setBraking(null);
    setGrip(null);

    const timings = SEGMENT_TIMINGS[segment.label];
    const slowTr = timings?.slow;

    Promise.allSettled([
      fetchLapTime(SEGMENT_NAME_MAP[segment.label] ?? segment.label).then((d) =>
        setLapTime(d),
      ),
      fetchTopSpeed(slowTr).then((d) => setTopSpeed(d)),
      fetchTimeLostPerSection().then((d) => setTimeLost(d)),
      fetchBrakingEfficiency(slowTr).then((d) => setBraking(d)),
      fetchGripUtilization(slowTr).then((d) => setGrip(d)),
    ]).then(() => setLoaded(true));
  }, [segment, open]);

  const slowTopSpeed = topSpeed?.topSpeeds.find((s) => s.race_id === "slow");
  const fastTopSpeed = topSpeed?.topSpeeds.find((s) => s.race_id === "fast");
  const brakingRaw = braking?.brakingEfficiency ?? null;
  const gripRaw = grip?.gripUtilization ?? null;
  const pendingLabel = loaded ? "N/A" : "Loading...";

  const selectedSegmentKey = segment?.label
    ? (SEGMENT_NAME_MAP[segment.label] ?? segment.label)
    : "";

  const selectedBrakingSection =
    brakingRaw?.sections?.find(
      (s) =>
        normalizeSectionKey(s.section) ===
        normalizeSectionKey(selectedSegmentKey),
    ) ??
    brakingRaw?.sections?.find((s) => Boolean(s.race)) ??
    brakingRaw?.sections?.[0];

  const selectedGripSection =
    gripRaw?.sections?.find(
      (s) =>
        normalizeSectionKey(s.section) ===
        normalizeSectionKey(selectedSegmentKey),
    ) ??
    gripRaw?.sections?.find((s) => Boolean(s.race)) ??
    gripRaw?.sections?.[0];

  const brakingStats = brakingRaw
    ? {
        score:
          brakingRaw.score ??
          selectedBrakingSection?.race?.score ??
          selectedBrakingSection?.score ??
          null,
        rating:
          brakingRaw.rating ?? selectedBrakingSection?.race?.rating ?? null,
        timeLostUnderBraking:
          brakingRaw.timeLostUnderBraking ??
          selectedBrakingSection?.race?.timeLostUnderBraking ??
          selectedBrakingSection?.time_lost ??
          null,
        weakestSection:
          brakingRaw.weakestSection ?? selectedBrakingSection?.section ?? null,
        sections: brakingRaw.sections ?? [],
      }
    : null;

  const gripStats = gripRaw
    ? {
        score:
          gripRaw.score ??
          selectedGripSection?.race?.score ??
          selectedGripSection?.score ??
          null,
        rating: gripRaw.rating ?? selectedGripSection?.race?.rating ?? null,
        overallStatus:
          gripRaw.overallStatus ??
          selectedGripSection?.race?.overallStatus ??
          selectedGripSection?.status ??
          null,
        weakestSection:
          gripRaw.weakestSection ?? selectedGripSection?.section ?? null,
        sections: gripRaw.sections ?? [],
      }
    : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[90vw] w-[1200px] h-[80vh] p-0 gap-0 border-border bg-background overflow-hidden">
        <DialogTitle className="sr-only">
          {segment?.label ?? "Segment"} — Sector Analysis
        </DialogTitle>

        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-3">
            <div
              className="h-3 w-3 rounded-full"
              style={{
                backgroundColor: segment?.accent ?? "hsl(var(--primary))",
              }}
            />
            <h2 className="font-display text-lg font-semibold tracking-[0.12em] text-foreground">
              {segment?.label ?? "Sector"}
            </h2>
            <span className="rounded-full border border-border bg-secondary px-3 py-0.5 text-[11px] text-muted-foreground">
              Sector Analysis
            </span>
          </div>
        </div>

        {/* Body: Map left, Metrics right */}
        <div className="flex flex-1 min-h-0">
          {/* Map */}
          <div className="flex-1 min-h-0 border-r border-border p-3">
            <InteractiveTrackMap
              selectedSegmentId={segment?.segmentId}
              onSegmentSelect={onSegmentChange}
              className="h-full min-h-0"
              zoomPadding={8}
              modalOpen={open}
            />
          </div>

          {/* Metrics */}
          <div className="w-[420px] flex flex-col gap-3 p-5 overflow-y-auto">
            {/* Segment Time */}
            <MetricCard
              icon={<Clock className="w-4 h-4 text-primary" />}
              label="Segment Time"
              value={
                lapTime
                  ? formatLapTime(lapTime.slow_race.duration.seconds)
                  : "—"
              }
              sub={
                lapTime
                  ? `+${lapTime.difference.slow_minus_fast.seconds.toFixed(3)}s vs best`
                  : pendingLabel
              }
            />

            {/* Max Speed */}
            <MetricCard
              icon={<Gauge className="w-4 h-4 text-primary" />}
              label="Max Speed"
              value={
                slowTopSpeed
                  ? `${(slowTopSpeed.top_speed_mps * 3.6).toFixed(1)} km/h`
                  : "—"
              }
              sub={
                fastTopSpeed
                  ? `Best: ${(fastTopSpeed.top_speed_mps * 3.6).toFixed(1)} km/h`
                  : pendingLabel
              }
            />

            {/* Braking Efficiency */}
            <MetricCard
              icon={<Shield className="w-4 h-4 text-primary" />}
              label="Braking Efficiency"
              value={
                brakingStats?.score != null
                  ? `${brakingStats.score.toFixed(1)}`
                  : "—"
              }
              badge={
                brakingStats?.rating
                  ? {
                      text: brakingStats.rating.replace("_", " "),
                      className: ratingColor(brakingStats.rating),
                    }
                  : undefined
              }
              sub={
                typeof brakingStats?.timeLostUnderBraking?.seconds === "number"
                  ? `${brakingStats.timeLostUnderBraking.seconds.toFixed(2)}s lost under braking`
                  : pendingLabel
              }
            />

            {/* Grip & Tires */}
            <div className="rounded-xl border border-border bg-card p-4 flex flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <Circle className="w-4 h-4 text-primary" />
                <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium">
                  Grip & Tires
                </span>
              </div>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="font-display text-2xl font-semibold text-foreground tracking-tight">
                  {gripStats?.score != null
                    ? `${gripStats.score.toFixed(1)}`
                    : "—"}
                </span>
                {gripStats?.overallStatus && (
                  <span
                    className={`text-xs font-medium capitalize ${ratingColor(gripStats.rating ?? "")}`}
                  >
                    {gripStats.overallStatus.replace(/_/g, " ")}
                  </span>
                )}
              </div>
              <span className="text-[11px] text-muted-foreground">
                {gripStats?.weakestSection
                  ? `Weakest: ${gripStats.weakestSection}`
                  : pendingLabel}
              </span>
              {Array.isArray(gripStats?.sections) &&
                gripStats.sections.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {gripStats.sections.map((s) => (
                      <span
                        key={s.section}
                        className="text-[10px] text-muted-foreground bg-secondary px-2 py-0.5 rounded font-mono"
                      >
                        {s.section}:{" "}
                        {typeof s.score === "number" ? s.score.toFixed(0) : "—"}
                      </span>
                    ))}
                  </div>
                )}
            </div>

            {/* Time Lost */}
            <div className="rounded-xl border border-border bg-card p-4 flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Timer className="w-4 h-4 text-primary" />
                <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium">
                  Time Lost vs Best
                </span>
              </div>
              {timeLost ? (
                <div className="flex flex-col gap-2">
                  {Object.entries(timeLost.timeLostPerSection).map(
                    ([section, ns]) => {
                      const seconds = Number(ns) / 1_000_000_000;
                      const maxLoss = Math.max(
                        ...Object.values(timeLost.timeLostPerSection).map(
                          (v) => Number(v) / 1_000_000_000,
                        ),
                      );
                      const pct = maxLoss > 0 ? (seconds / maxLoss) * 100 : 0;

                      return (
                        <div key={section} className="flex items-center gap-3">
                          <span className="text-[11px] text-muted-foreground w-14 capitalize font-medium">
                            {section}
                          </span>
                          <div className="flex-1 h-3 bg-secondary rounded-sm overflow-hidden">
                            <div
                              className="h-full bg-primary/70 rounded-sm transition-all duration-500"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="text-xs font-mono text-foreground/80 w-16 text-right">
                            +{seconds.toFixed(3)}s
                          </span>
                        </div>
                      );
                    },
                  )}
                </div>
              ) : (
                <span className="text-[11px] text-muted-foreground">
                  {pendingLabel}
                </span>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

interface MetricCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  badge?: { text: string; className: string };
}

const MetricCard = ({ icon, label, value, sub, badge }: MetricCardProps) => (
  <div className="rounded-xl border border-border bg-card p-4 flex flex-col gap-1">
    <div className="flex items-center gap-2">
      {icon}
      <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium">
        {label}
      </span>
    </div>
    <div className="flex items-baseline gap-2 mt-1">
      <span className="font-display text-2xl font-semibold text-foreground tracking-tight">
        {value}
      </span>
      {badge && (
        <span className={`text-xs font-medium capitalize ${badge.className}`}>
          {badge.text}
        </span>
      )}
    </div>
    <span className="text-[11px] text-muted-foreground">{sub}</span>
  </div>
);

export default SegmentModal;
