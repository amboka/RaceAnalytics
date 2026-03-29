"""
main.py
=======
AI Racing Co-Driver — A2RL Hackathon MVP
Yas Marina Circuit, Abu Dhabi

Entry point that wires together all modules:
  1. Load MCAP telemetry
  2. Compare laps & generate delta chart
  3. Request AI coaching debrief from Claude
  4. Run live dashboard + voice co-driver in parallel

Usage:
    python main.py                             # full run, all MCAP files
    python main.py --no-voice                  # skip pyttsx3 (CI/SSH)
    python main.py --no-dashboard              # plain console only
    python main.py --lap fast                  # replay fast lap instead of good lap
    python main.py --synthetic                 # use generated demo data (no MCAP needed)
"""

import os
import sys
import argparse
import threading
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ─────────────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="A2RL AI Race Engineer Co-Driver")
    p.add_argument("--no-voice",     action="store_true", help="Disable TTS voice output")
    p.add_argument("--no-dashboard", action="store_true", help="Disable rich dashboard (plain console)")
    p.add_argument("--no-claude",    action="store_true", help="Skip Claude API (use rule-based debrief)")
    p.add_argument("--voice-only",   action="store_true",
                   help="Run only telemetry replay + voice co-driver (skip lap compare/debrief)")
    p.add_argument("--save-voice-dir", default=None,
                   help="Directory to save spoken feedback as WAV clips")
    p.add_argument("--lap",          choices=["good", "fast", "battle"], default="good",
                   help="Which lap to replay (default: good)")
    p.add_argument("--synthetic",    action="store_true",
                   help="Use synthetic data (no MCAP files needed)")
    p.add_argument("--speed",        type=float, default=1.0,
                   help="Playback speed multiplier (default: 1.0, use 3.0 for quick demo)")
    return p.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
# File paths (adjust if your files are in a different directory)
# ─────────────────────────────────────────────────────────────────────────────
MCAP_FILES = {
    "good":   "hackathon_good_lap.mcap",
    "fast":   "hackathon_fast_laps.mcap",
    "battle": "hackathon_wheel_to_wheel.mcap",
}
TRACK_BOUNDARY_FILE = "yas_marina_bnd.json"
DELTA_CHART_FILE    = "lap_delta.png"


# ─────────────────────────────────────────────────────────────────────────────
# Startup banner
# ─────────────────────────────────────────────────────────────────────────────
BANNER = """
╔══════════════════════════════════════════════════════════════╗
║      🏁  A2RL  AI RACE ENGINEER  —  YAS MARINA CIRCUIT       ║
║         Autonomous Racing Hackathon  ·  Abu Dhabi            ║
╚══════════════════════════════════════════════════════════════╝
"""


def _should_wait_for_enter() -> bool:
    """Skip the prompt in non-interactive environments such as Docker runs."""
    if os.getenv("CODRIVER_SKIP_PROMPT", "").lower() in {"1", "true", "yes"}:
        return False
    return sys.stdin.isatty()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()
    print(BANNER)

    if args.save_voice_dir:
        os.environ["CODRIVER_SAVE_AUDIO_DIR"] = args.save_voice_dir

    if args.voice_only and args.no_voice:
        print("⚠️  You passed both --voice-only and --no-voice.")
        print("   Remove --no-voice to hear spoken co-driver feedback.")
        return

    # ── 1. Import modules ─────────────────────────────────────────────────────
    from mcap_reader import load_mcap, _generate_synthetic_data
    from track_corners import load_track_boundary
    if not args.voice_only:
        from lap_compare import compare_laps, generate_delta_chart, print_sector_table
        from coaching_engine import get_coaching_debrief, print_debrief, _fallback_debrief

    # ── 2. Load telemetry ─────────────────────────────────────────────────────
    print("─" * 62)
    print("  STEP 1 / 4  —  Loading Telemetry")
    print("─" * 62)

    if args.synthetic:
        print("  Using synthetic Yas Marina data (demo mode)\n")
        ref_df = _generate_synthetic_data(duration=81.0)
        lap_df = _generate_synthetic_data(duration=74.0)   # slightly faster
    else:
        lap_file = MCAP_FILES[args.lap]
        ref_file = MCAP_FILES["good"]
        if args.voice_only and args.lap != "fast":
            fast_file = MCAP_FILES.get("fast")
            if fast_file and Path(fast_file).exists():
                ref_file = fast_file

        print(f"  Reference lap : {ref_file}")
        print(f"  Driver lap    : {lap_file}\n")
        ref_df = load_mcap(ref_file)
        lap_df = load_mcap(lap_file)

    print(f"  Reference: {len(ref_df):,} frames  ({ref_df['time'].max():.1f}s)")
    print(f"  Driver:    {len(lap_df):,} frames  ({lap_df['time'].max():.1f}s)\n")

    # ── 3. Load track boundary ────────────────────────────────────────────────
    track_data = load_track_boundary(TRACK_BOUNDARY_FILE)

    comparison = None
    debrief = None

    if not args.voice_only:
        # ── 4. Compare laps ───────────────────────────────────────────────────
        print("─" * 62)
        print("  STEP 2 / 4  —  Lap Comparison")
        print("─" * 62)

        comparison = compare_laps(ref_df, lap_df)
        print_sector_table(comparison)

        print(f"  Generating delta chart → {DELTA_CHART_FILE}")
        generate_delta_chart(comparison, output_path=DELTA_CHART_FILE)

        # ── 5. AI coaching debrief ────────────────────────────────────────────
        print("─" * 62)
        print("  STEP 3 / 4  —  AI Coaching Debrief")
        print("─" * 62)

        if args.no_claude or not os.getenv("ANTHROPIC_API_KEY"):
            if not os.getenv("ANTHROPIC_API_KEY"):
                print("  ⚠️  ANTHROPIC_API_KEY not set — using rule-based debrief\n")
            debrief = _fallback_debrief(comparison)
        else:
            print("  Calling Claude claude-sonnet-4-20250514 race engineer...\n")
            debrief = get_coaching_debrief(comparison)

        print_debrief(debrief, comparison)
    else:
        print("─" * 62)
        print("  STEP 2 / 4  —  Voice-Only Mode")
        print("─" * 62)
        print("  Skipping lap comparison and coaching debrief.\n")
        if not args.no_dashboard:
            print("  Voice-only mode uses plain console replay (dashboard disabled).\n")
            args.no_dashboard = True

    # ── 6. Live session (dashboard + voice) ───────────────────────────────────
    print("─" * 62)
    print("  STEP 4 / 4  —  Live Replay Session")
    print("─" * 62)
    print("  Starting real-time playback...\n")
    if _should_wait_for_enter():
        try:
            input("  Press ENTER to begin the live co-driver session ▶")
            print()
        except EOFError:
            print("  Input unavailable — starting immediately.\n")
    else:
        print("  Non-interactive session detected — starting immediately.\n")

    # Apply playback speed from CLI
    import codriver_voice
    codriver_voice.PLAYBACK_SPEED = args.speed

    stop_event = threading.Event()

    if not args.no_dashboard:
        # ── Dashboard + voice in parallel threads ──────────────────────────
        try:
            from dashboard import DashboardState, run_dashboard
            state = DashboardState()
            state.set_comparison(comparison)
            state.set_debrief(debrief)

            def playback_thread():
                from codriver_voice import run_voice_codriver
                run_voice_codriver(
                    lap_df,
                    ref_df=ref_df,
                    track_data=track_data,
                    enable_voice=not args.no_voice,
                    on_state_update=state.update if not args.no_dashboard else None,
                    stop_event=stop_event,
                )
                stop_event.set()  # signal dashboard to close

            vt = threading.Thread(target=playback_thread, daemon=True)
            vt.start()

            run_dashboard(state, stop_event)

            vt.join(timeout=5)

        except ImportError as e:
            print(f"  Dashboard unavailable ({e}) — falling back to console mode")
            args.no_dashboard = True

    if args.no_dashboard:
        # ── Plain console voice replay ─────────────────────────────────────
        from codriver_voice import run_voice_codriver
        run_voice_codriver(
            lap_df,
            ref_df=ref_df,
            track_data=track_data,
            enable_voice=not args.no_voice,
            stop_event=stop_event,
        )

    print("\n🏁  Session complete — checkered flag!\n")


if __name__ == "__main__":
    main()
