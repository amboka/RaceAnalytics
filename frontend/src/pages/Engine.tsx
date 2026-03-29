import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import Navbar from "@/components/Navbar";
import SystemsPanel from "@/components/SystemsPanel";
import ThrottleChart from "@/components/engine/ThrottleChart";
import GearboxChart from "@/components/engine/GearboxChart";
import RpmChart from "@/components/engine/RpmChart";
import PlaybackBar from "@/components/engine/PlaybackBar";
import EnginePerformanceTrackMap from "@/components/EnginePerformanceTrackMap";
import {
  fetchThrottleComparison,
  fetchGearboxComparison,
  fetchRpmComparison,
  type ThrottleComparisonResponse,
  type GearboxComparisonResponse,
  type RpmComparisonResponse,
} from "@/lib/api";

const REQUEST_POINTS = 600;

const Engine = () => {
  const navigate = useNavigate();
  const [throttleData, setThrottleData] =
    useState<ThrottleComparisonResponse | null>(null);
  const [gearboxData, setGearboxData] =
    useState<GearboxComparisonResponse | null>(null);
  const [rpmData, setRpmData] = useState<RpmComparisonResponse | null>(null);

  const [cursorIndex, setCursorIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const rafRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number>(0);

  // Derive actual data length from whichever dataset loaded
  const dataLength =
    throttleData?.series.distanceM.length ??
    gearboxData?.series.distanceM.length ??
    REQUEST_POINTS;
  const maxIndex = dataLength - 1;

  // Fetch data
  useEffect(() => {
    fetchThrottleComparison("slow", "fast", REQUEST_POINTS)
      .then(setThrottleData)
      .catch((e) => console.error("Throttle fetch error:", e));

    fetchGearboxComparison("slow", "fast", REQUEST_POINTS)
      .then(setGearboxData)
      .catch((e) => console.error("Gearbox fetch error:", e));

    fetchRpmComparison("slow", "fast", REQUEST_POINTS)
      .then(setRpmData)
      .catch((e) => console.error("RPM fetch error:", e));
  }, []);

  // Playback animation
  const animate = useCallback(
    (timestamp: number) => {
      if (!lastTimeRef.current) lastTimeRef.current = timestamp;
      const elapsed = timestamp - lastTimeRef.current;

      if (elapsed > 33) {
        lastTimeRef.current = timestamp;
        setCursorIndex((prev) => {
          if (prev >= maxIndex) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }
      rafRef.current = requestAnimationFrame(animate);
    },
    [maxIndex],
  );

  useEffect(() => {
    if (isPlaying) {
      lastTimeRef.current = 0;
      rafRef.current = requestAnimationFrame(animate);
    } else if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
    }
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isPlaying, animate]);

  const distanceM = throttleData?.series.distanceM[cursorIndex];
  const progressRatio = throttleData?.series.progressRatio[cursorIndex];

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Navbar />
      <div className="flex flex-1 min-h-0">
        <button
          onClick={() => navigate("/")}
          className="absolute top-16 left-4 z-30 flex items-center gap-1.5 rounded-lg border border-border bg-card/80 px-3 py-1.5 text-xs text-muted-foreground backdrop-blur transition hover:text-foreground hover:border-foreground/20"
          aria-label="Back to dashboard"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back
        </button>
        <div className="flex-1 min-h-0 flex flex-col">
          <div className="flex-1 min-h-0 p-3 grid grid-cols-2 grid-rows-2 gap-3">
            {/* Top left: track map colored by engine performance */}
            <div className="border border-border rounded-lg bg-card/50 p-2">
              <EnginePerformanceTrackMap
                className="h-full"
                throttleData={throttleData}
                gearboxData={gearboxData}
                rpmData={rpmData}
                cursorProgress={progressRatio ?? 0}
              />
            </div>

            <ThrottleChart data={throttleData} cursorIndex={cursorIndex} />
            <GearboxChart data={gearboxData} cursorIndex={cursorIndex} />
            <RpmChart data={rpmData} cursorIndex={cursorIndex} />
          </div>

          <PlaybackBar
            value={cursorIndex}
            max={maxIndex}
            isPlaying={isPlaying}
            onValueChange={(v) => {
              setCursorIndex(v);
              setIsPlaying(false);
            }}
            onPlayPause={() => setIsPlaying(!isPlaying)}
            onReset={() => {
              setCursorIndex(0);
              setIsPlaying(false);
            }}
            distanceM={distanceM}
            progressPct={progressRatio}
          />
        </div>

        <SystemsPanel />
      </div>
    </div>
  );
};

export default Engine;
