import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Pause,
  Play,
  SkipBack,
  SkipForward,
  Volume2,
  VolumeX,
  Gauge,
  Timer,
  Clapperboard,
  ArrowLeft,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";

const VIDEO_SRC = "/voice_full%20(online-video-cutter.com).mp4";

const formatVideoTime = (seconds: number): string => {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0");
  return `${mins}:${secs}`;
};

const formatPace = (seconds: number): string => {
  if (!Number.isFinite(seconds) || seconds <= 0) return "--:--";
  const mins = Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0");
  const secs = Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0");
  return `${mins}:${secs}`;
};

const LiveSimulate = () => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(true);
  const [volume, setVolume] = useState(0.75);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onLoadedMetadata = () => setDuration(video.duration || 0);
    const onTimeUpdate = () => setCurrentTime(video.currentTime || 0);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);

    video.addEventListener("loadedmetadata", onLoadedMetadata);
    video.addEventListener("timeupdate", onTimeUpdate);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);

    return () => {
      video.removeEventListener("loadedmetadata", onLoadedMetadata);
      video.removeEventListener("timeupdate", onTimeUpdate);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
    };
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    video.play().catch(() => {
      setIsPlaying(false);
    });
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.volume = volume;
  }, [volume]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.playbackRate = playbackRate;
  }, [playbackRate]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = isMuted;
  }, [isMuted]);

  const togglePlayback = async () => {
    const video = videoRef.current;
    if (!video) return;

    if (video.paused) {
      try {
        await video.play();
      } catch {
        setIsPlaying(false);
      }
      return;
    }

    video.pause();
  };

  const onScrub = (nextSeconds: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = nextSeconds;
    setCurrentTime(nextSeconds);
  };

  const jumpBySeconds = (delta: number) => {
    const video = videoRef.current;
    if (!video) return;

    const next = Math.max(0, Math.min(video.currentTime + delta, duration || 0));
    video.currentTime = next;
    setCurrentTime(next);
  };

  const toggleMute = () => {
    setIsMuted((prev) => !prev);
  };

  const handleVolumeChange = (nextVolume: number) => {
    setVolume(nextVolume);
    if (nextVolume > 0 && isMuted) {
      setIsMuted(false);
    }
    if (nextVolume === 0 && !isMuted) {
      setIsMuted(true);
    }
  };

  const remainingTime = Math.max(0, duration - currentTime);
  const playbackOptions = [0.75, 1, 1.25];

  return (
    <div className="min-h-screen bg-background px-4 py-6 md:px-6 md:py-8">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
              <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-primary">
                Live HUD System
              </span>
            </div>
            <h1 className="text-xl font-display font-semibold text-foreground tracking-wide">
              Simulation Playback
            </h1>
            <p className="mt-1 text-xs text-muted-foreground">
              Replay from onboard feed with synchronized controls
            </p>
          </div>
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <Link to="/live">
              <ArrowLeft className="h-3.5 w-3.5" />
              Back to Live
            </Link>
          </Button>
        </div>

        <Card className="overflow-hidden border-border bg-card/95">
          <CardContent className="p-0">
            <div className="relative border-b border-border bg-black">
              <video
                ref={videoRef}
                src={VIDEO_SRC}
                className="aspect-video w-full"
                playsInline
                muted={isMuted}
                preload="metadata"
                onClick={togglePlayback}
              />
              <div className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/70 to-transparent" />
              <div className="absolute left-3 top-3 flex items-center gap-2 md:left-4 md:top-4">
                <Badge
                  variant="outline"
                  className="border-white/20 bg-black/40 text-[10px] uppercase tracking-wider text-white/80"
                >
                  Voice Full
                </Badge>
                <Badge
                  variant="outline"
                  className="border-white/15 bg-black/30 text-[10px] uppercase tracking-wider text-white/70"
                >
                  {isPlaying ? "Playing" : "Paused"}
                </Badge>
              </div>
            </div>

            <div className="space-y-4 px-4 py-4 md:px-5 md:py-5">
              <div className="flex items-center gap-3">
                <span className="w-12 text-right font-mono text-[11px] text-muted-foreground tabular-nums">
                  {formatVideoTime(currentTime)}
                </span>
                <Slider
                  value={[Math.min(currentTime, duration || 0)]}
                  min={0}
                  max={duration || 0.1}
                  step={0.1}
                  onValueChange={([next]) => onScrub(next)}
                  className="[&_[data-radix-slider-range]]:bg-primary [&_[data-radix-slider-thumb]]:h-3 [&_[data-radix-slider-thumb]]:w-3 [&_[data-radix-slider-thumb]]:border-primary [&_[data-radix-slider-track]]:h-1 [&_[data-radix-slider-track]]:bg-muted"
                />
                <span className="w-12 font-mono text-[11px] text-muted-foreground tabular-nums">
                  {formatVideoTime(duration)}
                </span>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-1.5">
                  <Button
                    type="button"
                    size="icon"
                    variant="secondary"
                    onClick={() => jumpBySeconds(-5)}
                    aria-label="Rewind 5 seconds"
                    className="h-8 w-8"
                  >
                    <SkipBack className="h-4 w-4" />
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    onClick={togglePlayback}
                    aria-label={isPlaying ? "Pause video" : "Play video"}
                    className="h-9 w-9 rounded-full"
                  >
                    {isPlaying ? (
                      <Pause className="h-4 w-4" />
                    ) : (
                      <Play className="ml-0.5 h-4 w-4" />
                    )}
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    variant="secondary"
                    onClick={() => jumpBySeconds(5)}
                    aria-label="Forward 5 seconds"
                    className="h-8 w-8"
                  >
                    <SkipForward className="h-4 w-4" />
                  </Button>

                  <div className="ml-2 flex items-center gap-2 rounded-md border border-border bg-secondary/40 px-2 py-1">
                    <button
                      type="button"
                      onClick={toggleMute}
                      aria-label={isMuted ? "Unmute" : "Mute"}
                      className="text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {isMuted ? (
                        <VolumeX className="h-4 w-4" />
                      ) : (
                        <Volume2 className="h-4 w-4" />
                      )}
                    </button>
                    <div className="w-20">
                      <Slider
                        value={[isMuted ? 0 : volume]}
                        min={0}
                        max={1}
                        step={0.05}
                        onValueChange={([next]) => handleVolumeChange(next)}
                        className="[&_[data-radix-slider-thumb]]:h-2.5 [&_[data-radix-slider-thumb]]:w-2.5 [&_[data-radix-slider-track]]:h-1"
                      />
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {playbackOptions.map((rate) => (
                    <Button
                      key={rate}
                      type="button"
                      size="sm"
                      variant={playbackRate === rate ? "default" : "outline"}
                      onClick={() => setPlaybackRate(rate)}
                      className="h-7 px-2.5 text-[11px]"
                    >
                      {rate}x
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Card className="border-border bg-card">
            <CardContent className="flex items-center gap-3 p-4">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
                <Timer className="h-4 w-4 text-primary" />
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
                  Remaining
                </p>
                <p className="font-mono text-sm text-foreground">
                  {formatVideoTime(remainingTime)}
                </p>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card">
            <CardContent className="flex items-center gap-3 p-4">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
                <Gauge className="h-4 w-4 text-primary" />
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
                  Playback Rate
                </p>
                <p className="font-mono text-sm text-foreground">
                  {playbackRate.toFixed(2)}x
                </p>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border bg-card">
            <CardContent className="flex items-center gap-3 p-4">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
                <Clapperboard className="h-4 w-4 text-primary" />
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
                  Session Pace
                </p>
                <p className="font-mono text-sm text-foreground">
                  {formatPace(duration)}
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default LiveSimulate;
