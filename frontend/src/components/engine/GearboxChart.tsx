import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { GearboxComparisonResponse } from "@/lib/api";

interface Props {
  data: GearboxComparisonResponse | null;
  cursorIndex: number | null;
}

const GearboxChart = ({ data, cursorIndex }: Props) => {
  const chartData = useMemo(() => {
    if (!data) return [];
    const { distanceM, lapGear, referenceGear, lapSpeedMps, referenceSpeedMps } = data.series;
    return distanceM.map((d, i) => ({
      distance: Math.round(d),
      lapGear: lapGear[i],
      refGear: referenceGear[i],
      lapSpeed: Number((lapSpeedMps[i] * 3.6).toFixed(1)),
      refSpeed: Number((referenceSpeedMps[i] * 3.6).toFixed(1)),
    }));
  }, [data]);

  const cursorDistance = cursorIndex !== null && chartData[cursorIndex]
    ? chartData[cursorIndex].distance
    : null;

  if (!data) {
    return (
      <div className="border border-border rounded-lg bg-card flex items-center justify-center">
        <span className="text-muted-foreground text-xs">Loading gearbox data…</span>
      </div>
    );
  }

  const summary = data.summary;

  return (
    <div className="border border-border rounded-lg bg-card flex flex-col min-h-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <div className="flex items-center gap-2">
          <div className="w-1 h-4 rounded-full bg-primary" />
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium">
            Gearbox & Shift Comparison
          </span>
        </div>
        <div className="flex items-center gap-4 text-[10px] text-muted-foreground">
          <span>Early: <span className="text-foreground font-mono">{summary.earlierShiftCount}</span></span>
          <span>Late: <span className="text-foreground font-mono">{summary.laterShiftCount}</span></span>
          <span>Mismatches: <span className="text-foreground font-mono">{summary.mismatchZoneCount}</span></span>
        </div>
      </div>

      <div className="flex-1 min-h-0 px-2 pb-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 14%, 18%)" vertical={false} />
            {cursorDistance !== null && (
              <ReferenceLine yAxisId="gear" x={cursorDistance} stroke="hsl(0, 0%, 60%)" strokeWidth={1} strokeDasharray="3 2" />
            )}
            <XAxis
              dataKey="distance"
              stroke="hsl(220, 10%, 35%)"
              tick={{ fontSize: 9, fill: "hsl(220, 10%, 55%)" }}
              tickLine={false} axisLine={false}
              label={{ value: "Distance (m)", position: "insideBottomRight", offset: -2, fontSize: 9, fill: "hsl(220, 10%, 45%)" }}
            />
            <YAxis yAxisId="gear" domain={[1, 8]} stroke="hsl(220, 10%, 35%)" tick={{ fontSize: 9, fill: "hsl(220, 10%, 55%)" }} tickLine={false} axisLine={false} width={24} label={{ value: "Gear", angle: -90, position: "insideLeft", fontSize: 9, fill: "hsl(220, 10%, 45%)" }} />
            <YAxis yAxisId="speed" orientation="right" stroke="hsl(220, 10%, 35%)" tick={{ fontSize: 9, fill: "hsl(220, 10%, 40%)" }} tickLine={false} axisLine={false} width={36} label={{ value: "km/h", angle: 90, position: "insideRight", fontSize: 9, fill: "hsl(220, 10%, 40%)" }} />
            <Tooltip
              contentStyle={{ background: "hsl(220, 18%, 10%)", border: "1px solid hsl(220, 14%, 18%)", borderRadius: 6, fontSize: 11, color: "hsl(0, 0%, 85%)" }}
              labelFormatter={(v) => `${v}m`}
              formatter={(value: number, name: string) => {
                const labels: Record<string, string> = { lapGear: "Your Gear", refGear: "Ref Gear", lapSpeed: "Your Speed", refSpeed: "Ref Speed" };
                const unit = name.includes("Speed") ? " km/h" : "";
                return [`${value}${unit}`, labels[name] || name];
              }}
            />
            <Line yAxisId="gear" type="stepAfter" dataKey="refGear" stroke="hsl(160, 70%, 50%)" strokeWidth={1.5} dot={false} strokeOpacity={0.7} />
            <Line yAxisId="gear" type="stepAfter" dataKey="lapGear" stroke="hsl(0, 85%, 55%)" strokeWidth={1.5} dot={false} />
            <Line yAxisId="speed" type="monotone" dataKey="refSpeed" stroke="hsl(160, 70%, 50%)" strokeWidth={1} dot={false} strokeOpacity={0.25} strokeDasharray="4 3" />
            <Line yAxisId="speed" type="monotone" dataKey="lapSpeed" stroke="hsl(0, 85%, 55%)" strokeWidth={1} dot={false} strokeOpacity={0.25} strokeDasharray="4 3" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default GearboxChart;
