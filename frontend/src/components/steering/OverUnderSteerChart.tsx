import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { OverUnderSteerResponse } from "@/lib/api";

interface Props {
  data: OverUnderSteerResponse | null;
  cursorIndex: number | null;
}

const classColor: Record<string, string> = {
  understeer: "hsl(45, 90%, 55%)",
  oversteer: "hsl(0, 85%, 55%)",
  neutral: "hsl(160, 70%, 50%)",
  not_cornering: "hsl(220, 10%, 40%)",
};

const OverUnderSteerChart = ({ data, cursorIndex }: Props) => {
  // Show first race (slow) for now; could be toggled
  const race = data?.races.find((r) => r.raceId === "slow") ?? data?.races[0];

  const chartData = useMemo(() => {
    if (!race) return [];
    return race.series.balanceScore.map((score, i) => ({
      index: i,
      score,
      balanceClass: race.series.balanceClass[i],
      isCornering: race.series.isCornering[i],
    }));
  }, [race]);

  const cursorX = cursorIndex !== null && chartData[cursorIndex] ? cursorIndex : null;

  if (!data) {
    return (
      <div className="border border-border rounded-lg bg-card flex items-center justify-center">
        <span className="text-muted-foreground text-xs">Loading over/understeer…</span>
      </div>
    );
  }

  return (
    <div className="border border-border rounded-lg bg-card flex flex-col min-h-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <div className="flex items-center gap-2">
          <div className="w-1 h-4 rounded-full bg-primary" />
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium">
            Over / Understeer
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full inline-block" style={{ background: classColor.oversteer }} /> Oversteer
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full inline-block" style={{ background: classColor.understeer }} /> Understeer
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full inline-block" style={{ background: classColor.neutral }} /> Neutral
          </span>
        </div>
      </div>

      <div className="flex-1 min-h-0 px-2 pb-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 14%, 18%)" vertical={false} />
            <ReferenceLine y={0} stroke="hsl(220, 10%, 35%)" strokeWidth={1} />
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
              label={{ value: "Score", angle: -90, position: "insideLeft", fontSize: 9, fill: "hsl(220, 10%, 45%)" }}
            />
            <Tooltip
              contentStyle={{
                background: "hsl(220, 18%, 10%)",
                border: "1px solid hsl(220, 14%, 18%)",
                borderRadius: 6, fontSize: 11, color: "hsl(0, 0%, 85%)",
              }}
              formatter={(value: number) => [`${value.toFixed(3)}`, "Balance Score"]}
              labelFormatter={(i) => {
                const d = chartData[i as number];
                return d ? `${d.balanceClass} ${d.isCornering ? "" : "(straight)"}` : "";
              }}
            />
            <Line
              type="monotone"
              dataKey="score"
              stroke="hsl(45, 90%, 55%)"
              strokeWidth={1.5}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default OverUnderSteerChart;
