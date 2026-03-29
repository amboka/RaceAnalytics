import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import Navbar from "@/components/Navbar";
import SystemsPanel from "@/components/SystemsPanel";
import PlaybackBar from "@/components/engine/PlaybackBar";
import BrakePressureChart from "@/components/brakes/BrakePressureChart";
import BrakeTemperatureChart from "@/components/brakes/BrakeTemperatureChart";
import BrakeTransitionChart from "@/components/brakes/BrakeTransitionChart";
import BrakesPerformanceTrackMap from "@/components/BrakesPerformanceTrackMap";
import {
  fetchBrakePressureComparison,
  fetchBrakeTemperatureComparison,
  fetchBrakeTransition,
  type BrakePressureComparisonResponse,
  type BrakeTemperatureComparisonResponse,
  type BrakeTransitionResponse,
} from "@/lib/api";

const Brakes = () => {
  const navigate = useNavigate();
  const [pressureData, setPressureData] =
    useState<BrakePressureComparisonResponse | null>(null);
  const [tempData, setTempData] =
    useState<BrakeTemperatureComparisonResponse | null>(null);
  const [transitionData, setTransitionData] =
    useState<BrakeTransitionResponse | null>(null);

  const [cursorIndex, setCursorIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const rafRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number>(0);

  const dataLength =
    pressureData?.series.distanceM.length ??
    tempData?.series.distanceM.length ??
    700;
  const maxIndex = dataLength - 1;

  useEffect(() => {
    fetchBrakePressureComparison()
      .then(setPressureData)
      .catch((e) => console.error("Brake pressure fetch error:", e));

    fetchBrakeTemperatureComparison()
      .then(setTempData)
      .catch((e) => console.error("Brake temp fetch error:", e));

    fetchBrakeTransition()
      .then(setTransitionData)
      .catch((e) => console.error("Brake transition fetch error:", e));
  }, []);

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

  const distanceM = pressureData?.series.distanceM[cursorIndex];
  const progressRatio = pressureData?.series.progressRatio[cursorIndex];

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
            {/* Top-left: Track Map */}
            <div className="border border-border rounded-lg bg-card/50 p-2">
              <BrakesPerformanceTrackMap
                className="h-full"
                pressureData={pressureData}
                tempData={tempData}
                transitionData={transitionData}
                cursorProgress={progressRatio ?? 0}
              />
            </div>

            {/* Top-right: Brake Pressure */}
            <BrakePressureChart data={pressureData} cursorIndex={cursorIndex} />

            {/* Bottom-left: Brake Temperature */}
            <BrakeTemperatureChart data={tempData} cursorIndex={cursorIndex} />

            {/* Bottom-right: Brake → Throttle Transition */}
            <BrakeTransitionChart data={transitionData} />
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

export default Brakes;
