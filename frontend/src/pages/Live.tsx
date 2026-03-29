import { useState, useRef, useEffect } from "react";
import { Volume2, Navigation, Play, Pause, X, ArrowLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const VIDEO_SRC = "/voice_full%20(online-video-cutter.com).mp4";

const features = [
  {
    icon: Navigation,
    title: "Optimal Racing Line Projection",
    description:
      "Real-time AR overlay projected onto the windshield showing the ideal racing line and apex points — adapting dynamically to speed and track conditions.",
  },
  {
    icon: Volume2,
    title: "Audio Navigator System",
    description:
      "Rally-style co-driver audio cues delivered through an in-helmet or cabin speaker system. Provides corner callouts and pace guidance in real time.",
  },
];

const formatTime = (s: number) => {
  if (!Number.isFinite(s) || s < 0) return "0:00";
  return `${Math.floor(s / 60)}:${Math.floor(s % 60)
    .toString()
    .padStart(2, "0")}`;
};

const Live = () => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    if (!open) {
      setIsPlaying(false);
      setCurrentTime(0);
      return;
    }
    const video = videoRef.current;
    if (!video) return;

    const onMeta = () => setDuration(video.duration || 0);
    const onTime = () => setCurrentTime(video.currentTime || 0);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);

    video.addEventListener("loadedmetadata", onMeta);
    video.addEventListener("timeupdate", onTime);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);

    video.play().catch(() => setIsPlaying(false));

    return () => {
      video.removeEventListener("loadedmetadata", onMeta);
      video.removeEventListener("timeupdate", onTime);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
    };
  }, [open]);

  const toggle = async () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      try {
        await v.play();
      } catch {
        setIsPlaying(false);
      }
    } else {
      v.pause();
    }
  };

  const scrub = (val: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = val;
    setCurrentTime(val);
  };

  return (
    <div className="min-h-screen bg-background p-6 space-y-8">
      {/* Header */}
      <div className="max-w-4xl mx-auto">
        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate("/")}
          className="mb-4 gap-1.5"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Dashboard
        </Button>
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
          <span className="text-xs font-medium uppercase tracking-widest text-primary">
            Live HUD System
          </span>
        </div>
        <h1 className="text-2xl font-display font-bold text-foreground mb-3">
          In-Car Augmented Driving Assistant
        </h1>
        <p className="text-sm text-muted-foreground leading-relaxed max-w-2xl">
          A hardware + software solution installed directly in the race car. It
          projects the optimal driving line onto the front windshield using AR
          overlays and provides real-time audio navigation — similar to a rally
          co-driver — guiding the racer through every corner, braking zone, and
          straight with precision cues.
        </p>
      </div>

      {/* Feature cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-4xl mx-auto">
        {features.map((f) => (
          <Card key={f.title} className="bg-card border-border">
            <CardContent className="p-5 space-y-3">
              <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
                <f.icon className="w-4.5 h-4.5 text-primary" />
              </div>
              <h3 className="text-sm font-semibold text-foreground">
                {f.title}
              </h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {f.description}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Images section */}
      <div className="max-w-4xl mx-auto space-y-3">
        <h2 className="text-sm font-display font-semibold text-foreground uppercase tracking-wider">
          Hardware Preview
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="aspect-video overflow-hidden rounded-lg border border-border bg-card">
            <img
              src="/BMW-Head-Up-Display.jpg"
              alt="BMW head-up display hardware"
              className="h-full w-full object-cover"
              loading="lazy"
            />
          </div>
          <div className="aspect-video overflow-hidden rounded-lg border border-border bg-card">
            <img
              src="/0874f902-67bd-43e3-b241-e92e34c0a68b_900x506.jpg"
              alt="HUD demo visualization"
              className="h-full w-full object-cover"
              loading="lazy"
            />
          </div>
        </div>
      </div>

      {/* Simulate button */}
      <div className="max-w-4xl mx-auto">
        <Button size="lg" onClick={() => setOpen(true)} className="gap-2">
          <Play className="w-4 h-4" />
          Launch Simulation
        </Button>
      </div>

      {/* Video modal */}
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm">
          <div className="relative w-full max-w-4xl mx-4 flex flex-col gap-3">
            {/* Close */}
            <button
              onClick={() => {
                videoRef.current?.pause();
                setOpen(false);
              }}
              className="absolute -top-10 left-0 flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors z-10"
            >
              <X className="w-4 h-4" />
              <span>Close</span>
            </button>

            {/* Video */}
            <div className="overflow-hidden rounded-xl border border-border bg-black">
              <video
                ref={videoRef}
                src={VIDEO_SRC}
                className="aspect-video w-full"
                playsInline
                preload="metadata"
                loop
                onClick={toggle}
              />
            </div>

            {/* Controls */}
            <div className="flex items-center gap-3 rounded-lg border border-border bg-card/80 backdrop-blur-sm px-3 py-2">
              <button
                type="button"
                onClick={toggle}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary text-foreground transition-colors hover:bg-secondary/80"
                aria-label={isPlaying ? "Pause" : "Play"}
              >
                {isPlaying ? (
                  <Pause className="h-3.5 w-3.5" />
                ) : (
                  <Play className="ml-0.5 h-3.5 w-3.5" />
                )}
              </button>

              <span className="w-10 text-right font-mono text-[11px] text-muted-foreground tabular-nums">
                {formatTime(currentTime)}
              </span>

              <input
                type="range"
                min={0}
                max={duration || 0}
                step={0.1}
                value={Math.min(currentTime, duration || 0)}
                onChange={(e) => scrub(Number(e.target.value))}
                className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-muted [&::-moz-range-thumb]:h-2.5 [&::-moz-range-thumb]:w-2.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-primary [&::-webkit-slider-thumb]:h-2.5 [&::-webkit-slider-thumb]:w-2.5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary"
                aria-label="Video progress"
              />

              <span className="w-10 font-mono text-[11px] text-muted-foreground tabular-nums">
                {formatTime(duration)}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Live;
