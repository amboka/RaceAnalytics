import { useState, useEffect, useRef } from "react";
import {
  X,
  ChevronRight,
  ChevronLeft,
  Play,
  Pause,
  AlertTriangle,
  Lightbulb,
  Target,
} from "lucide-react";
import { cn } from "@/lib/utils";
import AnalysisTrackMap, {
  type AnalysisMistakeMarker,
} from "@/components/AnalysisTrackMap";
import { fetchCameraFrames, type CameraFrame } from "@/lib/api";

interface RaceMistake {
  id: string;
  timestamp: string;
  severity: "critical" | "warning" | "minor";
  title: string;
  sector: number;
  description: string;
}

interface MistakeAnalysisProps {
  mistakes: RaceMistake[];
  selectedIndex: number;
  onClose: () => void;
  onNavigate: (index: number) => void;
  raceId: string;
}

// Mock coaching data per mistake
const COACHING: Record<string, { what: string; why: string; fix: string }> = {
  m1: {
    what: "Rear-right wheel locked under heavy braking into Turn 1 at 285 km/h. Brake pressure peaked at 98% with no modulation on initial application.",
    why: "Brake bias was shifted too far rearward for the current fuel load. The sudden full-pressure input exceeded rear tire grip threshold, causing instant lock-up.",
    fix: "Apply brakes progressively — ramp to peak pressure over 0.15s instead of instant. Shift brake bias 2% forward for this fuel window. Trail-brake into the corner to maintain rear stability.",
  },
  m2: {
    what: "Apex missed by 0.8 meters at Turn 3, resulting in a wider exit line and 6 km/h lower exit speed onto the following straight.",
    why: "Turn-in point was 3 meters late. The entry speed was 4 km/h above optimal, forcing a wider arc through the corner.",
    fix: "Brake 5 meters earlier and turn in at the 50m board. Reduce entry speed by 4 km/h to hit the apex kerb. This alone recovers ~0.15s.",
  },
  m3: {
    what: "Throttle applied 0.2 seconds before the car reached optimal rotation point exiting Turn 4. Caused mild understeer on exit.",
    why: "Driver anticipation — throttle was applied before the steering wheel was unwound. The front tires were still loaded laterally when longitudinal force was requested.",
    fix: "Wait for steering angle to reduce below 40° before applying throttle. Use the visual reference of the exit kerb becoming visible before squeezing the throttle.",
  },
  m4: {
    what: "Brakes released 15 meters before corner entry. The car lost rotational yaw and pushed wide through mid-corner.",
    why: "Trail braking was cut short — the driver released brake pressure abruptly rather than gradually tapering it into the corner.",
    fix: "Maintain light brake pressure (8-12%) through the first third of the corner. Gradually release as you approach the apex. This keeps weight on the front axle for better turn-in.",
  },
  m5: {
    what: "Sudden oversteer snap at Turn 7 mid-corner requiring full counter-steer correction. Lost 0.4 seconds and wore the rear tires significantly.",
    why: "Aggressive throttle application on a downhill, off-camber section combined with a bump unsettled the rear. Differential was in an aggressive setting.",
    fix: "Smooth throttle application through T7 — use 60% throttle through the off-camber section before going full power. Consider softening the diff setting for this sector.",
  },
  m6: {
    what: "Downshift from 4th to 3rd gear was 0.15 seconds late entering Turn 9. Engine RPM dropped below optimal power band.",
    why: "The driver was focused on braking reference and delayed the downshift. The sequential shift was initiated too close to the turn-in point.",
    fix: "Initiate the downshift sequence 10 meters earlier. Use the 75m board as the trigger for the 4th-to-3rd shift. Practice heel-toe timing at this corner.",
  },
  m7: {
    what: "Two wheels exceeded track boundary on Turn 11 exit. In a race scenario this would trigger a track limits warning.",
    why: "Exit speed was 3 km/h higher than the tire grip could sustain on the exit kerb. The car drifted onto the run-off area.",
    fix: "Sacrifice 2 km/h of mid-corner speed to stay within limits on exit. Use the painted line as your visual boundary — if you see gravel, you're too wide.",
  },
  m8: {
    what: "Brief throttle lift on the back straight lasting 0.12 seconds. Cost approximately 0.1 seconds in lap time.",
    why: "Likely a confidence lift — possibly reacting to a visual disturbance or wind gust. The data shows no mechanical reason for the lift.",
    fix: "Commit to full throttle through the straight. If the car feels unstable, address it through setup (rear wing, diff) rather than lifting mid-straight.",
  },
  m9: {
    what: "Front-end push on entry to Turn 14. The car understeered through mid-corner, scrubbing 4 km/h of speed.",
    why: "Entry speed was 5 km/h too high and the car was not rotated enough before apex. Weight transfer was insufficient for the tire to generate lateral grip.",
    fix: "Brake 8 meters earlier for T14. Use a slight trail brake to load the front axle. Consider a lift-turn-brake sequence if trail braking feels uncomfortable here.",
  },
};

const severityColor: Record<string, string> = {
  critical: "text-destructive",
  warning: "text-yellow-400",
  minor: "text-blue-400",
};
/** Parse "M:SS.d" timestamp to seconds */
const parseTimestamp = (ts: string): number => {
  const parts = ts.split(":");
  const minutes = parseInt(parts[0], 10) || 0;
  const seconds = parseFloat(parts[1]) || 0;
  return minutes * 60 + seconds;
};

const formatTimestamp = (secondsTotal: number): string => {
  const safeSeconds = Math.max(0, secondsTotal);
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds - minutes * 60;
  return `${minutes}:${seconds.toFixed(1).padStart(4, "0")}`;
};

const toCameraFrame = (
  frame: string | CameraFrame,
  fallbackFrameNumber: number,
): CameraFrame => {
  if (typeof frame === "string") {
    return {
      frameNumber: fallbackFrameNumber,
      imageUrl: frame,
      timestampSeconds: 0,
      timestampNs: 0,
      x: 0,
      y: 0,
      z: 0,
    };
  }
  return frame;
};

const CAMERA_RACE_ID_FALLBACKS = ["0", "hackathon_good_lap"];
const WINDOW_BEFORE_SECONDS = 3;
const WINDOW_AFTER_SECONDS = 7;
const WINDOW_DURATION_SECONDS = WINDOW_BEFORE_SECONDS + WINDOW_AFTER_SECONDS;

const MistakeAnalysis = ({
  mistakes,
  selectedIndex,
  onClose,
  onNavigate,
  raceId,
}: MistakeAnalysisProps) => {
  const clampedIndex = Math.min(selectedIndex, mistakes.length - 1);
  const mistake = mistakes[clampedIndex];
  const coaching = mistake
    ? COACHING[mistake.id] || {
        what: mistake.description,
        why: "Analysis pending.",
        fix: "Review telemetry data for this segment.",
      }
    : { what: "", why: "", fix: "" };
  const [isPlaying, setIsPlaying] = useState(true);
  const [frameIndex, setFrameIndex] = useState(0);

  // Camera frame state
  const [frontFrames, setFrontFrames] = useState<CameraFrame[]>([]);
  const [rearFrames, setRearFrames] = useState<CameraFrame[]>([]);
  const [fps, setFps] = useState(5);
  const [framesLoading, setFramesLoading] = useState(false);
  const effectiveRaceId = raceId || "0";

  const lapDuration = 70;
  const mistakeSeconds = mistake ? parseTimestamp(mistake.timestamp) : 0;
  const windowStartSeconds = Math.max(
    mistakeSeconds - WINDOW_BEFORE_SECONDS,
    0,
  );
  const requestStartTimestamp = formatTimestamp(windowStartSeconds);

  const frameIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch camera frames by timestamp when mistake changes
  useEffect(() => {
    if (!mistake) return;
    setFramesLoading(true);
    setFrameIndex(0);
    setFrontFrames([]);
    setRearFrames([]);

    const candidateRaceIds = Array.from(
      new Set([effectiveRaceId, ...CAMERA_RACE_ID_FALLBACKS]),
    );

    const fetchWithFallback = async (camera: number) => {
      for (const candidateRaceId of candidateRaceIds) {
        const response = await fetchCameraFrames(
          candidateRaceId,
          camera,
          requestStartTimestamp,
          WINDOW_DURATION_SECONDS,
        ).catch(() => null);
        if (response && response.frames.length > 0) {
          return response;
        }
      }
      return null;
    };

    Promise.all([fetchWithFallback(0), fetchWithFallback(1)]).then(
      ([front, rear]) => {
        if (front) {
          setFrontFrames(
            front.frames.map((frame, idx) => toCameraFrame(frame, idx + 1)),
          );
          setFps(front.fps || 5);
        }
        if (rear) {
          setRearFrames(
            rear.frames.map((frame, idx) => toCameraFrame(frame, idx + 1)),
          );
        }
        setFramesLoading(false);
      },
    );
  }, [mistake?.id, effectiveRaceId, requestStartTimestamp]);

  // Reset playback on mistake change
  useEffect(() => {
    setFrameIndex(0);
    setIsPlaying(true);
  }, [selectedIndex]);

  // Frame ticker (for image flipbook)
  const totalFrames = Math.max(frontFrames.length, rearFrames.length, 1);
  const activeFrontFrame =
    frontFrames.length > 0
      ? frontFrames[frameIndex % frontFrames.length]
      : null;
  const activeRearFrame =
    rearFrames.length > 0 ? rearFrames[frameIndex % rearFrames.length] : null;
  const activeFrameForMap = activeFrontFrame ?? activeRearFrame;
  const windowElapsedSeconds = fps > 0 ? frameIndex / fps : 0;
  const relativeSecondsFromMistake =
    windowStartSeconds + windowElapsedSeconds - mistakeSeconds;
  const lapProgress = Math.min(
    (windowStartSeconds + windowElapsedSeconds) / lapDuration,
    1,
  );
  const currentMapPosition = activeFrameForMap
    ? { x: activeFrameForMap.x, y: activeFrameForMap.y }
    : null;

  useEffect(() => {
    if (isPlaying && totalFrames > 1) {
      frameIntervalRef.current = setInterval(() => {
        setFrameIndex((i) => (i + 1) % totalFrames);
      }, 1000 / fps);
    } else if (frameIntervalRef.current) {
      clearInterval(frameIntervalRef.current);
    }
    return () => {
      if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
    };
  }, [isPlaying, totalFrames, fps]);

  if (!mistake) {
    return null;
  }

  const hasPrev = clampedIndex > 0;
  const hasNext = clampedIndex < mistakes.length - 1;

  return (
    <div className="absolute inset-0 z-50 flex flex-col bg-background">
      {/* Top bar — close + navigate */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-card/60 shrink-0">
        <button
          onClick={onClose}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <X className="w-4 h-4" />
          <span>Close</span>
        </button>

        <div className="flex items-center gap-2">
          <span
            className={cn(
              "text-xs font-medium",
              severityColor[mistake.severity],
            )}
          >
            {mistake.severity.toUpperCase()}
          </span>
          <span className="text-sm font-medium text-foreground">
            {mistake.title}
          </span>
          <span className="text-xs font-mono text-muted-foreground">
            @ {mistake.timestamp}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => hasPrev && onNavigate(selectedIndex - 1)}
            disabled={!hasPrev}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1 rounded hover:bg-secondary/40"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            Prev
          </button>
          <span className="text-[10px] text-muted-foreground/60 tabular-nums font-mono">
            {selectedIndex + 1}/{mistakes.length}
          </span>
          <button
            onClick={() => hasNext && onNavigate(selectedIndex + 1)}
            disabled={!hasNext}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1 rounded hover:bg-secondary/40"
          >
            Next
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Content — split vertically */}
      <div className="flex-1 min-h-0 flex flex-col">
        {/* Top half — camera feeds */}
        <div className="flex-1 flex flex-col border-b border-border">
          {/* Scrub slider */}
          {totalFrames > 1 && (
            <div className="flex items-center gap-3 px-4 py-1.5 bg-black/40 shrink-0">
              <span className="text-[10px] font-mono text-white/50 tabular-nums w-10 text-right">
                {relativeSecondsFromMistake >= 0 ? "+" : ""}{relativeSecondsFromMistake.toFixed(1)}s
              </span>
              <input
                type="range"
                min={0}
                max={totalFrames - 1}
                value={frameIndex}
                onChange={(e) => setFrameIndex(Number(e.target.value))}
                className="flex-1 h-1 appearance-none bg-white/10 rounded-full cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-2.5 [&::-webkit-slider-thumb]:h-2.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary [&::-moz-range-thumb]:w-2.5 [&::-moz-range-thumb]:h-2.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-primary [&::-moz-range-thumb]:border-0"
              />
              <span className="text-[10px] font-mono text-white/50 tabular-nums w-12">
                {frameIndex + 1}/{totalFrames}
              </span>
            </div>
          )}
          <div className="flex-1 flex">
          {/* Left camera — Front (camera=0) */}
          <div className="w-1/2 border-r border-border relative bg-black overflow-hidden flex items-center justify-center">
            {frontFrames.length > 0 ? (
              <img
                src={activeFrontFrame?.imageUrl}
                alt={`Front camera frame ${frameIndex}`}
                className="w-full h-full object-cover"
                style={{ display: "block" }}
              />
            ) : (
              <div className="absolute inset-0 bg-background/95 flex items-center justify-center">
                <div className="text-center">
                  <div className="w-16 h-16 rounded-full border border-border flex items-center justify-center mx-auto mb-3">
                    {framesLoading ? (
                      <div className="w-5 h-5 border-2 border-muted-foreground/30 border-t-primary rounded-full animate-spin" />
                    ) : (
                      <Play className="w-6 h-6 text-muted-foreground/40 ml-0.5" />
                    )}
                  </div>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground/50">
                    {framesLoading
                      ? "Loading frames…"
                      : "Front Camera — No frames"}
                  </p>
                </div>
              </div>
            )}
            {/* HUD overlay */}
            <div className="absolute top-3 left-3 z-10">
              <span className="text-[9px] uppercase tracking-[0.15em] text-white/40 bg-black/50 px-2 py-1 rounded">
                CAM 1 — Front
              </span>
            </div>
            <div className="absolute bottom-3 left-3 z-10 flex items-center gap-2">
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className="flex items-center justify-center w-7 h-7 rounded-full bg-white/10 hover:bg-white/20 transition-colors"
              >
                {isPlaying ? (
                  <Pause className="w-3 h-3 text-white" />
                ) : (
                  <Play className="w-3 h-3 text-white ml-0.5" />
                )}
              </button>
              <span className="text-[11px] font-mono text-white/60 tabular-nums">
                {mistake.timestamp}
                <span className="text-white/30">
                  {" "}
                  {relativeSecondsFromMistake >= 0 ? "+" : ""}
                  {relativeSecondsFromMistake.toFixed(1)}s
                </span>
              </span>
            </div>
            <div className="absolute bottom-3 right-3 z-10 flex items-center gap-2">
              <span className="text-[10px] font-mono text-white/40">
                {frontFrames.length > 0
                  ? `${(frameIndex % frontFrames.length) + 1}/${frontFrames.length}`
                  : ""}
              </span>
              <span className="text-[10px] font-mono text-white/40">
                S{mistake.sector}
              </span>
            </div>
          </div>

          {/* Right camera — Rear (camera=1) */}
          <div className="w-1/2 border-r border-border relative bg-black overflow-hidden flex items-center justify-center">
            {rearFrames.length > 0 ? (
              <img
                src={activeRearFrame?.imageUrl}
                alt={`Rear camera frame ${frameIndex}`}
                className="w-full h-full object-cover"
                style={{ display: "block" }}
              />
            ) : (
              <div className="absolute inset-0 bg-background/95 flex items-center justify-center">
                <div className="text-center">
                  <div className="w-16 h-16 rounded-full border border-border flex items-center justify-center mx-auto mb-3">
                    {framesLoading ? (
                      <div className="w-5 h-5 border-2 border-muted-foreground/30 border-t-primary rounded-full animate-spin" />
                    ) : (
                      <Play className="w-6 h-6 text-muted-foreground/40 ml-0.5" />
                    )}
                  </div>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground/50">
                    {framesLoading
                      ? "Loading frames…"
                      : "Rear Camera — No frames"}
                  </p>
                </div>
              </div>
            )}
            <div className="absolute top-3 left-3 z-10">
              <span className="text-[9px] uppercase tracking-[0.15em] text-white/40 bg-black/50 px-2 py-1 rounded">
                CAM 2 — Rear
              </span>
            </div>
            <div className="absolute bottom-3 right-3 z-10 flex items-center gap-2">
              <span className="text-[10px] font-mono text-white/40">
                {rearFrames.length > 0
                  ? `${(frameIndex % rearFrames.length) + 1}/${rearFrames.length}`
                  : ""}
              </span>
              <span className="text-[10px] font-mono text-white/40">
                S{mistake.sector}
              </span>
            </div>
          </div>
          </div>
        </div>

        {/* Bottom half — map + coaching */}
        <div className="h-1/2 min-h-0 flex">
          {/* Map — 40% */}
          <div className="w-[40%] min-h-0 p-3 border-r border-border">
            <div className="h-full rounded-xl border border-white/10 overflow-hidden">
              <AnalysisTrackMap
                className="h-full"
                lapProgress={lapProgress}
                currentPosition={currentMapPosition}
                mistakes={mistakes.map(
                  (m) =>
                    ({
                      lapPosition: parseTimestamp(m.timestamp) / lapDuration,
                      severity: m.severity,
                    }) as AnalysisMistakeMarker,
                )}
              />
            </div>
          </div>

          {/* Coaching — 60% */}
          <div className="w-[60%] min-h-0 p-4 overflow-y-auto">
            <div className="space-y-4">
              {/* What happened */}
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <AlertTriangle
                    className={cn(
                      "w-3.5 h-3.5",
                      severityColor[mistake.severity],
                    )}
                  />
                  <span className="text-[10px] uppercase tracking-[0.18em] font-semibold text-muted-foreground">
                    What happened
                  </span>
                </div>
                <p className="text-sm text-foreground/90 leading-relaxed pl-5.5">
                  {coaching.what}
                </p>
              </div>

              {/* Why */}
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <Target className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="text-[10px] uppercase tracking-[0.18em] font-semibold text-muted-foreground">
                    Root Cause
                  </span>
                </div>
                <p className="text-sm text-foreground/90 leading-relaxed pl-5.5">
                  {coaching.why}
                </p>
              </div>

              {/* How to fix */}
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <Lightbulb className="w-3.5 h-3.5 text-yellow-400" />
                  <span className="text-[10px] uppercase tracking-[0.18em] font-semibold text-muted-foreground">
                    How to Improve
                  </span>
                </div>
                <p className="text-sm text-foreground/90 leading-relaxed pl-5.5">
                  {coaching.fix}
                </p>
              </div>

              {/* Quick stats */}
              <div className="flex items-center gap-4 pt-2 border-t border-border/50">
                <div>
                  <span className="text-[9px] uppercase tracking-wider text-muted-foreground/60">
                    Sector
                  </span>
                  <p className="text-sm font-mono text-foreground">
                    {mistake.sector}
                  </p>
                </div>
                <div>
                  <span className="text-[9px] uppercase tracking-wider text-muted-foreground/60">
                    Time
                  </span>
                  <p className="text-sm font-mono text-foreground">
                    {mistake.timestamp}
                  </p>
                </div>
                <div>
                  <span className="text-[9px] uppercase tracking-wider text-muted-foreground/60">
                    Severity
                  </span>
                  <p
                    className={cn(
                      "text-sm font-medium",
                      severityColor[mistake.severity],
                    )}
                  >
                    {mistake.severity.charAt(0).toUpperCase() +
                      mistake.severity.slice(1)}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MistakeAnalysis;
