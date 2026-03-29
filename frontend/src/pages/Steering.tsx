import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import Navbar from "@/components/Navbar";
import SystemsPanel from "@/components/SystemsPanel";
import PlaybackBar from "@/components/engine/PlaybackBar";
import SteeringAngleChart from "@/components/steering/SteeringAngleChart";
import OverUnderSteerChart from "@/components/steering/OverUnderSteerChart";
import SlipMetricsChart from "@/components/steering/SlipMetricsChart";
import SteeringPerformanceTrackMap from "@/components/SteeringPerformanceTrackMap";
import {
  fetchSteeringAngle,
  fetchOverUnderSteer,
  fetchSlipCoachingMetrics,
  type SteeringAngleResponse,
  type OverUnderSteerResponse,
  type SlipCoachingResponse,
} from "@/lib/api";

const Steering = () => {
  const navigate = useNavigate();
  const [steeringData, setSteeringData] =
    useState<SteeringAngleResponse | null>(null);
  const [overUnderData, setOverUnderData] =
    useState<OverUnderSteerResponse | null>(null);
  const [slipData, setSlipData] = useState<SlipCoachingResponse | null>(null);

  const [cursorIndex, setCursorIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const rafRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number>(0);

  // Derive data length from steering angle (slow race sample count)
  const dataLength =
    steeringData?.races.find((r) => r.raceId === "slow")?.sampleCount ??
    overUnderData?.races[0]?.sampleCount ??
    400;
  const maxIndex = dataLength - 1;

  useEffect(() => {
    fetchSteeringAngle()
      .then(setSteeringData)
      .catch((e) => console.error("Steering angle fetch error:", e));

    fetchOverUnderSteer()
      .then(setOverUnderData)
      .catch((e) => console.error("Over/understeer fetch error:", e));

    fetchSlipCoachingMetrics()
      .then(setSlipData)
      .catch((e) => console.error("Slip coaching fetch error:", e));
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

  const cursorProgress = maxIndex > 0 ? cursorIndex / maxIndex : 0;

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
            {/* Top left: track map placeholder */}
            <div className="border border-border rounded-lg bg-card/50 p-2">
              <SteeringPerformanceTrackMap
                className="h-full"
                steeringData={steeringData}
                overUnderData={overUnderData}
                slipData={slipData}
                cursorProgress={cursorProgress}
              />
            </div>

            <SteeringAngleChart data={steeringData} cursorIndex={cursorIndex} />
            <OverUnderSteerChart
              data={overUnderData}
              cursorIndex={cursorIndex}
            />
            <SlipMetricsChart data={slipData} cursorIndex={cursorIndex} />
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
          />
        </div>

        <SystemsPanel />
      </div>
    </div>
  );
};

export default Steering;
