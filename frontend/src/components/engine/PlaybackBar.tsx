import { Play, Pause, RotateCcw } from "lucide-react";

interface Props {
  value: number;
  max: number;
  isPlaying: boolean;
  onValueChange: (v: number) => void;
  onPlayPause: () => void;
  onReset: () => void;
  distanceM?: number;
  progressPct?: number;
}

const PlaybackBar = ({ value, max, isPlaying, onValueChange, onPlayPause, onReset, distanceM, progressPct }: Props) => {
  return (
    <div className="flex items-center gap-3 px-4 py-2 border-t border-border bg-card shrink-0">
      <button
        onClick={onReset}
        className="p-1.5 rounded hover:bg-surface transition-colors text-muted-foreground hover:text-foreground"
        aria-label="Reset playback"
      >
        <RotateCcw className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={onPlayPause}
        className="p-1.5 rounded hover:bg-surface transition-colors text-muted-foreground hover:text-foreground"
        aria-label={isPlaying ? "Pause playback" : "Play playback"}
      >
        {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
      </button>

      <input
        type="range"
        min={0}
        max={max}
        value={value}
        onChange={(e) => onValueChange(Number(e.target.value))}
        className="flex-1 h-1 appearance-none bg-secondary rounded-full cursor-pointer accent-primary
          [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3
          [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:shadow-md
          [&::-webkit-slider-thumb]:cursor-pointer"
      />

      <div className="flex items-center gap-3 text-[10px] text-muted-foreground font-mono min-w-[160px] justify-end">
        {distanceM !== undefined && (
          <span>{Math.round(distanceM)}m</span>
        )}
        {progressPct !== undefined && (
          <span>{(progressPct * 100).toFixed(1)}%</span>
        )}
        <span className="text-foreground/60">{value}/{max}</span>
      </div>
    </div>
  );
};

export default PlaybackBar;
