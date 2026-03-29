"""
codriver_voice.py
=================
Real-time telemetry replay with voice feedback via pyttsx3.
Uses track boundary data for corner detection instead of hardcoded times.
"""

import os
import shutil
import subprocess
import tempfile
import time
import threading
import wave
from pathlib import Path
import numpy as np
import pandas as pd

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

from track_corners import (
    load_track_boundary, compute_track_progress,
    get_corner_at_progress, YAS_MARINA_CORNERS
)


# ── Feedback thresholds — tune these for A2RL data ───────────────────────────
THRESHOLDS = {
    # Brake now: high speed, low brake input
    "brake_now_speed":       150,   # km/h
    "brake_now_brake_max":   0.10,

    # Good braking: strong brake application
    "good_brake_min":        0.65,

    # Too fast into corner: above apex speed × this factor
    "corner_overspeed_factor": 1.20,
    "bestlap_fast_delta_kmh": 8.0,
    "bestlap_slow_delta_kmh": 10.0,

    # Throttle too early: high throttle at low speed in corner exit
    "throttle_early_min":    0.75,
    "throttle_early_speed":  80,    # km/h

    # Understeer: high steering angle + brake still on
    "understeer_steering":   0.4,
    "understeer_brake":      0.3,
    "understeer_speed":      60,

    # Late apex hint
    "late_apex_brake_late":  0.15,  # brake delta threshold in seconds
}

REPEAT_COOLDOWN = 4.0    # seconds before the same alert fires again
PLAYBACK_SPEED  = 1.0    # 1.0 = real-time, 2.0 = demo fast
AUDIO_SAVE_ENV  = "CODRIVER_SAVE_AUDIO_DIR"


class _AudioRecorder:
    """Save spoken feedback clips and a merged WAV that preserves timing gaps."""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_path = self.output_dir / "voice_transcript.tsv"
        self.espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak")
        self._counter = 0
        self._lock = threading.Lock()
        self._events: list[dict] = []

        if not self.transcript_path.exists():
            self.transcript_path.write_text("index\tspoken_time\ttext\twav_file\n")

    def _next_event(self, text: str, spoken_at: float) -> tuple[int, Path]:
        with self._lock:
            self._counter += 1
            idx = self._counter
            wav_path = self.output_dir / f"voice_{idx:04d}.wav"
            self._events.append(
                {"idx": idx, "spoken_at": float(spoken_at), "text": text, "wav_path": wav_path}
            )
        return idx, wav_path

    def note(self, text: str, spoken_at: float) -> Path:
        """Record one spoken event and reserve output WAV filename."""
        _, wav_path = self._next_event(text, spoken_at)
        return wav_path

    def _synthesize_clip(self, text: str, wav_path: Path):
        if self.espeak_bin:
            subprocess.run(
                [self.espeak_bin, "-s", "170", "-v", "en", "-w", str(wav_path), text],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif pyttsx3 is not None:
            engine = pyttsx3.init()
            engine.setProperty("rate", 170)
            engine.save_to_file(text, str(wav_path))
            engine.runAndWait()
        else:
            raise RuntimeError("No TTS synthesizer available to save audio")

    def finalize(self) -> Path | None:
        """
        Render per-phrase clips and merge them into one WAV while preserving
        timing gaps between spoken events.
        """
        with self._lock:
            events = list(self._events)

        if not events:
            return None

        events.sort(key=lambda e: e["idx"])
        self.transcript_path.write_text("index\tspoken_time\ttext\twav_file\n", encoding="utf-8")
        with self.transcript_path.open("a", encoding="utf-8") as f:
            for e in events:
                self._synthesize_clip(e["text"], e["wav_path"])
                f.write(
                    f"{e['idx']}\t{e['spoken_at']:.3f}\t{e['text']}\t{e['wav_path'].name}\n"
                )

        merged_path = self.output_dir / "voice_full.wav"
        ref_params = None
        prev_end_time = None

        with wave.open(str(merged_path), "wb") as out_wav:
            for e in events:
                clip_path = e["wav_path"]
                with wave.open(str(clip_path), "rb") as in_wav:
                    params = (
                        in_wav.getnchannels(),
                        in_wav.getsampwidth(),
                        in_wav.getframerate(),
                        in_wav.getcomptype(),
                        in_wav.getcompname(),
                    )
                    if ref_params is None:
                        ref_params = params
                        out_wav.setnchannels(params[0])
                        out_wav.setsampwidth(params[1])
                        out_wav.setframerate(params[2])
                    elif params != ref_params:
                        print(f"[codriver] Skipping incompatible clip: {clip_path.name}")
                        continue

                    frame_rate = float(params[2])
                    nframes = in_wav.getnframes()
                    duration_s = nframes / frame_rate if frame_rate > 0 else 0.0

                    if prev_end_time is not None:
                        gap_s = max(0.0, float(e["spoken_at"]) - prev_end_time)
                        if gap_s > 0:
                            silence_frames = int(round(gap_s * frame_rate))
                            silence = b"\x00" * (silence_frames * params[0] * params[1])
                            out_wav.writeframes(silence)

                    out_wav.writeframes(in_wav.readframes(nframes))
                    prev_end_time = float(e["spoken_at"]) + duration_s

        return merged_path


# ─────────────────────────────────────────────────────────────────────────────
# TTS Engine (singleton per process)
# ─────────────────────────────────────────────────────────────────────────────
class _Pyttsx3Backend:
    name = "pyttsx3"

    def __init__(self):
        if pyttsx3 is None:
            raise RuntimeError("pyttsx3 is not installed")

        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", 170)
        self.engine.setProperty("volume", 1.0)

        voices = self.engine.getProperty("voices")
        for voice in voices:
            if "english" in voice.name.lower() or "david" in voice.name.lower():
                self.engine.setProperty("voice", voice.id)
                break

    def speak(self, text: str):
        self.engine.say(text)
        self.engine.runAndWait()


class _EspeakBackend:
    name = "espeak"

    def __init__(self):
        self.espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak")
        self.player_bin = shutil.which("paplay") or shutil.which("aplay")

        if not self.espeak_bin:
            raise RuntimeError("neither espeak-ng nor espeak is available")

    def speak(self, text: str):
        if self.player_bin:
            fd, wav_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                subprocess.run(
                    [self.espeak_bin, "-s", "170", "-v", "en", "-w", wav_path, text],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                subprocess.run(
                    [self.player_bin, wav_path],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            finally:
                Path(wav_path).unlink(missing_ok=True)
            return

        subprocess.run(
            [self.espeak_bin, "-s", "170", "-v", "en", text],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _build_tts_engine():
    requested = os.getenv("CODRIVER_TTS_BACKEND", "").strip().lower()
    in_container = Path("/.dockerenv").exists()

    if requested == "pyttsx3":
        candidates = (_Pyttsx3Backend, _EspeakBackend)
    elif requested == "espeak":
        candidates = (_EspeakBackend, _Pyttsx3Backend)
    elif in_container:
        candidates = (_EspeakBackend, _Pyttsx3Backend)
    else:
        candidates = (_Pyttsx3Backend, _EspeakBackend)

    errors = []
    for backend_cls in candidates:
        try:
            backend = backend_cls()
            print(f"[codriver] Using {backend.name} TTS backend")
            return backend
        except Exception as exc:
            errors.append(f"{backend_cls.__name__}: {exc}")

    raise RuntimeError("No TTS backend available: " + "; ".join(errors))


def _speak_thread(engine, text: str, lock: threading.Lock, recorder: _AudioRecorder | None = None):
    """Speak in a daemon thread; skip if TTS is already busy."""
    if lock.locked():
        return

    def _run():
        with lock:
            try:
                spoken_at = time.time()
                if recorder is not None:
                    recorder.note(text, spoken_at=spoken_at)
                engine.speak(text)
            except Exception as exc:
                print(f"[codriver] TTS failed: {exc}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ─────────────────────────────────────────────────────────────────────────────
# Feedback Rules Engine
# ─────────────────────────────────────────────────────────────────────────────
class VoiceCoDriver:
    """
    Stateful co-driver that evaluates telemetry frame-by-frame
    and fires voice alerts. Tracks cooldowns to avoid spam.
    """

    def __init__(self, ref_df: pd.DataFrame | None = None,
                 track_data: dict | None = None):
        self.ref_df     = ref_df
        self.track_data = track_data
        self._cooldowns: dict[str, float] = {}
        self._ref_progress: np.ndarray | None = None

        if ref_df is not None:
            self._ref_progress = compute_track_progress(ref_df, track_data)

    def _reference_speed_at_progress(self, progress_pct: float) -> float | None:
        """Return reference-lap speed (km/h) at the nearest progress sample."""
        if self.ref_df is None or self._ref_progress is None:
            return None
        if "speed" not in self.ref_df.columns or len(self.ref_df) == 0:
            return None
        idx = int(np.argmin(np.abs(self._ref_progress - progress_pct)))
        return float(self.ref_df.iloc[idx]["speed"])

    @staticmethod
    def _corner_tag(corner) -> str:
        """Short corner label like 'T8' from names such as 'T8 — Marina Curve'."""
        if corner is None:
            return ""
        name = str(getattr(corner, "name", "")).strip()
        if not name:
            return ""
        if "—" in name:
            return name.split("—", 1)[0].strip()
        if "-" in name:
            return name.split("-", 1)[0].strip()
        return name.split()[0]

    # ── Cooldown guard ────────────────────────────────────────────────────────
    def _can_fire(self, key: str, wall_now: float) -> bool:
        last = self._cooldowns.get(key, 0.0)
        if wall_now - last >= REPEAT_COOLDOWN:
            self._cooldowns[key] = wall_now
            return True
        return False

    # ── Main evaluation ───────────────────────────────────────────────────────
    def evaluate(self, row: pd.Series, progress_pct: float, wall_now: float) -> str | None:
        """
        Evaluate one telemetry frame. Returns a feedback string or None.
        Rules are ordered by priority — first match wins.
        """
        speed   = row["speed"]
        throttle = row["throttle"]
        brake   = row["brake"]
        steering = abs(row.get("steering", 0))
        corner  = get_corner_at_progress(progress_pct)
        corner_tag = self._corner_tag(corner)
        ref_speed = self._reference_speed_at_progress(progress_pct)

        # ── 1. Corner speed vs best lap (preferred) or fallback apex model ───
        if corner and ref_speed is not None:
            delta_kmh = speed - ref_speed
            if delta_kmh > THRESHOLDS["bestlap_fast_delta_kmh"]:
                key = f"too_fast_bestlap_{corner.name}"
                if self._can_fire(key, wall_now):
                    return f"Too fast, {corner_tag}."
            if delta_kmh < -THRESHOLDS["bestlap_slow_delta_kmh"]:
                key = f"too_slow_bestlap_{corner.name}"
                if self._can_fire(key, wall_now):
                    return f"Too slow, {corner_tag}."
        elif corner and speed > corner.apex_speed * THRESHOLDS["corner_overspeed_factor"]:
            if self._can_fire("too_fast_corner", wall_now):
                return f"Too fast, {corner_tag}."

        # ── 2. Brake NOW (high speed, not braking, before known corner) ───────
        if speed > THRESHOLDS["brake_now_speed"] and brake < THRESHOLDS["brake_now_brake_max"]:
            # Check if a corner is coming within ~10% of track progress
            coming_corner = get_corner_at_progress(progress_pct + 8)
            if coming_corner or corner:
                if self._can_fire("brake_now", wall_now):
                    return "Brake now! Brake now!"

        # ── 3. Understeer detected ────────────────────────────────────────────
        if (corner and
                steering > THRESHOLDS["understeer_steering"] and
                brake > THRESHOLDS["understeer_brake"] and
                speed > THRESHOLDS["understeer_speed"]):
            if self._can_fire("understeer", wall_now):
                return f"Understeer — ease off, let it settle"

        # ── 4. Throttle too early (in corner, not at apex yet) ────────────────
        if (corner and
                throttle > THRESHOLDS["throttle_early_min"] and
                speed < THRESHOLDS["throttle_early_speed"]):
            if self._can_fire("throttle_early", wall_now):
                return "Too aggressive on throttle — wait for apex"

        # ── 5. Good braking (positive reinforcement) ──────────────────────────
        if brake > THRESHOLDS["good_brake_min"]:
            if self._can_fire("good_brake", wall_now):
                return "Good braking — nice and straight"

        # ── 6. Straight-line speed nudge ──────────────────────────────────────
        if not corner and throttle < 0.5 and speed > 100:
            if self._can_fire("throttle_lift", wall_now):
                return "Full throttle — you're on a straight"

        return None


# ─────────────────────────────────────────────────────────────────────────────
# Real-time simulation loop
# ─────────────────────────────────────────────────────────────────────────────
def run_voice_codriver(
    lap_df: pd.DataFrame,
    ref_df: pd.DataFrame | None = None,
    track_data: dict | None = None,
    enable_voice: bool = True,
    on_state_update=None,      # callback(row, progress, corner, feedback) for dashboard
    stop_event: threading.Event | None = None,
):
    """
    Replay telemetry in real-time and fire voice alerts.

    Args:
        lap_df:          Driver lap telemetry
        ref_df:          Reference lap (for comparison hints)
        track_data:      Parsed yas_marina_bnd.json
        enable_voice:    Enable spoken feedback
        on_state_update: Optional callback for dashboard integration
        stop_event:      threading.Event to stop the loop externally
    """
    engine   = _build_tts_engine() if enable_voice else None
    tts_lock = threading.Lock()
    codriver = VoiceCoDriver(ref_df=ref_df, track_data=track_data)
    recorder = None
    audio_dir = os.getenv(AUDIO_SAVE_ENV, "").strip()
    if audio_dir:
        try:
            recorder = _AudioRecorder(audio_dir)
            print(f"[codriver] Saving voice clips to: {recorder.output_dir}")
        except Exception as exc:
            print(f"[codriver] Audio recording disabled: {exc}")

    # Pre-compute track progress for the entire lap
    progress_arr = compute_track_progress(lap_df, track_data)
    lap_duration = lap_df["time"].max()

    print(f"\n[codriver] 🎙️  Voice co-driver active — {len(lap_df)} frames, "
          f"{lap_duration:.1f}s lap\n")

    loop_start  = time.time()
    sim_t0      = lap_df["time"].iloc[0]

    for i, row in lap_df.iterrows():
        if stop_event and stop_event.is_set():
            break

        # ── Timing: sleep until this frame's sim timestamp ────────────────────
        sim_elapsed  = row["time"] - sim_t0
        wall_elapsed = (time.time() - loop_start) * PLAYBACK_SPEED
        sleep_for    = (sim_elapsed - wall_elapsed) / PLAYBACK_SPEED
        if sleep_for > 0:
            time.sleep(sleep_for)

        wall_now    = time.time()
        progress    = float(progress_arr[i]) if i < len(progress_arr) else 0.0
        corner      = get_corner_at_progress(progress)

        # ── Evaluate co-driver rules ──────────────────────────────────────────
        feedback = codriver.evaluate(row, progress, wall_now)

        # ── Speak feedback (non-blocking) ─────────────────────────────────────
        if feedback and engine is not None:
            _speak_thread(engine, feedback, tts_lock, recorder=recorder)

        # ── Console output ────────────────────────────────────────────────────
        corner_name = corner.name if corner else "Straight"
        fb_str      = f"  ⚡ {feedback}" if feedback else ""
        print(
            f"  t={row['time']:6.1f}s | "
            f"spd={row['speed']:5.1f} | "
            f"thr={row['throttle']:.2f} | "
            f"brk={row['brake']:.2f} | "
            f"{corner_name:<22}"
            f"{fb_str}"
        )

        # ── Dashboard callback ────────────────────────────────────────────────
        if on_state_update:
            on_state_update(row, progress, corner, feedback)

    print("\n[codriver] ✅  Lap complete — session ended.\n")
    time.sleep(1.0)  # let final speech finish
    wait_deadline = time.time() + 20.0
    while tts_lock.locked() and time.time() < wait_deadline:
        time.sleep(0.05)

    if recorder is not None:
        try:
            merged_path = recorder.finalize()
            if merged_path is not None:
                print(f"[codriver] Combined voice file saved: {merged_path}")
        except Exception as exc:
            print(f"[codriver] Failed to build combined voice file: {exc}")
