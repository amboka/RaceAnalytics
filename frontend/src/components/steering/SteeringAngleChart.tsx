import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { SteeringAngleResponse } from "@/lib/api";

interface Props {
  data: SteeringAngleResponse | null;
  cursorIndex: number | null;
}

const SteeringAngleChart = ({ data, cursorIndex }: Props) => {
  const chartData = useMemo(() => {
    if (!data || data.races.length < 2) return [];
    const slow = data.races.find((r) => r.raceId === "slow");
    const fast = data.races.find((r) => r.raceId === "fast");
    if (!slow || !fast) return [];

    const len = Math.min(slow.sampleCount, fast.sampleCount);
    return Array.from({ length: len }, (_, i) => ({
      index: i,
      lap: slow.series.steeringAngleDeg[i],
      ref: fast.series.steeringAngleDeg[i],
    }));
  }, [data]);

  const cursorX = cursorIndex !== null && chartData[cursorIndex] ? cursorIndex : null;

  if (!data) {
    return (
      <div className="border border-border rounded-lg bg-card flex items-center justify-center">
        <span className="text-muted-foreground text-xs">Loading steering angle…</span>
      </div>
    );
  }

  return (
    <div className="border border-border rounded-lg bg-card flex flex-col min-h-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <div className="flex items-center gap-2">
          <div className="w-1 h-4 rounded-full bg-primary" />
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium">
            Steering Angle
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-0.5 rounded-full bg-primary inline-block" /> Your Lap
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-0.5 rounded-full inline-block" style={{ background: "hsl(160, 70%, 50%)" }} /> Best Lap
          </span>
        </div>
      </div>

      <div className="flex-1 min-h-0 px-2 pb-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 14%, 18%)" vertical={false} />
            {cursorX !== null && (
              <ReferenceLine x={cursorX} stroke="hsl(0, 0%, 60%)" strokeWidth={1} strokeDasharray="3 2" />
            )}
            <XAxis
              dataKey="index"
              stroke="hsl(220, 10%, 35%)"
              tick={{ fontSize: 9, fill: "hsl(220, 10%, 55%)" }}
              tickLine={false}
              axisLine={false}
              label={{ value: "Sample", position: "insideBottomRight", offset: -2, fontSize: 9, fill: "hsl(220, 10%, 45%)" }}
            />
            <YAxis
              stroke="hsl(220, 10%, 35%)"
              tick={{ fontSize: 9, fill: "hsl(220, 10%, 55%)" }}
              tickLine={false}
              axisLine={false}
              width={36}
              label={{ value: "deg", angle: -90, position: "insideLeft", fontSize: 9, fill: "hsl(220, 10%, 45%)" }}
            />
            <Tooltip
              contentStyle={{
                background: "hsl(220, 18%, 10%)",
                border: "1px solid hsl(220, 14%, 18%)",
                borderRadius: 6, fontSize: 11, color: "hsl(0, 0%, 85%)",
              }}
              formatter={(value: number, name: string) => [
                `${value.toFixed(2)}°`,
                name === "lap" ? "Your Lap" : "Best Lap",
              ]}
            />
            <Line type="monotone" dataKey="ref" stroke="hsl(160, 70%, 50%)" strokeWidth={1.5} dot={false} strokeOpacity={0.7} />
            <Line type="monotone" dataKey="lap" stroke="hsl(0, 85%, 55%)" strokeWidth={1.5} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default SteeringAngleChart;
