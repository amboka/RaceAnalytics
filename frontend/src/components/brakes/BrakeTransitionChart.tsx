import { useMemo, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { BrakeTransitionResponse } from "@/lib/api";

interface Props {
  data: BrakeTransitionResponse | null;
}

const classColor: Record<string, string> = {
  smooth: "text-green-400",
  hesitant: "text-yellow-400",
  delayed: "text-orange-400",
  abrupt: "text-destructive",
  overlap: "text-blue-400",
};

const BrakeTransitionChart = ({ data }: Props) => {
  const [selectedZone, setSelectedZone] = useState(0);

  const detail = data?.selectedZoneDetail;

  const chartData = useMemo(() => {
    if (!detail) return [];
    return detail.lap.localProgress.map((lp, i) => ({
      progress: Number(lp.toFixed(3)),
      lapBrake: detail.lap.brakePressure[i],
      lapThrottle: detail.lap.throttlePct[i],
      refBrake: detail.reference.brakePressure[i],
      refThrottle: detail.reference.throttlePct[i],
    }));
  }, [detail]);

  const zones = data?.zones ?? [];
  const activeZone = zones[selectedZone];

  if (!data) {
    return (
      <div className="border border-border rounded-lg bg-card flex items-center justify-center h-full">
        <span className="text-muted-foreground text-xs">Loading brake transition…</span>
      </div>
    );
  }

  return (
    <div className="border border-border rounded-lg bg-card flex flex-col min-h-0 overflow-hidden h-full">
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <div className="flex items-center gap-2">
          <div className="w-1 h-4 rounded-full" style={{ background: "hsl(200, 70%, 55%)" }} />
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium">
            Brake → Throttle Transition
          </span>
        </div>
        <div className="flex items-center gap-2">
          {zones.map((z, i) => (
            <button
              key={z.zoneId}
              onClick={() => setSelectedZone(i)}
              className={`text-[9px] px-1.5 py-0.5 rounded font-mono transition-colors ${
                i === selectedZone
                  ? "bg-primary/20 text-primary"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Z{z.zoneId}
            </button>
          ))}
        </div>
      </div>

      {activeZone && (
        <div className="flex items-center gap-4 px-4 pb-1 text-[10px] text-muted-foreground">
          <span>
            Gap: <span className="text-foreground">{activeZone.transition.brakeToThrottleGapS.toFixed(2)}s</span>
          </span>
          <span>
            Smoothness: <span className="text-foreground">{activeZone.transition.smoothnessScore.toFixed(0)}</span>
          </span>
          <span className={classColor[activeZone.transition.classification] ?? "text-muted-foreground"}>
            {activeZone.transition.classification}
          </span>
          {activeZone.delta && (
            <span className="text-foreground/50">
              Δsmooth {activeZone.delta.smoothnessScore > 0 ? "+" : ""}{activeZone.delta.smoothnessScore.toFixed(1)}
            </span>
          )}
        </div>
      )}

      <div className="flex-1 min-h-0 px-2 pb-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 14%, 18%)" vertical={false} />
            <ReferenceLine x={0} stroke="hsl(0, 0%, 40%)" strokeWidth={1} label={{ value: "Apex", fontSize: 9, fill: "hsl(0, 0%, 50%)", position: "top" }} />
            {detail && (
              <>
                <ReferenceLine x={Number(detail.lap.markers.brakeRelease.toFixed(3))} stroke="hsl(0, 85%, 50%)" strokeDasharray="4 2" strokeWidth={1} />
                <ReferenceLine x={Number(detail.lap.markers.throttleApplication.toFixed(3))} stroke="hsl(120, 60%, 50%)" strokeDasharray="4 2" strokeWidth={1} />
              </>
            )}
            <XAxis
              dataKey="progress"
              type="number"
              domain={[-1, 1]}
              stroke="hsl(220, 10%, 35%)"
              tick={{ fontSize: 9, fill: "hsl(220, 10%, 55%)" }}
              tickLine={false}
              axisLine={false}
              label={{ value: "← Entry | Apex | Exit →", position: "insideBottomRight", offset: -2, fontSize: 9, fill: "hsl(220, 10%, 45%)" }}
            />
            <YAxis
              domain={[0, "auto"]}
              stroke="hsl(220, 10%, 35%)"
              tick={{ fontSize: 9, fill: "hsl(220, 10%, 55%)" }}
              tickLine={false}
              axisLine={false}
              width={32}
            />
            <Tooltip
              contentStyle={{
                background: "hsl(220, 18%, 10%)",
                border: "1px solid hsl(220, 14%, 18%)",
                borderRadius: 6, fontSize: 11, color: "hsl(0, 0%, 85%)",
              }}
              formatter={(value: number, name: string) => {
                const labels: Record<string, string> = {
                  lapBrake: "Brake (You)",
                  refBrake: "Brake (Ref)",
                  lapThrottle: "Throttle (You)",
                  refThrottle: "Throttle (Ref)",
                };
                return [value.toFixed(2), labels[name] ?? name];
              }}
            />
            <Line type="monotone" dataKey="refBrake" stroke="hsl(160, 70%, 50%)" strokeWidth={1.2} dot={false} strokeOpacity={0.5} strokeDasharray="4 2" />
            <Line type="monotone" dataKey="lapBrake" stroke="hsl(0, 85%, 55%)" strokeWidth={1.5} dot={false} />
            <Line type="monotone" dataKey="refThrottle" stroke="hsl(160, 70%, 50%)" strokeWidth={1.2} dot={false} strokeOpacity={0.5} />
            <Line type="monotone" dataKey="lapThrottle" stroke="hsl(120, 60%, 55%)" strokeWidth={1.5} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default BrakeTransitionChart;
