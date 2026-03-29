import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { RpmComparisonResponse } from "@/lib/api";

interface Props {
  data: RpmComparisonResponse | null;
  cursorIndex: number | null;
}

const RpmChart = ({ data, cursorIndex }: Props) => {
  const chartData = useMemo(() => {
    if (!data) return [];
    return data.series.distanceM.map((d, i) => ({
      distance: Math.round(d),
      lap: Math.round(data.series.lapRpm[i]),
      ref: Math.round(data.series.referenceRpm[i]),
    }));
  }, [data]);

  const cursorDistance = cursorIndex !== null && chartData[cursorIndex]
    ? chartData[cursorIndex].distance
    : null;

  if (chartData.length === 0) {
    return (
      <div className="border border-border rounded-lg bg-card flex items-center justify-center">
        <span className="text-muted-foreground text-xs">Loading RPM data…</span>
      </div>
    );
  }

  return (
    <div className="border border-border rounded-lg bg-card flex flex-col min-h-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <div className="flex items-center gap-2">
          <div className="w-1 h-4 rounded-full bg-primary" />
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-medium">
            RPM Comparison
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-0.5 rounded-full bg-primary inline-block" /> Your Lap
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-0.5 rounded-full inline-block" style={{ background: "hsl(160, 70%, 50%)" }} /> Reference
          </span>
        </div>
      </div>
      <div className="flex-1 min-h-0 px-2 pb-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 14%, 18%)" vertical={false} />
            <ReferenceLine y={11000} stroke="hsl(0, 85%, 50%)" strokeDasharray="6 3" strokeOpacity={0.4} label={{ value: "Redline", position: "right", fontSize: 9, fill: "hsl(0, 85%, 50%)" }} />
            {cursorDistance !== null && (
              <ReferenceLine x={cursorDistance} stroke="hsl(0, 0%, 60%)" strokeWidth={1} strokeDasharray="3 2" />
            )}
            <XAxis dataKey="distance" stroke="hsl(220, 10%, 35%)" tick={{ fontSize: 9, fill: "hsl(220, 10%, 55%)" }} tickLine={false} axisLine={false} />
            <YAxis domain={[2000, 13000]} stroke="hsl(220, 10%, 35%)" tick={{ fontSize: 9, fill: "hsl(220, 10%, 55%)" }} tickLine={false} axisLine={false} width={40} />
            <Tooltip contentStyle={{ background: "hsl(220, 18%, 10%)", border: "1px solid hsl(220, 14%, 18%)", borderRadius: 6, fontSize: 11, color: "hsl(0, 0%, 85%)" }} />
            <Line type="monotone" dataKey="ref" stroke="hsl(160, 70%, 50%)" strokeWidth={1.5} dot={false} strokeOpacity={0.7} />
            <Line type="monotone" dataKey="lap" stroke="hsl(0, 85%, 55%)" strokeWidth={1.5} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default RpmChart;
