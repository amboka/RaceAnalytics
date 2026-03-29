# 🏁 A2RL AI Race Engineer Co-Driver
### Hackathon MVP · Yas Marina Circuit · Abu Dhabi

---

## 📁 Project Structure

```
codriver/
├── main.py              ← Entry point — run this
├── mcap_reader.py       ← MCAP telemetry extractor
├── track_corners.py     ← Corner detection (GPS + time-based)
├── lap_compare.py       ← Sector-by-sector lap delta engine
├── coaching_engine.py   ← Claude AI debrief generator
├── codriver_voice.py    ← Real-time voice co-driver (pyttsx3)
├── dashboard.py         ← Rich terminal dashboard
└── inspect_mcap.py      ← Topic inspector utility
```

---

## ⚡ Quick Start

### 1. Install dependencies

```bash
pip install mcap mcap-ros2-support pandas pyttsx3 rich anthropic matplotlib numpy
```

**Linux/Ubuntu only** (for pyttsx3 voice):
```bash
sudo apt install espeak espeak-ng libespeak-ng-dev
```

**macOS only:**
```bash
brew install espeak
```

### 2. Set your API key (optional — works without it)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 3. Put your files in the same folder

```
codriver/
├── hackathon_good_lap.mcap
├── hackathon_fast_laps.mcap
├── hackathon_wheel_to_wheel.mcap
└── yas_marina_bnd.json
```

### 4. Inspect your MCAP topics (do this first!)

```bash
python inspect_mcap.py hackathon_good_lap.mcap
```

This prints every topic in the file and suggests TOPIC_MAP entries.
Copy the suggestions into `mcap_reader.py` → `TOPIC_MAP`.

### 5. Run the full system

```bash
# Full demo (dashboard + voice + Claude AI)
python main.py

# Fast demo mode (3× playback speed, good for hackathon presentation)
python main.py --speed 3.0

# No MCAP files? Use synthetic data
python main.py --synthetic

# Skip voice (SSH / headless)
python main.py --no-voice

# Skip dashboard (plain console)
python main.py --no-dashboard

# Replay specific lap
python main.py --lap fast
python main.py --lap battle

# Skip Claude API (rule-based debrief only)
python main.py --no-claude
```

---

## 🟢 Optimal Line Overlay (x_m / y_m + camera image)

Extract the optimal line from `state_estimation` and draw it on
`camera_fl/compressed_image` frames:

```bash
# Step 1: extract and save optimal lap trajectory (x_m, y_m, yaw_rad)
python optimal_line_overlay.py \
  --optimal-mcap hackathon_fast_laps.mcap \
  --tf-mcap merged_for_map.mcap \
  --save-optimal-csv optimal_lap_xy.csv \
  --max-frames 0

# Step 2: render overlaid camera frames for a run
python optimal_line_overlay.py \
  --optimal-mcap hackathon_fast_laps.mcap \
  --tf-mcap merged_for_map.mcap \
  --run-mcap hackathon_fast_laps.mcap \
  --output-dir overlay_frames \
  --max-frames 100
```

Single-image mode (for a new car pose + one JPEG frame):

```bash
python optimal_line_overlay.py \
  --optimal-mcap hackathon_fast_laps.mcap \
  --tf-mcap merged_for_map.mcap \
  --single-image-jpeg frame.jpg \
  --x-m -196.8 --y-m -19.6 --z-m 0.98 --yaw-rad 0.13 \
  --single-output frame_overlay.jpg
```

`--tf-mcap merged_for_map.mcap` reads `/tf_static` and uses the real
`base_link -> camera_fl` transform so the line projection uses the camera's true
mount position relative to `x_m/y_m` (which are base_link coordinates).
For best 3D projection in single-image mode, also pass `--roll-rad` and
`--pitch-rad` when available.
For MCAP frame rendering, the script automatically uses `roll_rad`, `pitch_rad`,
and `yaw_rad` from `/constructor0/state_estimation`.

By default, `optimal_line_overlay.py` uses `camera_fl` intrinsics and
`plumb_bob` distortion coefficients. If your images are already rectified, use:

```bash
python optimal_line_overlay.py \
  --optimal-mcap hackathon_fast_laps.mcap \
  --tf-mcap merged_for_map.mcap \
  --run-mcap hackathon_fast_laps.mcap \
  --output-dir overlay_frames_rectified \
  --fx-px 2748.62329 --fy-px 3058.90015 \
  --cx-px 1957.1594 --cy-px 1117.6496 \
  --no-distortion
```

The renderer now uses image-based camera refinement by default (first frames),
which tunes small camera offsets against road geometry in the image.
You can disable it with `--no-auto-camera-refine`.
It also uses timestamp-interpolated vehicle pose and continuity-aware line
tracking for smoother frame-to-frame overlays.
The refinement uses an OpenCV-style lane pipeline (gradient thresholding +
sliding-window lane fit + polynomial centerline), inspired by the common
"Advanced Lane Finding" GitHub/Udacity approach.

## Docker

Build and run the project in a container:

```bash
docker compose build
docker compose up
```

The default container command runs a safe demo setup:

```bash
python main.py --synthetic --no-claude --speed 3.0
```

Run against real files from the mounted `files/` folder:

```bash
docker compose run --rm codriver python main.py --lap fast --no-voice
docker compose run --rm codriver python inspect_mcap.py hackathon_good_lap.mcap
```

Notes:

- `files/` is mounted into the container, so your `.mcap`, `yas_marina_bnd.json`, and generated `lap_delta.png` stay on the host.
- Linux Docker audio is passed through with the host PulseAudio socket and Pulse auth cookie, which is more reliable than raw device mapping in containers.
- Docker uses the `espeak-ng` command backend by default instead of `pyttsx3`, because it is much more reliable in containers.
- If you are running over SSH, inside WSL, or without a local sound device, use `--no-voice`.
- Set `ANTHROPIC_API_KEY` in your shell before `docker compose run` if you want the Claude debrief in-container.

---

## 🔧 Fixing Topic Names

If telemetry isn't loading, run the inspector:

```bash
python inspect_mcap.py hackathon_good_lap.mcap
```

Example output:
```
  /a2rl/vehicle/speed_kmh          Float32                   81,000
  /a2rl/vehicle/throttle_pct       Float32                   81,000
  /a2rl/imu/kistler                Imu                       81,000
  /vectornav/gps                   NavSatFix                 20,250
```

Then update `TOPIC_MAP` in `mcap_reader.py`:
```python
TOPIC_MAP = {
    "speed":    ["/a2rl/vehicle/speed_kmh"],
    "throttle": ["/a2rl/vehicle/throttle_pct"],
    "imu":      ["/a2rl/imu/kistler"],
    "gps":      ["/vectornav/gps"],
    ...
}
```

---

## 🏗 System Architecture

```
MCAP Files ──► mcap_reader.py ──► pandas DataFrame
                                        │
                          ┌─────────────┼─────────────┐
                          ▼             ▼             ▼
                   lap_compare    track_corners  codriver_voice
                   (delta chart)  (corner zones)  (voice alerts)
                          │                           │
                          └──────────┬────────────────┘
                                     ▼
                             coaching_engine
                            (Claude API debrief)
                                     │
                                     ▼
                               dashboard.py
                            (Rich terminal UI)
```

---

## 📊 What You Get

### Terminal Dashboard (Rich)
```
╔══════════════════════════════════════════════════════════════╗
║      🏁  A2RL  AI RACE ENGINEER  —  YAS MARINA CIRCUIT       ║
╚══════════════════════════════════════════════════════════════╝
┌─ TELEMETRY ──────────────┐  ┌─ TRACK POSITION ─────────────┐
│ SPEED    198.4 km/h      │  │ CORNER   T5 — Hotel Hairpin   │
│ THROTTLE [████████░░] 0.8│  │ PROGRESS [▶▶▶▶▶▶▶····] 38.2% │
│ BRAKE    [░░░░░░░░░░] 0.0│  │                               │
│ GEAR     6               │  │ CO-DRIVER ⚡ Brake now!        │
└──────────────────────────┘  └───────────────────────────────┘
┌─ LAP DELTA ────────────────────────────────────────────────┐
│ S1  +8.2  +0.12s  GAIN                                     │
│ S2  -3.1  -0.05s  LOSS                                     │
│ ...                                                         │
└──────────────────────────────────────────────────────────────┘
```

### Lap Delta Chart (`lap_delta.png`)
Dark-themed bar chart showing speed deltas per mini-sector + cumulative time delta.

### AI Debrief (Claude)
```
═══════════════════════════════════════════════════════════════
  🏁  POST-LAP DEBRIEF — Race Engineer Report
═══════════════════════════════════════════════════════════════
  Lap Rating: ⭐⭐⭐⭐⭐⭐⭐  (7/10)

  ❌ TOP MISTAKES:
  1. 🔴  Late trail braking into T5
     Sector: S6 (-12.3 km/h)
     Braking point 0.4s early vs reference...

  ✅ IMPROVEMENTS:
  1. 💚  Excellent T1 exit speed
     Carrying 15 km/h more through the long right...

  🎯 Focus: Push the T5 braking point 10m later

  💬 "The pace is there — you just need to trust the car."
═══════════════════════════════════════════════════════════════
```

---

## 🚨 Common Issues

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: mcap` | `pip install mcap mcap-ros2-support` |
| `No data loaded` | Run `inspect_mcap.py` and update `TOPIC_MAP` |
| `pyttsx3` no sound | `sudo apt install espeak` (Linux) |
| `API key not found` | `export ANTHROPIC_API_KEY=sk-ant-...` |
| Dashboard flickers | Use `--no-dashboard` and redirect to file |
| Slow load | Add `max_rows=5000` to `load_mcap()` call |

---

## 🎯 Demo Script (Hackathon Pitch)

1. **Show the dashboard** running with `--speed 3.0` (fast playback)
2. **Point out** the voice alerts firing at each corner
3. **Show the lap delta chart** (`lap_delta.png`) on a second screen
4. **Show the AI debrief** — highlight that it's Claude analysing real A2RL data
5. **Key message**: "Any amateur driver can now get pro-level coaching from real autonomous racing data"
