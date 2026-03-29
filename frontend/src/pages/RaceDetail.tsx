import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, ChevronRight } from "lucide-react";
import Navbar from "@/components/Navbar";
import HeatmapTrackMap from "@/components/HeatmapTrackMap";
import MetricsPanel from "@/components/MetricsPanel";
import MistakeAnalysis from "@/components/MistakeAnalysis";
import { cn } from "@/lib/utils";

// Mock race metadata keyed by id
const RACE_META: Record<
  string,
  {
    date: string;
    track: string;
    bestLap: string;
    totalLaps: number;
    conditions: string;
  }
> = {
  r12: {
    date: "Mar 28, 2026",
    track: "Yas Marina — North Layout",
    bestLap: "1:10.100",
    totalLaps: 14,
    conditions: "Clear, 31°C",
  },
  r11: {
    date: "Mar 25, 2026",
    track: "Yas Marina — North Layout",
    bestLap: "1:10.500",
    totalLaps: 12,
    conditions: "Clear, 29°C",
  },
  r10: {
    date: "Mar 22, 2026",
    track: "Yas Marina — North Layout",
    bestLap: "1:10.800",
    totalLaps: 15,
    conditions: "Overcast, 27°C",
  },
  r9: {
    date: "Mar 19, 2026",
    track: "Yas Marina — North Layout",
    bestLap: "1:11.200",
    totalLaps: 10,
    conditions: "Clear, 33°C",
  },
  r8: {
    date: "Mar 15, 2026",
    track: "Yas Marina — North Layout",
    bestLap: "1:11.500",
    totalLaps: 13,
    conditions: "Clear, 30°C",
  },
  r7: {
    date: "Mar 12, 2026",
    track: "Yas Marina — North Layout",
    bestLap: "1:12.000",
    totalLaps: 11,
    conditions: "Clear, 28°C",
  },
  r6: {
    date: "Mar 8, 2026",
    track: "Yas Marina — North Layout",
    bestLap: "1:12.900",
    totalLaps: 14,
    conditions: "Hazy, 32°C",
  },
  r5: {
    date: "Mar 1, 2026",
    track: "Yas Marina — North Layout",
    bestLap: "1:13.500",
    totalLaps: 12,
    conditions: "Clear, 26°C",
  },
  r4: {
    date: "Feb 15, 2026",
    track: "Yas Marina — North Layout",
    bestLap: "1:14.100",
    totalLaps: 9,
    conditions: "Clear, 24°C",
  },
  r3: {
    date: "Feb 1, 2026",
    track: "Yas Marina — North Layout",
    bestLap: "1:14.800",
    totalLaps: 11,
    conditions: "Overcast, 22°C",
  },
  r2: {
    date: "Jan 18, 2026",
    track: "Yas Marina — North Layout",
    bestLap: "1:15.400",
    totalLaps: 10,
    conditions: "Clear, 21°C",
  },
  r1: {
    date: "Jan 4, 2026",
    track: "Yas Marina — North Layout",
    bestLap: "1:16.200",
    totalLaps: 8,
    conditions: "Clear, 20°C",
  },
};

interface RaceMistake {
  id: string;
  timestamp: string;
  severity: "critical" | "warning" | "minor";
  title: string;
  sector: number;
  description: string;
}

// Mock mistakes sorted chronologically
const MOCK_MISTAKES: RaceMistake[] = [
  {
    id: "m1",
    timestamp: "0:08.4",
    severity: "critical",
    title: "Lock-up under braking",
    sector: 1,
    description:
      "Rear-right locked under heavy braking into T1. Flat spot risk.",
  },
  {
    id: "m2",
    timestamp: "0:51.9",
    severity: "minor",
    title: "Gear selection delay",
    sector: 2,
    description: "Downshift to 3rd was 0.15s late entering T9.",
  },
];

const severityLabel: Record<string, string> = {
  critical: "Critical",
  warning: "Warning",
  minor: "Minor",
};

const severityDot: Record<string, string> = {
  critical: "bg-destructive",
  warning: "bg-yellow-400",
  minor: "bg-blue-400",
};

const RaceDetail = () => {
  const { raceId } = useParams<{ raceId: string }>();
  const [selectedMistakeIndex, setSelectedMistakeIndex] = useState<
    number | null
  >(null);
  const navigate = useNavigate();
  const race = raceId ? RACE_META[raceId] : null;

  if (!race) {
    return (
      <div className="flex flex-col h-screen bg-background">
        <Navbar />
        <div className="flex-1 flex items-center justify-center">
          <p className="text-muted-foreground">Race not found</p>
        </div>
      </div>
    );
  }

  const mistakeMarkers = MOCK_MISTAKES.map((m) => ({
    sector: m.sector,
    severity: m.severity,
  }));

  return (
    <div className="relative flex flex-col h-screen overflow-hidden bg-background">
      <Navbar />

      {/* Sub-header */}
      <div className="flex items-center gap-3 px-5 py-2.5 border-b border-border bg-card/50">
        <button
          onClick={() => navigate("/history")}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back
        </button>
        <div className="w-px h-4 bg-border" />
        <span className="text-sm font-medium text-foreground">{race.date}</span>
        <span className="text-xs text-muted-foreground">·</span>
        <span className="text-xs text-muted-foreground">{race.track}</span>
        <span className="text-xs text-muted-foreground">·</span>
        <span className="text-xs font-mono text-foreground">
          {race.bestLap}
        </span>
        <span className="text-xs text-muted-foreground">·</span>
        <span className="text-xs text-muted-foreground">
          {race.totalLaps} laps · {race.conditions}
        </span>
      </div>

      {/* Main layout */}
      <div className="flex flex-1 min-h-0">
        {/* Left: Track Map — 40% */}
        <div className="w-[40%] min-h-0 p-4 flex">
          <div className="flex-1 min-h-0 rounded-[1.5rem] border border-white/10 bg-card/60 shadow-2xl shadow-black/20 overflow-hidden">
            <HeatmapTrackMap className="h-full" mistakes={mistakeMarkers} />
          </div>
        </div>

        {/* Right: Remarks + Stats — 60% */}
        <div className="w-[60%] min-h-0 flex flex-col gap-4 p-4 pl-0">
          {/* Top: Remarks & Mistakes */}
          <div className="flex-[5] min-h-0 flex flex-col overflow-hidden rounded-xl border border-border bg-card/50">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                Remarks & Mistakes
              </span>
              <span className="text-[11px] text-muted-foreground/60">
                {MOCK_MISTAKES.length} events
              </span>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto">
              {MOCK_MISTAKES.map((mistake, i) => (
                <button
                  key={mistake.id}
                  onClick={() => setSelectedMistakeIndex(i)}
                  className={cn(
                    "group w-full text-left px-4 py-3 flex items-center gap-3 transition-colors hover:bg-secondary/30",
                    i < MOCK_MISTAKES.length - 1 && "border-b border-border/50",
                  )}
                >
                  <span
                    className={`w-2 h-2 rounded-full shrink-0 ${severityDot[mistake.severity]}`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground">
                        {mistake.title}
                      </span>
                      <span className="text-[10px] text-muted-foreground/50 uppercase tracking-wider">
                        {severityLabel[mistake.severity]}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground/70 line-clamp-1 mt-0.5">
                      {mistake.description}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-[11px] font-mono text-muted-foreground tabular-nums">
                      {mistake.timestamp}
                    </span>
                    <ChevronRight className="w-3 h-3 text-muted-foreground/30 group-hover:text-muted-foreground/60 transition-colors" />
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Bottom: Statistics */}
          <div className="flex-[5] min-h-0">
            <MetricsPanel />
          </div>
        </div>
      </div>

      {/* Mistake Analysis Overlay */}
      {selectedMistakeIndex !== null && (
        <MistakeAnalysis
          mistakes={MOCK_MISTAKES}
          selectedIndex={selectedMistakeIndex}
          onClose={() => setSelectedMistakeIndex(null)}
          onNavigate={setSelectedMistakeIndex}
          raceId={raceId || ""}
        />
      )}
    </div>
  );
};

export default RaceDetail;
