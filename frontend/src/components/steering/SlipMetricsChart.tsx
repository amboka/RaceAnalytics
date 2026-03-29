import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { SlipCoachingResponse } from "@/lib/api";

interface Props {
  data: SlipCoachingResponse | null;
  cursorIndex: number | null;
}

const SlipMetricsChart = ({ data, cursorIndex }: Props) => {
  const race = data?.races.find((r) => r.raceId === "slow") ?? data?.races[0];

  const chartData = useMemo(() => {
    if (!race) return [];
    return race.series.maxSlipDeg.map((slip, i) => ({
      index: i,
      frontSlip: race.series.frontSlipDeg[i],
      rearSlip: race.series.rearSlipDeg[i],
      maxSlip: slip,
      coachingState: race.series.coachingState[i],
      balanceHint: race.series.balanceHint[i],
    }));
  }, [race]);

  const cursorX = cursorIndex !== null && chartData[cursorIndex] ? cursorIndex : null;

  // Get target slip from config if available
  const targetSlip = data?.config?.targetSlipDeg ?? 6;
  const slipWindow = data?.config?.slipWindowDeg ?? 2;

  if (!data) {
    return (
      <div className="border border-border rounded-lg bg-card flex items-center justify-center">
        <span className="text-muted-foreground text-xs">Loading slip metrics…</span>
      </div>
    );
  }

  return (
    <div className="border border-border rounded-lg bg-card flex flex-col min-h-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <div className="flex items-center gap-2">
          <div className="w-1 h-4 rounded-full bg-primary" />
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium">
            Slip Coaching
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-0.5 rounded-full inline-block" style={{ background: "hsl(0, 85%, 55%)" }} /> Front
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-0.5 rounded-full inline-block" style={{ background: "hsl(210, 80%, 55%)" }} /> Rear
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-0.5 rounded-full inline-block" style={{ background: "hsl(45, 90%, 55%)" }} /> Max
          </span>
        </div>
      </div>

      <div className="flex-1 min-h-0 px-2 pb-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 14%, 18%)" vertical={false} />
            {/* Optimal slip window band */}
            <ReferenceLine y={targetSlip + slipWindow} stroke="hsl(160, 70%, 50%)" strokeDasharray="4 4" strokeOpacity={0.4} />
            <ReferenceLine y={targetSlip - slipWindow} stroke="hsl(160, 70%, 50%)" strokeDasharray="4 4" strokeOpacity={0.4} />
            <ReferenceLine y={targetSlip} stroke="hsl(160, 70%, 50%)" strokeWidth={1} strokeOpacity={0.6} />
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
              formatter={(value: number, name: string) => {
                const labels: Record<string, string> = { frontSlip: "Front", rearSlip: "Rear", maxSlip: "Max" };
                return [`${value.toFixed(2)}°`, labels[name] ?? name];
              }}
              labelFormatter={(i) => {
                const d = chartData[i as number];
                return d ? `${d.coachingState} · ${d.balanceHint}` : "";
              }}
            />
            <Line type="monotone" dataKey="frontSlip" stroke="hsl(0, 85%, 55%)" strokeWidth={1.5} dot={false} />
            <Line type="monotone" dataKey="rearSlip" stroke="hsl(210, 80%, 55%)" strokeWidth={1.5} dot={false} />
            <Line type="monotone" dataKey="maxSlip" stroke="hsl(45, 90%, 55%)" strokeWidth={1.2} dot={false} strokeDasharray="4 2" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default SlipMetricsChart;
