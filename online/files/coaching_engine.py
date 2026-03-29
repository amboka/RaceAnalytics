"""
coaching_engine.py
==================
Sends lap statistics to Claude claude-sonnet-4-20250514 and returns a structured
race engineer debrief: mistakes, improvements, and motivation.
"""

import json
import os
import anthropic
from lap_compare import LapComparison


# ─────────────────────────────────────────────────────────────────────────────
# System prompt — defines Claude's persona as a race engineer
# ─────────────────────────────────────────────────────────────────────────────
RACE_ENGINEER_SYSTEM = """You are an elite motorsport race engineer and driver coach 
with 20 years of experience in Formula racing, including work with autonomous racing 
programmes like A2RL at Yas Marina Circuit in Abu Dhabi.

Your job is to analyse lap telemetry data and give precise, actionable coaching 
feedback to the driver. You speak with authority, use racing terminology, and you 
balance technical precision with motivational energy.

You always respond with ONLY valid JSON — no markdown, no explanation outside the JSON.
The JSON must exactly follow this schema:
{
  "mistakes": [
    {"title": "string", "detail": "string", "sector": "string", "severity": "high|medium|low"},
    {"title": "string", "detail": "string", "sector": "string", "severity": "high|medium|low"},
    {"title": "string", "detail": "string", "sector": "string", "severity": "high|medium|low"}
  ],
  "improvements": [
    {"title": "string", "detail": "string"},
    {"title": "string", "detail": "string"}
  ],
  "lap_rating": "integer 1-10",
  "focus_area": "string — single most important thing to improve next lap",
  "motivation": "string — one punchy, genuine motivational line from engineer to driver"
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Main coaching function
# ─────────────────────────────────────────────────────────────────────────────
def get_coaching_debrief(comparison: LapComparison) -> dict:
    """
    Send lap comparison stats to Claude and return a structured debrief dict.
    Falls back to a rule-based debrief if the API call fails.
    """
    stats = comparison.summary_stats
    sectors = comparison.sectors

    # Build a concise telemetry summary for the prompt
    worst_3 = sorted(sectors, key=lambda s: s.speed_delta)[:3]
    best_2  = sorted(sectors, key=lambda s: s.speed_delta, reverse=True)[:2]

    prompt = f"""
Analyse this lap telemetry comparison and give your race engineer debrief.

LAP OVERVIEW:
- Reference (good lap) time: {comparison.ref_lap_time:.2f}s
- Driver lap time: {comparison.driver_lap_time:.2f}s  
- Total delta: {comparison.total_delta:+.2f}s ({'faster' if comparison.total_delta < 0 else 'slower'} than reference)
- Track: Yas Marina Circuit, Abu Dhabi (A2RL autonomous racing)

SPEED ANALYSIS:
- Reference avg speed: {stats['avg_speed_ref']} km/h | Driver avg: {stats['avg_speed_lap']} km/h
- Reference top speed: {stats['max_speed_ref']} km/h | Driver top: {stats['max_speed_lap']} km/h

BRAKING ANALYSIS:
- Reference avg brake: {stats['avg_brake_ref']:.3f} | Driver avg brake: {stats['avg_brake_lap']:.3f}
- Reference max brake: {stats['max_brake_ref']:.3f} | Driver max brake: {stats['max_brake_lap']:.3f}
- Late braking events: {stats['late_braking_count']} sectors | Early braking: {stats['early_braking_count']} sectors

THROTTLE:
- Reference avg throttle: {stats['avg_throttle_ref']:.3f} | Driver avg: {stats['avg_throttle_lap']:.3f}

SECTOR BREAKDOWN ({stats['n_sectors']} mini-sectors of 5s each):
- GAIN sectors (driver faster): {stats['gain_sectors']}
- LOSS sectors (driver slower): {stats['loss_sectors']}
- EVEN sectors: {stats['even_sectors']}

WORST 3 SECTORS (biggest speed losses):
{chr(10).join(f"- {w}" for w in stats['worst_sectors'])}

BEST 2 SECTORS (biggest speed gains):
{chr(10).join(f"- {b}" for b in stats['best_sectors'])}

DETAILED WORST SECTORS:
{chr(10).join(f"- S{s.sector} ({s.time_start:.0f}-{s.time_end:.0f}s): ref {s.ref_avg_speed} km/h, driver {s.lap_avg_speed} km/h, brake delta {s.brake_delta:+.2f}s" for s in worst_3)}

Respond with ONLY the JSON debrief. Be specific about sectors and times.
Use real Yas Marina corner names where relevant (T1, T5 Hotel Hairpin, T8 Marina Curve, etc).
"""

    try:
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=RACE_ENGINEER_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text.strip()

        # Strip accidental markdown code fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        debrief = json.loads(raw)
        return debrief

    except anthropic.APIError as e:
        print(f"[coaching_engine] Claude API error: {e}")
        return _fallback_debrief(comparison)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[coaching_engine] JSON parse error: {e}")
        return _fallback_debrief(comparison)
    except Exception as e:
        print(f"[coaching_engine] Unexpected error: {e}")
        return _fallback_debrief(comparison)


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based fallback (works offline, no API key needed)
# ─────────────────────────────────────────────────────────────────────────────
def _fallback_debrief(comparison: LapComparison) -> dict:
    """Generate a debrief using pure rules when Claude API is unavailable."""
    stats   = comparison.sectors
    summary = comparison.summary_stats
    delta   = comparison.total_delta

    mistakes = []
    improvements = []

    # Detect speed loss
    if summary["avg_speed_lap"] < summary["avg_speed_ref"] - 5:
        mistakes.append({
            "title": "Carrying insufficient speed",
            "detail": f"Average speed {summary['avg_speed_lap']:.0f} vs ref {summary['avg_speed_ref']:.0f} km/h — "
                      f"you're leaving {summary['avg_speed_ref'] - summary['avg_speed_lap']:.0f} km/h on the table.",
            "sector": summary["worst_sectors"][0] if summary["worst_sectors"] else "Multiple",
            "severity": "high"
        })

    # Detect braking issues
    if summary["early_braking_count"] > 2:
        mistakes.append({
            "title": "Braking too early",
            "detail": f"{summary['early_braking_count']} sectors with early trail braking — "
                      "push the braking point 10–15m later into the corners.",
            "sector": summary["worst_sectors"][1] if len(summary["worst_sectors"]) > 1 else "Multiple",
            "severity": "high"
        })

    if summary["avg_throttle_lap"] < summary["avg_throttle_ref"] - 0.05:
        mistakes.append({
            "title": "Low throttle application",
            "detail": "Average throttle below reference — commit to the throttle earlier on corner exit.",
            "sector": summary["worst_sectors"][2] if len(summary["worst_sectors"]) > 2 else "Multiple",
            "severity": "medium"
        })

    if not mistakes:
        mistakes.append({
            "title": "Inconsistent sector pace",
            "detail": f"{summary['loss_sectors']} loss sectors vs {summary['gain_sectors']} gain sectors — "
                      "focus on consistency over raw speed.",
            "sector": "Multiple",
            "severity": "medium"
        })

    # Improvements
    if summary["gain_sectors"] > 0:
        improvements.append({
            "title": "Strong sector performance",
            "detail": f"{summary['gain_sectors']} sectors faster than reference — "
                      f"best: {summary['best_sectors'][0] if summary['best_sectors'] else 'S1'}."
        })

    if summary["max_speed_lap"] >= summary["max_speed_ref"] - 5:
        improvements.append({
            "title": "Good straight-line speed",
            "detail": f"Top speed {summary['max_speed_lap']:.0f} km/h is competitive with reference."
        })
    else:
        improvements.append({
            "title": "Braking confidence building",
            "detail": "Brake pressure is consistent — next step is timing, not force."
        })

    rating = max(1, min(10, 8 - int(abs(delta) / 2)))

    return {
        "mistakes":    mistakes[:3],
        "improvements": improvements[:2],
        "lap_rating":  rating,
        "focus_area":  mistakes[0]["title"] if mistakes else "Consistency",
        "motivation":  "The data doesn't lie — trust the process and the lap time will follow."
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pretty printer for the debrief
# ─────────────────────────────────────────────────────────────────────────────
def print_debrief(debrief: dict, comparison: LapComparison):
    """Print formatted coaching debrief to console (no rich required)."""
    delta = comparison.total_delta
    delta_str = f"{delta:+.2f}s"

    print("\n" + "═"*70)
    print("  🏁  POST-LAP DEBRIEF — Race Engineer Report")
    print("═"*70)
    print(f"  Lap Time: {comparison.driver_lap_time:.2f}s  |  "
          f"Ref: {comparison.ref_lap_time:.2f}s  |  Delta: {delta_str}")
    print(f"  Lap Rating: {'⭐' * debrief.get('lap_rating', 5)}  "
          f"({debrief.get('lap_rating', '?')}/10)")
    print("─"*70)

    print("\n  ❌  TOP MISTAKES:")
    for i, m in enumerate(debrief.get("mistakes", []), 1):
        sev = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(m.get("severity", "medium"), "🟡")
        print(f"\n  {i}. {sev}  {m.get('title', 'Unknown')}")
        print(f"     Sector: {m.get('sector', '—')}")
        print(f"     {m.get('detail', '')}")

    print("\n  ✅  IMPROVEMENTS vs LAST LAP:")
    for i, imp in enumerate(debrief.get("improvements", []), 1):
        print(f"\n  {i}. 💚  {imp.get('title', 'Unknown')}")
        print(f"     {imp.get('detail', '')}")

    print(f"\n  🎯  FOCUS NEXT LAP:  {debrief.get('focus_area', '—')}")
    print(f"\n  💬  ENGINEER:  \"{debrief.get('motivation', '')}\"")
    print("\n" + "═"*70 + "\n")
