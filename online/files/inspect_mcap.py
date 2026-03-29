"""
inspect_mcap.py
===============
Run this FIRST to discover what topics are in your MCAP files.
This tells you the exact topic names to update in mcap_reader.py's TOPIC_MAP.

Usage:
    python inspect_mcap.py hackathon_good_lap.mcap
    python inspect_mcap.py hackathon_good_lap.mcap --sample   # print 1 message per topic
"""

import sys
import argparse
import json

try:
    from mcap.reader import make_reader
except ImportError:
    print("ERROR: mcap library not installed.")
    print("Run: pip install mcap mcap-ros2-support")
    sys.exit(1)


def inspect(mcap_path: str, sample: bool = False):
    print(f"\n{'═'*70}")
    print(f"  MCAP Inspector — {mcap_path}")
    print(f"{'═'*70}\n")

    topics = {}        # topic → {schema, count}
    samples = {}       # topic → first raw message bytes

    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        for schema, channel, message in reader.iter_messages():
            t = channel.topic
            if t not in topics:
                topics[t] = {
                    "schema":   schema.name if schema else "unknown",
                    "encoding": channel.message_encoding,
                    "count":    0,
                }
                if sample:
                    samples[t] = message.data[:200]  # first 200 bytes
            topics[t]["count"] += 1

    print(f"  Found {len(topics)} topics across all schemas:\n")
    print(f"  {'Topic':<55} {'Schema':<30} {'Count':>8}")
    print(f"  {'─'*55} {'─'*30} {'─'*8}")

    for topic, info in sorted(topics.items()):
        print(f"  {topic:<55} {info['schema']:<30} {info['count']:>8,}")

    # Suggest TOPIC_MAP entries
    print(f"\n{'─'*70}")
    print("  SUGGESTED TOPIC_MAP ENTRIES (paste into mcap_reader.py):\n")
    suggestions = {
        "speed":    [],
        "throttle": [],
        "brake":    [],
        "steering": [],
        "imu":      [],
        "gps":      [],
        "rpm":      [],
        "gear":     [],
    }
    keywords = {
        "speed":    ["speed", "velocity"],
        "throttle": ["throttle", "accel"],
        "brake":    ["brake", "braking"],
        "steering": ["steering", "steer"],
        "imu":      ["imu", "inertial", "acceleration"],
        "gps":      ["gps", "gnss", "navsatfix", "fix"],
        "rpm":      ["rpm", "engine"],
        "gear":     ["gear", "transmission"],
    }
    for topic in topics:
        tl = topic.lower()
        for key, kws in keywords.items():
            if any(kw in tl for kw in kws):
                suggestions[key].append(topic)

    for key, matches in suggestions.items():
        if matches:
            print(f"  \"{key}\": {json.dumps(matches)},")

    print(f"\n{'═'*70}\n")

    if sample and samples:
        print("  RAW SAMPLE DATA (first message per topic, hex):\n")
        for topic, data in list(samples.items())[:5]:
            print(f"  {topic}:")
            print(f"    {data.hex()[:80]}...\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mcap_file", help="Path to .mcap file")
    parser.add_argument("--sample", action="store_true",
                        help="Print raw bytes sample for each topic")
    args = parser.parse_args()
    inspect(args.mcap_file, sample=args.sample)
