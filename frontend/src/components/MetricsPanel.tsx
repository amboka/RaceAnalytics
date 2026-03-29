import { useEffect, useState } from "react";
import { Clock, Gauge, Shield, Circle, Timer, AlertTriangle, Info } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
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
} from "@/lib/api";

const ratingColor = (rating: string) => {
  switch (rating) {
    case "excellent": return "text-green-400";
    case "strong": return "text-emerald-400";
    case "fair": return "text-yellow-400";
    case "needs_work": return "text-red-400";
    default: return "text-muted-foreground";
  }
};

const statusLabel = (s: string) => s.replace(/_/g, " ");

const formatLapTime = (seconds: number) => {
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(3);
  return `${m}:${s.padStart(6, "0")}`;
};

const BRAKING_TOOLTIP = `Braking Efficiency measures how effectively the driver decelerates before each corner. It evaluates brake timing, pressure consistency, and speed scrubbed relative to the optimal braking point. A higher score means less time lost under braking. The weakest section highlights where the most improvement is possible.`;

const GRIP_TOOLTIP = `Grip Utilization measures how effectively available tire grip is being used through each track section. It compares lateral and longitudinal forces against the tire's grip envelope. "Underutilizing" means the driver could push harder; "Overutilizing" indicates potential slides or lockups. Each section is scored independently.`;

const MetricsPanel = () => {
  const [lapTime, setLapTime] = useState<LapTimeResponse | null>(null);
  const [topSpeed, setTopSpeed] = useState<TopSpeedResponse | null>(null);
  const [timeLost, setTimeLost] = useState<TimeLostPerSectionResponse | null>(null);
  const [braking, setBraking] = useState<BrakingEfficiencyResponse | null>(null);
  const [grip, setGrip] = useState<GripUtilizationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    Promise.allSettled([
      fetchLapTime().then(d => setLapTime(d)),
      fetchTopSpeed().then(d => setTopSpeed(d)),
      fetchTimeLostPerSection().then(d => setTimeLost(d)),
      fetchBrakingEfficiency().then(d => setBraking(d)),
      fetchGripUtilization().then(d => setGrip(d)),
    ]).then((results) => {
      const failed = results.filter((result): result is PromiseRejectedResult => result.status === "rejected");
      setLoaded(true);
      if (failed.length === 0) return;

      if (failed.length === results.length) {
        setError("Unable to reach API");
        return;
      }

      const details = failed
        .map(result => result.reason instanceof Error ? result.reason.message : "Unknown API error")
        .join(" • ");
      setError(`Some metrics are unavailable: ${details}`);
    });
  }, []);

  const slowTopSpeed = topSpeed?.topSpeeds.find(s => s.race_id === "slow");
  const fastTopSpeed = topSpeed?.topSpeeds.find(s => s.race_id === "fast");
  const brakingStats = braking?.brakingEfficiency ?? null;
  const gripStats = grip?.gripUtilization ?? null;
  const pendingLabel = loaded ? "Unavailable" : "Loading...";

  return (
    <TooltipProvider delayDuration={100}>
      <div className="flex flex-col gap-2.5 min-h-0 h-full">
        {error && (
          <div className="flex items-center gap-2 px-3 py-2 bg-destructive/10 border border-destructive/20 rounded-md">
            <AlertTriangle className="w-3.5 h-3.5 text-destructive" />
            <span className="text-xs text-destructive">{error}</span>
          </div>
        )}

        {/* Top row - 3 cards */}
        <div className="grid grid-cols-3 gap-2.5 flex-1">
          <MetricCard
            icon={<Clock className="w-3.5 h-3.5 text-primary/60" />}
            label="Lap Time"
            value={lapTime ? formatLapTime(lapTime.slow_race.duration.seconds) : "—"}
            sub={lapTime ? `+${lapTime.difference.slow_minus_fast.seconds.toFixed(3)}s vs fast` : pendingLabel}
          />
          <MetricCard
            icon={<Gauge className="w-3.5 h-3.5 text-primary/60" />}
            label="Max Speed"
            value={slowTopSpeed ? `${(slowTopSpeed.top_speed_mps * 3.6).toFixed(1)} km/h` : "—"}
            sub={fastTopSpeed ? `Fast: ${(fastTopSpeed.top_speed_mps * 3.6).toFixed(1)} km/h` : pendingLabel}
          />
          <MetricCard
            icon={<Shield className="w-3.5 h-3.5 text-primary/60" />}
            label="Braking"
            tooltip={BRAKING_TOOLTIP}
            value={brakingStats ? `${brakingStats.score.toFixed(1)}` : "—"}
            badge={brakingStats ? {
              text: brakingStats.rating.replace("_", " "),
              className: ratingColor(brakingStats.rating),
            } : undefined}
            sub={brakingStats
              ? `${brakingStats.timeLostUnderBraking.seconds.toFixed(2)}s lost · weak: ${brakingStats.weakestSection}`
              : pendingLabel}
          />
        </div>

        {/* Bottom row */}
        <div className="grid grid-cols-5 gap-2.5 flex-1">
          {/* Grip & Tires */}
          <div className="col-span-2 bg-card border border-border rounded-lg p-4 flex flex-col justify-center gap-1">
            <div className="flex items-center gap-2">
              <Circle className="w-3.5 h-3.5 text-primary/60" />
              <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium">Grip & Tires</span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Info className="w-3 h-3 text-muted-foreground/50 hover:text-muted-foreground cursor-help transition-colors ml-auto" />
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-xs text-xs leading-relaxed">
                  {GRIP_TOOLTIP}
                </TooltipContent>
              </Tooltip>
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="font-display text-xl font-semibold text-foreground tracking-tight">
                {gripStats ? `${gripStats.score.toFixed(1)}` : "—"}
              </span>
              {gripStats && (
                <span className={`text-xs font-medium capitalize ${ratingColor(gripStats.rating)}`}>
                  {statusLabel(gripStats.overallStatus)}
                </span>
              )}
            </div>
            <span className="text-[11px] text-muted-foreground">
              {gripStats ? `Weakest: ${gripStats.weakestSection}` : pendingLabel}
            </span>
            {gripStats && (
              <div className="flex gap-1.5 mt-1.5">
                {gripStats.sections.map(s => (
                  <span key={s.section} className="text-[10px] text-muted-foreground bg-secondary px-2 py-0.5 rounded font-mono">
                    {s.section}: {s.score.toFixed(0)}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Time Lost Per Corner */}
          <div className="col-span-3 bg-card border border-border rounded-lg p-4 flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <Timer className="w-3.5 h-3.5 text-primary/60" />
              <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium">Time Lost Per Corner</span>
            </div>
            {timeLost ? (
              <div className="flex flex-col gap-2 flex-1 justify-center">
                {Object.entries(timeLost.timeLostPerSection).map(([section, ns]) => {
                  const seconds = Number(ns) / 1_000_000_000;
                  const maxLoss = Math.max(
                    ...Object.values(timeLost.timeLostPerSection).map(v => Number(v) / 1_000_000_000)
                  );
                  const pct = maxLoss > 0 ? (seconds / maxLoss) * 100 : 0;

                  return (
                    <div key={section} className="flex items-center gap-3">
                      <span className="text-[11px] text-muted-foreground w-14 capitalize font-medium">{section}</span>
                      <div className="flex-1 h-3.5 bg-secondary rounded-sm overflow-hidden">
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
                })}
              </div>
            ) : (
              <span className="text-[11px] text-muted-foreground">{pendingLabel}</span>
            )}
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
};

/* Reusable metric card */
interface MetricCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  tooltip?: string;
  badge?: { text: string; className: string };
}

const MetricCard = ({ icon, label, value, sub, tooltip, badge }: MetricCardProps) => (
  <div className="bg-card border border-border rounded-lg p-4 flex flex-col justify-center gap-1">
    <div className="flex items-center gap-2">
      {icon}
      <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium">{label}</span>
      {tooltip && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Info className="w-3 h-3 text-muted-foreground/50 hover:text-muted-foreground cursor-help transition-colors ml-auto" />
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs text-xs leading-relaxed">
            {tooltip}
          </TooltipContent>
        </Tooltip>
      )}
    </div>
    <div className="flex items-baseline gap-2 mt-1">
      <span className="font-display text-xl font-semibold text-foreground tracking-tight">{value}</span>
      {badge && (
        <span className={`text-xs font-medium capitalize ${badge.className}`}>{badge.text}</span>
      )}
    </div>
    <span className="text-[11px] text-muted-foreground">{sub}</span>
  </div>
);

export default MetricsPanel;
