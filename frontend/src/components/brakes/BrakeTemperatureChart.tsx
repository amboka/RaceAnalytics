import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { BrakeTemperatureComparisonResponse } from "@/lib/api";

interface Props {
  data: BrakeTemperatureComparisonResponse | null;
  cursorIndex: number | null;
}

const BrakeTemperatureChart = ({ data, cursorIndex }: Props) => {
  const chartData = useMemo(() => {
    if (!data) return [];
    const { distanceM, lapTempC, referenceTempC, deltaTempC } = data.series;
    return distanceM.map((d, i) => ({
      distance: Math.round(d),
      lap: lapTempC?.[i] ?? null,
      ref: referenceTempC?.[i] ?? null,
      delta: deltaTempC?.[i] ?? null,
    }));
  }, [data]);

  const cursorDistance = cursorIndex !== null && chartData[cursorIndex]
    ? chartData[cursorIndex].distance
    : null;

  if (!data) {
    return (
      <div className="border border-border rounded-lg bg-card flex items-center justify-center">
        <span className="text-muted-foreground text-xs">Loading brake temperature…</span>
      </div>
    );
  }

  return (
    <div className="border border-border rounded-lg bg-card flex flex-col min-h-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <div className="flex items-center gap-2">
          <div className="w-1 h-4 rounded-full" style={{ background: "hsl(30, 90%, 50%)" }} />
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium">
            Brake Temperature
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-0.5 rounded-full bg-primary inline-block" /> Your Lap
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-0.5 rounded-full inline-block" style={{ background: "hsl(160, 70%, 50%)" }} /> Best Lap
          </span>
          {data.peaks && (
            <span className="ml-1 text-foreground/60">
              Peak: {data.peaks.lap.maxTempC.toFixed(0)}°C (+{data.peaks.deltaMaxTempC.toFixed(1)}°)
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 min-h-0 px-2 pb-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 14%, 18%)" vertical={false} />
            {cursorDistance !== null && (
              <ReferenceLine x={cursorDistance} stroke="hsl(0, 0%, 60%)" strokeWidth={1} strokeDasharray="3 2" />
            )}
            <XAxis
              dataKey="distance"
              stroke="hsl(220, 10%, 35%)"
              tick={{ fontSize: 9, fill: "hsl(220, 10%, 55%)" }}
              tickLine={false}
              axisLine={false}
              label={{ value: "Distance (m)", position: "insideBottomRight", offset: -2, fontSize: 9, fill: "hsl(220, 10%, 45%)" }}
            />
            <YAxis
              stroke="hsl(220, 10%, 35%)"
              tick={{ fontSize: 9, fill: "hsl(220, 10%, 55%)" }}
              tickLine={false}
              axisLine={false}
              width={36}
              label={{ value: "°C", angle: -90, position: "insideLeft", fontSize: 9, fill: "hsl(220, 10%, 45%)" }}
            />
            <Tooltip
              contentStyle={{
                background: "hsl(220, 18%, 10%)",
                border: "1px solid hsl(220, 14%, 18%)",
                borderRadius: 6, fontSize: 11, color: "hsl(0, 0%, 85%)",
              }}
              labelFormatter={(v) => `${v}m`}
              formatter={(value: number, name: string) => [
                `${value.toFixed(1)}°C`,
                name === "lap" ? "Your Lap" : name === "ref" ? "Best Lap" : "Δ Temp",
              ]}
            />
            <Line type="monotone" dataKey="ref" stroke="hsl(160, 70%, 50%)" strokeWidth={1.5} dot={false} strokeOpacity={0.7} />
            <Line type="monotone" dataKey="lap" stroke="hsl(30, 90%, 55%)" strokeWidth={1.5} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default BrakeTemperatureChart;
