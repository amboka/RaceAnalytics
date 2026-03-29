"""
lap_compare.py
==============
Compares a driver lap against the reference good lap.
Produces sector-by-sector deltas and a matplotlib chart.
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # non-interactive backend — safe for hackathon
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from dataclasses import dataclass


SECTOR_DURATION = 5.0   # seconds per mini-sector


@dataclass
class SectorDelta:
    sector: int
    time_start: float
    time_end: float
    ref_avg_speed: float
    lap_avg_speed: float
    speed_delta: float      # positive = faster than reference
    ref_brake_point: float  # time of heaviest braking in sector
    lap_brake_point: float
    brake_delta: float      # positive = braking later (usually faster)
    label: str              # "GAIN" / "LOSS" / "EVEN"


@dataclass
class LapComparison:
    ref_lap_time: float
    driver_lap_time: float
    total_delta: float          # negative = driver is faster
    sectors: list[SectorDelta]
    summary_stats: dict


# ─────────────────────────────────────────────────────────────────────────────
# Core comparison logic
# ─────────────────────────────────────────────────────────────────────────────
def compare_laps(ref_df: pd.DataFrame, lap_df: pd.DataFrame) -> LapComparison:
    """
    Compare driver lap against reference lap sector by sector.

    Args:
        ref_df: Reference (good lap) telemetry DataFrame
        lap_df: Driver lap telemetry DataFrame

    Returns:
        LapComparison with all sector deltas and summary stats
    """
    ref_duration = ref_df["time"].max()
    lap_duration = lap_df["time"].max()
    total_delta   = lap_duration - ref_duration

    # Build sectors based on reference lap duration
    n_sectors = int(ref_duration / SECTOR_DURATION)
    sectors: list[SectorDelta] = []

    for i in range(n_sectors):
        t_start = i * SECTOR_DURATION
        t_end   = t_start + SECTOR_DURATION

        ref_sector = ref_df[(ref_df["time"] >= t_start) & (ref_df["time"] < t_end)]
        lap_sector = lap_df[(lap_df["time"] >= t_start) & (lap_df["time"] < t_end)]

        if ref_sector.empty or lap_sector.empty:
            continue

        ref_avg_speed = ref_sector["speed"].mean()
        lap_avg_speed = lap_sector["speed"].mean()
        speed_delta   = lap_avg_speed - ref_avg_speed

        # Braking point: time of peak brake input within the sector
        ref_brake_idx = ref_sector["brake"].idxmax()
        lap_brake_idx = lap_sector["brake"].idxmax()
        ref_brake_t   = ref_sector.loc[ref_brake_idx, "time"] if not ref_sector.empty else t_start
        lap_brake_t   = lap_sector.loc[lap_brake_idx, "time"] if not lap_sector.empty else t_start
        brake_delta   = lap_brake_t - ref_brake_t  # positive = braking later

        # Label the sector
        if speed_delta > 3:
            label = "GAIN"
        elif speed_delta < -3:
            label = "LOSS"
        else:
            label = "EVEN"

        sectors.append(SectorDelta(
            sector=i + 1,
            time_start=t_start,
            time_end=t_end,
            ref_avg_speed=round(ref_avg_speed, 1),
            lap_avg_speed=round(lap_avg_speed, 1),
            speed_delta=round(speed_delta, 1),
            ref_brake_point=round(ref_brake_t, 2),
            lap_brake_point=round(lap_brake_t, 2),
            brake_delta=round(brake_delta, 2),
            label=label,
        ))

    summary_stats = _compute_summary(ref_df, lap_df, sectors)

    return LapComparison(
        ref_lap_time=round(ref_duration, 2),
        driver_lap_time=round(lap_duration, 2),
        total_delta=round(total_delta, 2),
        sectors=sectors,
        summary_stats=summary_stats,
    )


def _compute_summary(ref_df, lap_df, sectors: list[SectorDelta]) -> dict:
    """Compute aggregated statistics for the coaching engine."""
    speed_deltas  = [s.speed_delta for s in sectors]
    brake_deltas  = [s.brake_delta for s in sectors]
    worst_sectors = sorted(sectors, key=lambda s: s.speed_delta)[:3]
    best_sectors  = sorted(sectors, key=lambda s: s.speed_delta, reverse=True)[:3]

    return {
        "avg_speed_ref":    round(ref_df["speed"].mean(), 1),
        "avg_speed_lap":    round(lap_df["speed"].mean(), 1),
        "max_speed_ref":    round(ref_df["speed"].max(), 1),
        "max_speed_lap":    round(lap_df["speed"].max(), 1),
        "avg_brake_ref":    round(ref_df["brake"].mean(), 3),
        "avg_brake_lap":    round(lap_df["brake"].mean(), 3),
        "max_brake_ref":    round(ref_df["brake"].max(), 3),
        "max_brake_lap":    round(lap_df["brake"].max(), 3),
        "avg_throttle_ref": round(ref_df["throttle"].mean(), 3),
        "avg_throttle_lap": round(lap_df["throttle"].mean(), 3),
        "n_sectors":        len(sectors),
        "gain_sectors":     sum(1 for s in sectors if s.label == "GAIN"),
        "loss_sectors":     sum(1 for s in sectors if s.label == "LOSS"),
        "even_sectors":     sum(1 for s in sectors if s.label == "EVEN"),
        "worst_sectors":    [f"S{s.sector} ({s.speed_delta:+.1f} km/h)" for s in worst_sectors],
        "best_sectors":     [f"S{s.sector} ({s.speed_delta:+.1f} km/h)" for s in best_sectors],
        "late_braking_count": sum(1 for b in brake_deltas if b > 0.2),
        "early_braking_count": sum(1 for b in brake_deltas if b < -0.2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Chart generation
# ─────────────────────────────────────────────────────────────────────────────
def generate_delta_chart(comparison: LapComparison, output_path: str = "lap_delta.png"):
    """
    Produce a professional lap delta chart:
    - Top: speed delta per sector (bar chart, green/red)
    - Bottom: cumulative time delta across the lap
    """
    sectors = comparison.sectors
    if not sectors:
        print("[lap_compare] No sectors to plot.")
        return

    sector_nums   = [s.sector for s in sectors]
    speed_deltas  = [s.speed_delta for s in sectors]
    cumulative    = np.cumsum([-s.speed_delta * SECTOR_DURATION / 100 for s in sectors])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8),
                                    facecolor="#0d0d0d", gridspec_kw={"height_ratios": [3, 2]})
    fig.suptitle("Lap Delta Analysis — Yas Marina Circuit",
                 color="white", fontsize=16, fontweight="bold", y=0.98)

    # ── Top: Speed delta bars ──────────────────────────────────────────────
    ax1.set_facecolor("#111111")
    colors = ["#00ff88" if d >= 0 else "#ff3355" for d in speed_deltas]
    bars = ax1.bar(sector_nums, speed_deltas, color=colors, width=0.8, alpha=0.85,
                   edgecolor="#ffffff22", linewidth=0.5)

    # Label big deltas
    for bar, val in zip(bars, speed_deltas):
        if abs(val) > 5:
            ax1.text(bar.get_x() + bar.get_width()/2, val + (0.5 if val > 0 else -1.5),
                     f"{val:+.1f}", ha="center", va="bottom" if val > 0 else "top",
                     color="white", fontsize=7, fontweight="bold")

    ax1.axhline(0, color="#ffffff44", linewidth=1.5, linestyle="--")
    ax1.set_ylabel("Speed Delta (km/h)\nDriver vs Reference", color="#aaaaaa", fontsize=10)
    ax1.set_xlabel("")
    ax1.tick_params(colors="#888888")
    ax1.spines[["top", "right", "left", "bottom"]].set_color("#333333")
    ax1.grid(axis="y", color="#222222", linewidth=0.5)

    # Legend
    gain_patch = mpatches.Patch(color="#00ff88", label="GAIN (faster than ref)")
    loss_patch = mpatches.Patch(color="#ff3355", label="LOSS (slower than ref)")
    ax1.legend(handles=[gain_patch, loss_patch], facecolor="#1a1a1a",
               edgecolor="#333333", labelcolor="white", fontsize=9)

    # Annotate total delta
    delta_str = f"{comparison.total_delta:+.2f}s"
    color_str = "#00ff88" if comparison.total_delta <= 0 else "#ff3355"
    ax1.text(0.98, 0.95,
             f"Total: {delta_str}  |  Ref: {comparison.ref_lap_time:.2f}s  |  Driver: {comparison.driver_lap_time:.2f}s",
             transform=ax1.transAxes, ha="right", va="top",
             color=color_str, fontsize=11, fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="#1a1a1a", edgecolor=color_str, linewidth=1.5))

    # ── Bottom: Cumulative delta line ──────────────────────────────────────
    ax2.set_facecolor("#111111")
    ax2.fill_between(sector_nums, cumulative, 0,
                     where=[c < 0 for c in cumulative], color="#00ff8844", step="mid")
    ax2.fill_between(sector_nums, cumulative, 0,
                     where=[c >= 0 for c in cumulative], color="#ff335544", step="mid")
    ax2.plot(sector_nums, cumulative, color="#ffffff", linewidth=2, marker="o",
             markersize=3, markerfacecolor="#ffffff")
    ax2.axhline(0, color="#ffffff44", linewidth=1, linestyle="--")
    ax2.set_ylabel("Cumulative Delta (s)", color="#aaaaaa", fontsize=10)
    ax2.set_xlabel("Mini-Sector (5s intervals)", color="#aaaaaa", fontsize=10)
    ax2.tick_params(colors="#888888")
    ax2.spines[["top", "right", "left", "bottom"]].set_color("#333333")
    ax2.grid(color="#222222", linewidth=0.5)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#0d0d0d")
    plt.close()
    print(f"[lap_compare] Chart saved → {output_path}")


def print_sector_table(comparison: LapComparison):
    """Print a simple ASCII sector table to the console."""
    print(f"\n{'─'*72}")
    print(f"  LAP DELTA  |  Ref: {comparison.ref_lap_time:.2f}s  |  "
          f"Driver: {comparison.driver_lap_time:.2f}s  |  "
          f"Delta: {comparison.total_delta:+.2f}s")
    print(f"{'─'*72}")
    print(f"  {'Sector':>6}  {'T-Start':>7}  {'T-End':>5}  "
          f"{'Ref spd':>7}  {'Lap spd':>7}  {'Δ Speed':>7}  {'Brake Δ':>7}  {'Zone':>5}")
    print(f"{'─'*72}")
    for s in comparison.sectors:
        sign = "▲" if s.speed_delta > 0 else ("▼" if s.speed_delta < 0 else "─")
        print(f"  S{s.sector:>4}   {s.time_start:>6.1f}s  {s.time_end:>4.1f}s  "
              f"{s.ref_avg_speed:>6.1f}  {s.lap_avg_speed:>6.1f}  "
              f"{sign}{abs(s.speed_delta):>5.1f}  {s.brake_delta:>+6.2f}s  {s.label:>5}")
    print(f"{'─'*72}\n")
