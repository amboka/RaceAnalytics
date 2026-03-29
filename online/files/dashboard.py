"""
dashboard.py
============
Live terminal dashboard using the `rich` library.
Shows telemetry gauges, corner info, lap delta, and coaching debrief.
"""

import time
import threading
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.columns import Columns
from rich import box
from rich.progress import BarColumn, Progress, TextColumn
from lap_compare import LapComparison, SectorDelta
from track_corners import Corner


console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Shared state — updated by voice co-driver, read by dashboard renderer
# ─────────────────────────────────────────────────────────────────────────────
class DashboardState:
    def __init__(self):
        self.lock = threading.Lock()
        # Live telemetry
        self.time        = 0.0
        self.speed       = 0.0
        self.throttle    = 0.0
        self.brake       = 0.0
        self.steering    = 0.0
        self.rpm         = 0.0
        self.gear        = 1
        self.gx          = 0.0
        self.gy          = 0.0
        # Context
        self.corner_name = "Straight"
        self.progress    = 0.0
        self.feedback    = ""
        self.feedback_ts = 0.0
        # Comparison
        self.comparison: LapComparison | None = None
        # Debrief
        self.debrief: dict | None = None

    def update(self, row, progress, corner: Corner | None, feedback: str | None):
        with self.lock:
            self.time      = float(row["time"])
            self.speed     = float(row["speed"])
            self.throttle  = float(row["throttle"])
            self.brake     = float(row["brake"])
            self.steering  = float(row.get("steering", 0))
            self.rpm       = float(row.get("rpm", 0))
            self.gear      = int(row.get("gear", 1))
            self.gx        = float(row.get("gx", 0))
            self.gy        = float(row.get("gy", 0))
            self.progress  = progress
            self.corner_name = corner.name if corner else "Straight"
            if feedback:
                self.feedback    = feedback
                self.feedback_ts = time.time()

    def set_comparison(self, comparison: LapComparison):
        with self.lock:
            self.comparison = comparison

    def set_debrief(self, debrief: dict):
        with self.lock:
            self.debrief = debrief


# ─────────────────────────────────────────────────────────────────────────────
# Gauge helpers
# ─────────────────────────────────────────────────────────────────────────────
def _bar(value: float, max_val: float, width: int = 20,
         color_low="green", color_high="red") -> Text:
    """Render a simple ASCII progress bar as a Rich Text object."""
    pct   = min(1.0, max(0.0, value / max_val))
    filled = int(pct * width)
    color = color_high if pct > 0.7 else color_low
    bar = "█" * filled + "░" * (width - filled)
    return Text(f"[{bar}] {value:5.1f}", style=color)


def _speed_color(speed: float) -> str:
    if speed > 180:  return "bold red"
    if speed > 120:  return "bold yellow"
    return "bold green"


# ─────────────────────────────────────────────────────────────────────────────
# Panel builders
# ─────────────────────────────────────────────────────────────────────────────
def _build_telemetry_panel(state: DashboardState) -> Panel:
    """Top-left: live speed, throttle, brake, G-forces."""
    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim", min_width=10)
    t.add_column(min_width=32)

    speed_text = Text(f"{state.speed:6.1f} km/h", style=_speed_color(state.speed))
    t.add_row("SPEED",    speed_text)
    t.add_row("THROTTLE", _bar(state.throttle, 1.0, color_low="green", color_high="bright_green"))
    t.add_row("BRAKE",    _bar(state.brake,    1.0, color_low="yellow", color_high="red"))
    t.add_row("STEERING", Text(f"{state.steering:+.3f}", style="cyan"))
    t.add_row("GEAR",     Text(f"  {state.gear}", style="bold magenta"))
    t.add_row("RPM",      Text(f"{state.rpm:>7,.0f}", style="yellow"))
    t.add_row("Gx/Gy",   Text(f"{state.gx:+.2f}g / {state.gy:+.2f}g", style="dim cyan"))
    t.add_row("TIME",     Text(f"{state.time:6.2f}s", style="dim"))

    return Panel(t, title="[bold white]TELEMETRY[/]",
                 border_style="bright_blue", padding=(0, 1))


def _build_track_panel(state: DashboardState) -> Panel:
    """Top-right: current corner, track progress, co-driver feedback."""
    # Feedback fades after 4s
    fb_age  = time.time() - state.feedback_ts
    fb_text = Text(f"⚡ {state.feedback}", style="bold yellow") if fb_age < 4 else Text("")

    # Progress bar
    prog_filled = int(state.progress / 5)  # 0–20 chars
    prog_bar    = "▶" * prog_filled + "·" * (20 - prog_filled)

    t = Table.grid(padding=(0, 1))
    t.add_column(style="dim", min_width=12)
    t.add_column(min_width=28)
    t.add_row("CORNER",   Text(state.corner_name, style="bold cyan"))
    t.add_row("PROGRESS", Text(f"[{prog_bar}] {state.progress:.1f}%", style="blue"))
    t.add_row("",         Text(""))
    t.add_row("CO-DRIVER", fb_text)

    return Panel(t, title="[bold white]TRACK POSITION[/]",
                 border_style="cyan", padding=(0, 1))


def _build_delta_panel(state: DashboardState) -> Panel:
    """Middle: sector delta table."""
    if state.comparison is None:
        return Panel("[dim]Awaiting lap comparison...[/]",
                     title="[bold white]LAP DELTA[/]", border_style="dim")

    comp = state.comparison
    delta_color = "green" if comp.total_delta <= 0 else "red"
    delta_str   = f"{comp.total_delta:+.2f}s"

    t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold dim",
              expand=True, padding=(0, 1))
    t.add_column("S#",    width=4,  style="dim")
    t.add_column("Δ Speed", width=9)
    t.add_column("Brake Δ", width=9)
    t.add_column("Zone",  width=6)

    # Highlight current sector based on progress
    current_sector = int(state.progress / 100 * len(comp.sectors))

    for i, s in enumerate(comp.sectors[:16]):  # show max 16 rows
        style = "on dark_blue" if i == current_sector else ""
        d_col = "green" if s.speed_delta >= 0 else "red"
        t.add_row(
            f"S{s.sector}",
            Text(f"{s.speed_delta:+.1f}", style=d_col),
            Text(f"{s.brake_delta:+.2f}s", style="cyan"),
            Text(s.label, style=d_col),
            style=style
        )

    header = Text(f"  Ref: {comp.ref_lap_time:.2f}s  |  Driver: {comp.driver_lap_time:.2f}s  |  Total: ", style="dim")
    header.append(delta_str, style=f"bold {delta_color}")

    return Panel(
        t,
        title=f"[bold white]LAP DELTA[/]  {header}",
        border_style="yellow"
    )


def _build_debrief_panel(state: DashboardState) -> Panel:
    """Bottom: coaching debrief (appears after lap ends)."""
    if state.debrief is None:
        return Panel("[dim]Post-lap debrief will appear here after the session...[/]",
                     title="[bold white]🏁 RACE ENGINEER DEBRIEF[/]", border_style="dim")

    d    = state.debrief
    text = Text()

    rating = d.get("lap_rating", "?")
    text.append(f"  Lap Rating: {'⭐' * int(rating)}  ({rating}/10)\n\n", style="yellow")

    text.append("  ❌ TOP MISTAKES:\n", style="bold red")
    for m in d.get("mistakes", []):
        sev_map = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        sev = sev_map.get(m.get("severity", "medium"), "🟡")
        text.append(f"  {sev} {m.get('title','')}\n", style="bold")
        text.append(f"     {m.get('detail','')}\n", style="dim")

    text.append("\n  ✅ IMPROVEMENTS:\n", style="bold green")
    for imp in d.get("improvements", []):
        text.append(f"  💚 {imp.get('title','')}\n", style="bold")
        text.append(f"     {imp.get('detail','')}\n", style="dim")

    text.append(f"\n  🎯 Focus: {d.get('focus_area','')}\n", style="bold cyan")
    text.append(f"\n  💬 \"{d.get('motivation','')}\"", style="italic yellow")

    return Panel(text, title="[bold white]🏁 RACE ENGINEER DEBRIEF[/]",
                 border_style="bright_yellow", padding=(0, 1))


def _build_header() -> Panel:
    """Top banner."""
    t = Text(justify="center")
    t.append("A2RL  ·  ", style="dim")
    t.append("YAS MARINA CIRCUIT", style="bold white")
    t.append("  ·  ", style="dim")
    t.append("AI RACE ENGINEER", style="bold red")
    t.append("  ·  ", style="dim")
    t.append("LIVE SESSION", style="bold green")
    return Panel(t, border_style="bright_blue", padding=(0, 0))


# ─────────────────────────────────────────────────────────────────────────────
# Layout builder
# ─────────────────────────────────────────────────────────────────────────────
def _build_layout(state: DashboardState) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header",  size=3),
        Layout(name="top",     size=14),
        Layout(name="middle",  size=22),
        Layout(name="bottom",  minimum_size=12),
    )
    layout["top"].split_row(
        Layout(name="telemetry", ratio=1),
        Layout(name="track",     ratio=1),
    )
    layout["header"].update(_build_header())
    layout["telemetry"].update(_build_telemetry_panel(state))
    layout["track"].update(_build_track_panel(state))
    layout["middle"].update(_build_delta_panel(state))
    layout["bottom"].update(_build_debrief_panel(state))
    return layout


# ─────────────────────────────────────────────────────────────────────────────
# Main dashboard runner
# ─────────────────────────────────────────────────────────────────────────────
def run_dashboard(state: DashboardState, stop_event: threading.Event):
    """
    Runs the Rich Live dashboard in the current thread.
    Call this BEFORE starting the voice co-driver thread.
    """
    with Live(console=console, refresh_per_second=10, screen=True) as live:
        while not stop_event.is_set():
            with state.lock:
                layout = _build_layout(state)
            live.update(layout)
            time.sleep(0.1)

    # Final static render after session ends
    console.clear()
    if state.debrief:
        from coaching_engine import print_debrief
        print_debrief(state.debrief, state.comparison)
