import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Navbar from "@/components/Navbar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  Calendar,
  ChevronRight,
  Trophy,
  TrendingDown,
  Clock,
  Gauge,
} from "lucide-react";

// Mock progression data (last 12 sessions)
const progressionData = [
  { session: "Mar 25", bestLap: 70.1, avgLap: 72.1, gripScore: 82 },
  { session: "Mar 28", bestLap: 76.2, avgLap: 78.5, gripScore: 60 },
];

interface RaceEntry {
  id: string;
  date: string;
  track: string;
  bestLap: string;
  totalLaps: number;
  improvement: number | null; // seconds improved vs previous session, null for first
  conditions: string;
  position?: number;
}

const MOCK_RACES: RaceEntry[] = [
  {
    id: "r12",
    date: "Mar 28, 2026",
    track: "Yas Marina — North Layout",
    bestLap: "1:23.100",
    totalLaps: 1,
    improvement: 6.1,
    conditions: "Clear, 31°C",
  },
];

const History = () => {
  const navigate = useNavigate();

  // Summary stats
  const totalSessions = MOCK_RACES.length;
  const totalLaps = MOCK_RACES.reduce((s, r) => s + r.totalLaps, 0);
  const totalImprovement = (
    progressionData[progressionData.length - 1].bestLap - progressionData[0].bestLap
  ).toFixed(1);
  const improvementPrefix = Number(totalImprovement) > 0 ? "+" : "";

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background">
      <Navbar />
      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="max-w-5xl mx-auto p-6 space-y-6">
          {/* Header */}
          <div>
            <h1 className="text-lg font-display font-semibold text-foreground tracking-wide">
              Session History
            </h1>
            <p className="text-xs text-muted-foreground mt-1">
              Your race archive and performance progression
            </p>
          </div>

          {/* Compact progression section */}
          <div className="grid grid-cols-4 gap-3">
            {/* Mini stats */}
            <Card className="border-border bg-card">
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <Calendar className="w-4 h-4 text-primary" />
                </div>
                <div>
                  <p className="text-[11px] text-muted-foreground">Sessions</p>
                  <p className="text-lg font-semibold text-foreground">{totalSessions}</p>
                </div>
              </CardContent>
            </Card>
            <Card className="border-border bg-card">
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <Clock className="w-4 h-4 text-primary" />
                </div>
                <div>
                  <p className="text-[11px] text-muted-foreground">Total Laps</p>
                  <p className="text-lg font-semibold text-foreground">{totalLaps}</p>
                </div>
              </CardContent>
            </Card>
            <Card className="border-border bg-card">
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-green-500/10 flex items-center justify-center shrink-0">
                  <TrendingDown className="w-4 h-4 text-green-400" />
                </div>
                <div>
                  <p className="text-[11px] text-muted-foreground">Time Gained</p>
                  <p className="text-lg font-semibold text-green-400">{improvementPrefix}{totalImprovement}s</p>
                </div>
              </CardContent>
            </Card>
            <Card className="border-border bg-card">
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <Trophy className="w-4 h-4 text-primary" />
                </div>
                <div>
                  <p className="text-[11px] text-muted-foreground">Personal Best</p>
                  <p className="text-lg font-semibold text-foreground">1:23.1</p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Progression chart — compact */}
          <Card className="border-border bg-card">
            <CardHeader className="pb-1 pt-4 px-4">
              <CardTitle className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Lap Time Progression
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <div className="h-36">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={progressionData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      dataKey="session"
                      stroke="hsl(var(--muted-foreground))"
                      fontSize={10}
                      tickLine={false}
                    />
                    <YAxis
                      stroke="hsl(var(--muted-foreground))"
                      fontSize={10}
                      tickLine={false}
                      domain={["dataMin - 0.5", "dataMax + 0.5"]}
                      tickFormatter={(v: number) => `${v.toFixed(0)}s`}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: 8,
                        fontSize: 11,
                        color: "hsl(var(--foreground))",
                      }}
                      formatter={(value: number, name: string) => [
                        `${value.toFixed(1)}s`,
                        name === "bestLap" ? "Best Lap" : "Avg Lap",
                      ]}
                    />
                    <Line
                      type="monotone"
                      dataKey="bestLap"
                      stroke="hsl(var(--primary))"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="avgLap"
                      stroke="hsl(var(--muted-foreground))"
                      strokeWidth={1.5}
                      strokeDasharray="4 3"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="flex items-center gap-4 mt-2">
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-0.5 bg-primary rounded-full" />
                  <span className="text-[10px] text-muted-foreground">Best Lap</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-0.5 bg-muted-foreground rounded-full opacity-60" />
                  <span className="text-[10px] text-muted-foreground">Avg Lap</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Race Archive */}
          <div>
            <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
              Race Archive
            </h2>
            <div className="space-y-2">
              {MOCK_RACES.map((race) => (
                <button
                  key={race.id}
                  onClick={() => navigate(`/history/${race.id}`)}
                  className="w-full group flex items-center justify-between px-4 py-3.5 rounded-xl bg-card border border-border hover:border-primary/30 hover:bg-secondary/40 transition-all text-left"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-lg bg-secondary flex items-center justify-center shrink-0">
                      <Gauge className="w-4.5 h-4.5 text-muted-foreground" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-foreground">
                          {race.date}
                        </span>
                        {race.id === "r12" && (
                          <Badge
                            variant="outline"
                            className="text-[9px] bg-primary/10 text-primary border-primary/25"
                          >
                            LATEST
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {race.track} · {race.totalLaps} laps · {race.conditions}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-5">
                    <div className="text-right">
                      <p className="text-sm font-mono font-semibold text-foreground">
                        {race.bestLap}
                      </p>
                      {race.improvement !== null && (
                        <p className="text-[11px] font-mono text-green-400">
                          {race.improvement.toFixed(1)}s
                        </p>
                      )}
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-foreground transition-colors" />
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default History;
