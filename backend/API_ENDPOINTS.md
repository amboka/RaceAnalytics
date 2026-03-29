# Frontend API Handoff

This document describes the backend API endpoints currently exposed under the Django `telemetry` app.

Base path for all endpoints:

```text
/api/
```

All endpoints are currently:
- `GET`
- JSON responses
- read-only
- unauthenticated in this project

## Quick Endpoint List

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/getLapTime` | Lap/section timing comparison between `slow` and `fast` |
| `GET` | `/api/topSpeed` | Top speed reached in each race present in the DB |
| `GET` | `/api/timeLostPerSection` | Time lost per hard-coded lap section (`slow - fast`) |
| `GET` | `/api/brakingEfficiency` | Overall braking-efficiency summary plus per-section breakdown |
| `GET` | `/api/gripUtilization` | Overall grip/tyre-utilization summary plus per-section breakdown |
| `GET` | `/api/engine/laps` | Detect complete laps inside one race/session and return lap IDs |
| `GET` | `/api/engine/throttleComparison` | Return an aligned lap-to-lap throttle comparison payload for plotting |
| `GET` | `/api/engine/rpm/comparison` | Return aligned RPM comparison against a reference lap |
| `GET` | `/api/engine/gearboxAndShift/comparison` | Return aligned gearbox and shift-timing comparison against a reference lap |
| `GET` | `/api/breaks/pressureComparison` | Return aligned brake-pressure comparison (lap vs reference) with braking zones |
| `GET` | `/api/breaks/temperatureComparison` | Return brake-temperature trace + hottest-zone summary with optional lap reference overlay |
| `GET` | `/api/breaks/trailBrakingAnalysis` | Return detected trail-braking zones with start/peak/release/end metrics and reference deltas |
| `GET` | `/api/breaks/releaseThrottleTransition` | Return brake-release to throttle-application transition zones plus aligned local transition traces |
| `GET` | `/api/steering/getSteeringAngle` | Return 5Hz steering-angle traces for all races |
| `GET` | `/api/steering/getOverUnderSteer` | Return 5Hz oversteer/understeer classification using yaw-rate error model |
| `GET` | `/api/steering/getSlipCoachingMetrics` | Return 5Hz slip-window and grip-balance coaching metrics |

---

## Shared Concepts

### Current race assumptions
Several analytics endpoints are currently demo-oriented and compare:
- `slow` = conservative / slower lap
- `fast` = reference / faster lap

Endpoints still based on these demo assumptions:
- `/api/getLapTime`
- `/api/timeLostPerSection`
- `/api/brakingEfficiency` (can be overridden with `race_id` and `reference_race_id` parameters)
- `/api/gripUtilization` (can be overridden with `race_id` and `reference_race_id` parameters)

The new engine endpoints are more flexible and work on detected laps rather than only on hard-coded section windows.

### Time-range filtering
Several analytics endpoints support optional `start_ns` and `end_ns` query parameters for custom time-window analysis:
- `/api/topSpeed` — Returns top speed within an optional time range
- `/api/brakingEfficiency` — Analyzes braking metrics within an optional time range
- `/api/gripUtilization` — Analyzes grip metrics within an optional time range

When time-range parameters are provided to `brakingEfficiency` or `gripUtilization`:
- Data is analyzed as a single "full" section
- No comparison score is computed (since there is no reference timeframe)
- Raw metrics are returned instead
- **Both `start_ns` and `end_ns` must be provided together** (or neither)

This enables on-track analysis of specific lap sections or custom telemetry windows.

### Laps vs races
A very important distinction for the frontend:
- `race_id` in the DB is a session label such as `slow` or `fast`
- a single `race_id` can contain a full lap or multiple laps
- the engine API detects complete laps and gives them IDs like `fast:1` or `slow:1`

If the frontend wants a reliable lap-to-lap comparison, it should think in terms of `lapId`, not only `race_id`.

### Units
- timestamps are in nanoseconds unless otherwise stated
- elapsed times in some payloads are in milliseconds (`ms`)
- speeds are in meters per second (`mps`)
- acceleration is in meters per second squared (`mps2`)
- distances are in meters (`m`)
- pressures are in Pascals (`Pa`)
- throttle in the engine comparison API is returned in percent (`0..100`)
- RPM is returned in revolutions per minute (`rpm`)
- steering angle is returned in radians (`rad`) and degrees (`deg`)

### Common error format
Most endpoints use one of these error shapes.

`400 Bad Request`

```json
{
  "error": "..."
}
```

or, in some cases:

```json
{
  "error": "...",
  "details": "..."
}
```

`404 Not Found`

```json
{
  "error": "..."
}
```

`500 Internal Server Error`

```json
{
  "error": "Unable to compute ...",
  "details": "..."
}
```

---

## 1. `GET /api/getLapTime`

### What it is for
Returns timing comparison between the `slow` and `fast` demo laps.

It supports:
- full lap timing when no query param is provided
- section timing when `segment` is provided

### Query params

| Param | Required | Type | Allowed values | Notes |
|---|---|---|---|---|
| `segment` | No | string | `snake`, `long`, `corner` | If omitted or empty, backend uses `full` |

### Unsupported query params
If the request includes `start_ns` or `end_ns`, the endpoint returns `400`.

### Response shape

```json
{
  "header": {
    "segment": "full"
  },
  "slow_race": {
    "race_id": "slow",
    "record_count": 188948,
    "db_timestamp_unit": "ns",
    "db_start": {
      "value": 1763219626170019753,
      "seconds": 1763219626.1700199
    },
    "db_end": {
      "value": 1763219707431832335,
      "seconds": 1763219707.4318323
    },
    "segment": {
      "name": "full",
      "start": {
        "value": 1763219627202000000,
        "seconds": 1763219627.202
      },
      "end": {
        "value": 1763219699245616802,
        "seconds": 1763219699.245617
      }
    },
    "duration": {
      "value": 72043616802,
      "unit": "ns",
      "milliseconds": 72043.616802,
      "seconds": 72.043616802
    }
  },
  "fast_race": {
    "race_id": "fast",
    "record_count": 172558,
    "db_timestamp_unit": "ns",
    "duration": {
      "value": 64959621899,
      "unit": "ns",
      "milliseconds": 64959.621899,
      "seconds": 64.959621899
    }
  },
  "difference": {
    "slow_minus_fast": {
      "value": 7083994903,
      "unit": "ns",
      "seconds": 7.083994903
    }
  }
}
```

### Frontend usage notes
- Use for overview timing cards.
- Use `segment` for section-level timing cards.
- Positive `slow_minus_fast` means `slow` took longer.

---

## 2. `GET /api/topSpeed`

### What it is for
Returns the maximum vehicle speed reached in each race stored in the database. Can optionally filter by a time range.

### Query params

| Param | Required | Type | Notes |
|---|---|---|---|
| `start_ns` | No | integer | Start timestamp in nanoseconds. If provided, `end_ns` must also be provided. |
| `end_ns` | No | integer | End timestamp in nanoseconds (exclusive). If provided, `start_ns` must also be provided. |

### How it works
It reads:
- `TopicStateEstimation.v_mps`

For each `race_id`, it returns `MAX(v_mps)`. If time range parameters are provided, only data within `[start_ns, end_ns)` is considered.

### Response shape

```json
{
  "topSpeeds": [
    {
      "race_id": "fast",
      "top_speed_mps": 68.24381873500963
    },
    {
      "race_id": "slow",
      "top_speed_mps": 68.37652097798751
    }
  ]
}
```

### Error cases
- Returns `400` if only one of `start_ns` or `end_ns` is provided (both required together).
- Returns `400` if the time parameters cannot be parsed as integers.

### Frontend usage notes
- Good for a simple comparison card or table.
- Convert to km/h if needed with `mps * 3.6`.
- Use `start_ns` and `end_ns` to filter top speed by lap section or custom time window.

---

## 3. `GET /api/timeLostPerSection`

### What it is for
Returns how much slower the `slow` lap was than the `fast` lap in each hard-coded section.

### Query params
None.

### Response shape

```json
{
  "timeLostPerSection": {
    "snake": 3684062533,
    "long": 1438238604,
    "corner": 1961693766
  }
}
```

### Frontend usage notes
- Best for compact bar charts or KPI tiles.
- Values are in nanoseconds.

---

## 4. `GET /api/brakingEfficiency`

### What it is for
Returns an overall braking-efficiency score for a lap compared with a reference lap, plus a per-section braking breakdown. Can optionally analyze a custom time range without reference comparison.

### Query params

| Param | Required | Type | Default | Notes |
|---|---|---|---|---|
| `race_id` | No | string | `slow` | The race/session ID to analyze. |
| `reference_race_id` | No | string | `fast` | The reference race for comparison. Ignored when time range is provided. |
| `start_ns` | No | integer | — | Start timestamp in nanoseconds. If provided, `end_ns` must also be provided. |
| `end_ns` | No | integer | — | End timestamp in nanoseconds (exclusive). If provided, `start_ns` must also be provided. |

### Comparison behavior
**Without time range:** Returns score and comparison against reference lap (currently defaults to comparing `slow` vs `fast`).

**With time range:** Analyzes braking metrics within the specified timeframe as a single "full" section. No comparison score is provided since there is no reference window for comparison.

### Response shape (standard, without time range)

```json
{
  "brakingEfficiency": {
    "raceId": "slow",
    "referenceRaceId": "fast",
    "score": 88.91,
    "rating": "strong",
    "timeLostUnderBraking": {
      "value": 1429979110,
      "unit": "ns",
      "seconds": 1.42997911
    },
    "sectionCount": 3,
    "weakestSection": "snake",
    "sections": [
      {
        "section": "snake",
        "status": "ok",
        "score": 79.6,
        "time_lost": {
          "value": 1020014358,
          "unit": "ns",
          "seconds": 1.020014358
        },
        "penalties": {
          "distance": 0.2456,
          "minimum_speed": 0.1587,
          "effort": 0.1896
        },
        "race": {
          "brake_distance_m": 176.69,
          "entry_speed_mps": 57.33,
          "min_speed_mps": 22.02
        },
        "reference": {
          "...": "same shape as race"
        }
      }
    ]
  }
}
```

### Response shape (with time range)

```json
{
  "brakingEfficiency": {
    "raceId": "slow",
    "timeRange": {
      "start_ns": 1763219835170378101,
      "end_ns": 1763219900130000000,
      "duration_ns": 64959621899
    },
    "score": null,
    "rating": null,
    "timeLostUnderBraking": null,
    "sectionCount": 1,
    "weakestSection": null,
    "sections": [
      {
        "section": "full",
        "status": "ok",
        "score": null,
        "weight": null,
        "time_lost": null,
        "penalties": null,
        "race": {
          "brake_distance_m": 176.69,
          "entry_speed_mps": 57.33,
          "min_speed_mps": 22.02
        },
        "reference": null
      }
    ]
  }
}
```

### Error cases
- Returns `400` if only one of `start_ns` or `end_ns` is provided (both required together).
- Returns `400` if unable to find data for the specified `race_id` or reference race.

### Frontend usage notes
- Use `score` and `rating` for the main summary card (standard mode).
- Use `timeLostUnderBraking.seconds` as the key supporting metric.
- Use `sections[]` for detail charts or section comparison UI.
- For time-range mode, display raw braking metrics without scoring (useful for on-track analysis).

---

## 5. `GET /api/gripUtilization`

### What it is for
Returns an overall grip / tyre-utilization score for a lap compared with a reference lap, plus a per-section breakdown. Can optionally analyze a custom time range without reference comparison.

### Query params

| Param | Required | Type | Default | Notes |
|---|---|---|---|---|
| `race_id` | No | string | `slow` | The race/session ID to analyze. |
| `reference_race_id` | No | string | `fast` | The reference race for comparison. Ignored when time range is provided. |
| `start_ns` | No | integer | — | Start timestamp in nanoseconds. If provided, `end_ns` must also be provided. |
| `end_ns` | No | integer | — | End timestamp in nanoseconds (exclusive). If provided, `start_ns` must also be provided. |

### Comparison behavior
**Without time range:** Returns score and comparison against reference lap (currently defaults to comparing `slow` vs `fast`).

**With time range:** Analyzes grip utilization metrics within the specified timeframe as a single "full" section. No comparison score is provided since there is no reference window for comparison.

### Response shape (standard, without time range)

```json
{
  "gripUtilization": {
    "raceId": "slow",
    "referenceRaceId": "fast",
    "score": 84.38,
    "rating": "fair",
    "overallStatus": "underutilizing_grip",
    "sectionCount": 3,
    "weakestSection": "long",
    "sections": [
      {
        "section": "snake",
        "status": "underutilizing_grip",
        "score": 84.79,
        "ratios": {
          "cornering_load": 0.8188,
          "corner_speed": 0.8521,
          "slip_angle": 0.6665,
          "combined_slip": 0.9878
        },
        "penalties": {
          "cornering_load": 0.1812,
          "corner_speed": 0.1479,
          "balance": 0.1522,
          "combined_slip": 0.0
        }
      }
    ]
  }
}
```

### Response shape (with time range)

```json
{
  "gripUtilization": {
    "raceId": "slow",
    "timeRange": {
      "start_ns": 1763219835170378101,
      "end_ns": 1763219900130000000,
      "duration_ns": 64959621899
    },
    "score": null,
    "rating": null,
    "overallStatus": null,
    "sectionCount": 1,
    "weakestSection": null,
    "sections": [
      {
        "section": "full",
        "status": "ok",
        "score": null,
        "weight": null,
        "race": {
          "active_sample_count": 2458,
          "active_duration": {
            "value": 64959621899,
            "unit": "ns",
            "seconds": 64.959621899
          },
          "mean_abs_lateral_accel_mps2": 5.41,
          "peak_abs_lateral_accel_mps2": 12.38,
          "mean_speed_mps": 42.15
        },
        "reference": null
      }
    ]
  }
}
```

### Error cases
- Returns `400` if only one of `start_ns` or `end_ns` is provided (both required together).
- Returns `400` if unable to find data for the specified `race_id` or reference race.

### Frontend usage notes
- Use `score` and `overallStatus` on the main grip card (standard mode).
- Use section `status` directly for badges or callouts.
- Use `ratios` for compact visual comparisons.
- For time-range mode, display raw grip metrics without scoring (useful for on-track analysis).

---

## 6. `GET /api/engine/laps`

### What it is for
Returns detected complete laps for one race/session.

This endpoint exists to support lap-to-lap comparison features. The throttle comparison endpoint works best when the frontend first asks the backend which lap IDs are available.

### Why this endpoint exists
The DB stores telemetry by `race_id` and timestamp, not by pre-made lap entity. So before the frontend can ask for “compare my lap to the reference lap,” the backend needs to detect where a full lap starts and ends.

This endpoint gives the frontend stable IDs such as:
- `fast:1`
- `slow:1`

### Query params

| Param | Required | Type | Notes |
|---|---|---|---|
| `race_id` | Yes | string | Example: `fast`, `slow` |

### How lap detection works
At a high level, the backend:
1. loads `TopicStateEstimation` samples for the requested race
2. orders them by timestamp
3. looks for a return near the starting position after enough time and distance have elapsed
4. marks that window as a complete lap

This is a pragmatic demo-oriented lap detector. It is designed to work well on the current hackathon dataset.

### Response shape

```json
{
  "raceId": "fast",
  "lapCount": 1,
  "bestLapId": "fast:1",
  "laps": [
    {
      "lapId": "fast:1",
      "lapNumber": 1,
      "startNs": 1763219835170015771,
      "endNs": 1763219899920028760,
      "durationNs": 64750012989,
      "sampleCount": 6476,
      "pathLengthM": 2968.851,
      "isComplete": true,
      "quality": "good",
      "isBestLap": true
    }
  ]
}
```

### Field-by-field explanation

| Field | Meaning |
|---|---|
| `raceId` | the race/session that was scanned |
| `lapCount` | number of complete laps the backend detected |
| `bestLapId` | the fastest detected lap for that race |
| `lapId` | stable lap identifier used by other engine endpoints |
| `lapNumber` | 1-based lap sequence inside the race/session |
| `startNs` | first timestamp of the lap |
| `endNs` | last timestamp of the lap |
| `durationNs` | `endNs - startNs` |
| `sampleCount` | number of valid state-estimation samples in the lap |
| `pathLengthM` | approximate driven path length over the lap |
| `isComplete` | whether the backend considers it a full lap |
| `quality` | simple qualitative label for the detected lap |
| `isBestLap` | whether this lap is the fastest one in that race |

### Frontend usage notes
- Call this first if the UI lets users pick a lap.
- For the current dataset, it is also useful as a sanity check that the backend found the expected complete lap.
- If `lapCount = 0`, the frontend should treat the race as not comparable for lap-to-lap plot features.

---

## 7. `GET /api/engine/throttleComparison`

### What it is for
Returns the full data payload needed to draw a lap-to-lap throttle comparison plot.

This is the main endpoint for the engine/throttle page.

### What problem this endpoint solves
Two laps cannot be compared correctly by raw time because they reach the same point on track at different times. If the frontend plotted throttle against timestamp only, the result would be visually misleading.

This endpoint fixes that by aligning both laps to the same track-progress axis.

### Alignment model
The comparison is built like this:
1. select a lap and a reference lap
2. load their `TopicStateEstimation` traces
3. use `x_m` / `y_m` position to build a path for the reference lap
4. project the other lap onto that same reference path
5. resample both throttle traces onto a shared distance/progress grid
6. return aligned series for plotting

This means the frontend receives throttle values at equivalent places on track, not just equivalent times.

### Throttle source used
The endpoint currently uses:
- `TopicStateEstimation.gas`

The backend normalizes it from a `0..1` signal to `0..100` percent before returning it.

### Query params

| Param | Required | Type | Notes |
|---|---|---|---|
| `lap_id` | No | string | Example: `slow:1` |
| `lap_number` | No | integer | Used together with `race_id` |
| `race_id` | No | string | Defaults to `slow` if no `lap_id` is given |
| `reference_lap_id` | No | string | Example: `fast:1` |
| `reference_lap_number` | No | integer | Used together with `reference_race_id` |
| `reference_race_id` | No | string | Defaults to `fast` if no `reference_lap_id` is given |
| `points` | No | integer | Resampled point count, must be between `200` and `1200`; default `600` |

### Selection behavior
If the request does not provide explicit lap IDs:
- the backend resolves the fastest detected lap for `race_id`
- the backend resolves the fastest detected lap for `reference_race_id`

So this is valid and convenient for the demo:

```text
/api/engine/throttleComparison?race_id=slow&reference_race_id=fast
```

And this is the explicit version if the frontend already has selected lap IDs:

```text
/api/engine/throttleComparison?lap_id=slow:1&reference_lap_id=fast:1&points=300
```

### Response shape

```json
{
  "lap": {
    "lapId": "slow:1",
    "raceId": "slow",
    "lapNumber": 1,
    "startNs": 1763219626170019753,
    "endNs": 1763219698300019140,
    "durationNs": 72129999387
  },
  "referenceLap": {
    "lapId": "fast:1",
    "raceId": "fast",
    "lapNumber": 1,
    "startNs": 1763219835170015771,
    "endNs": 1763219899920028760,
    "durationNs": 64750012989
  },
  "signal": {
    "source": "TopicStateEstimation.gas",
    "unit": "percent",
    "normalizedFrom": "0..1 to 0..100"
  },
  "alignment": {
    "basis": "reference_path_progress",
    "progressUnit": "ratio",
    "distanceUnit": "m",
    "referencePathLengthM": 2968.851,
    "pointCount": 300,
    "quality": {
      "lapCoverageRatio": 1.0,
      "referenceCoverageRatio": 1.0,
      "lapMedianProjectionErrorM": 1.234,
      "lapP95ProjectionErrorM": 4.567
    }
  },
  "series": {
    "progressRatio": [0.0, 0.003344, 0.006689],
    "distanceM": [0.0, 9.929, 19.859],
    "lapThrottlePct": [67.9, 68.4, 69.3],
    "referenceThrottlePct": [99.0, 99.0, 99.0],
    "deltaThrottlePct": [-31.1, -30.6, -29.7],
    "lapElapsedMs": [0.0, 230.0, 460.0],
    "referenceElapsedMs": [0.0, 190.0, 380.0]
  },
  "highlights": [
    {
      "type": "late_throttle_pickup",
      "traits": ["late_throttle_pickup", "slow_throttle_ramp"],
      "startProgress": 0.53,
      "endProgress": 0.58,
      "startDistanceM": 1573.49,
      "endDistanceM": 1721.94,
      "maxDeficitPct": 18.5,
      "meanDeficitPct": 11.2,
      "onsetDelayM": 14.3,
      "fullThrottleDelayM": 21.8
    }
  ]
}
```

### Top-level blocks

#### `lap`
Describes the selected lap being evaluated.

#### `referenceLap`
Describes the lap being used as the benchmark.

#### `signal`
Explains what telemetry signal the comparison is based on.

#### `alignment`
Explains how the backend aligned the two laps.

#### `series`
Contains the actual arrays the frontend should plot.

#### `highlights`
Contains pre-computed comparison zones the frontend can use for annotations, callouts, overlays, or insight cards.

### The `series` block in detail

| Field | Meaning | How frontend should use it |
|---|---|---|
| `progressRatio` | normalized lap progress from `0.0` to `1.0` | good x-axis if the UI wants percentage-of-lap |
| `distanceM` | physical distance along the reference lap | best x-axis if the UI wants real track distance |
| `lapThrottlePct` | selected lap throttle at each aligned point | plot line 1 |
| `referenceThrottlePct` | reference lap throttle at each aligned point | plot line 2 |
| `deltaThrottlePct` | `lapThrottlePct - referenceThrottlePct` | useful for shaded difference plot or deficit band |
| `lapElapsedMs` | elapsed time within the selected lap at each aligned point | useful for tooltips |
| `referenceElapsedMs` | elapsed time within the reference lap at each aligned point | useful for tooltips |

### Recommended plotting approach
A very good frontend plot setup is:
- x-axis: `distanceM` or `progressRatio`
- y-axis: throttle percent
- line 1: `lapThrottlePct`
- line 2: `referenceThrottlePct`
- optional shaded area: `deltaThrottlePct`
- optional annotations: `highlights[]`

### Why both `distanceM` and `progressRatio` are returned
The frontend may want either:
- a real physical track-distance axis
- or a simpler normalized `0..100%` lap-progress axis

Returning both keeps the frontend flexible without extra backend calls.

### The `alignment.quality` block

| Field | Meaning |
|---|---|
| `lapCoverageRatio` | fraction of the comparison grid that the selected lap could be mapped onto |
| `referenceCoverageRatio` | same idea for the reference lap; normally `1.0` |
| `lapMedianProjectionErrorM` | median geometric mismatch between the lap trace and the reference path |
| `lapP95ProjectionErrorM` | 95th percentile mismatch |

These values are mainly for debugging and confidence. For the normal hackathon UI, they can be hidden.

### The `highlights` block
Each highlight describes a region where throttle behavior meaningfully differs.

Possible traits currently include:
- `late_throttle_pickup`
- `slow_throttle_ramp`
- `throttle_hesitation`
- `late_full_throttle`
- fallback `throttle_deficit`

These are intended to help the frontend say things like:
- “You got on throttle later here.”
- “You ramped more slowly through this exit.”
- “There is hesitation before full commitment in this region.”

### Common frontend usage patterns

#### Simplest demo call
```text
/api/engine/throttleComparison?race_id=slow&reference_race_id=fast
```

Use this if the app just wants the default `slow vs fast` comparison.

#### Explicit lap-selection flow
1. call `/api/engine/laps?race_id=slow`
2. call `/api/engine/laps?race_id=fast`
3. let the user choose laps
4. call `/api/engine/throttleComparison?lap_id=slow:1&reference_lap_id=fast:1`

### Error behavior

#### Bad param example
```text
/api/engine/throttleComparison?points=50
```

Returns `400` because `points` must be between `200` and `1200`.

#### Lap not found case
If a lap ID or race does not resolve to a detected lap, the endpoint returns `404`.

#### Alignment safety case
If a lap cannot be aligned reliably enough to the reference, the endpoint returns `400` instead of returning misleading plot data.

### Frontend usage notes
- For the hackathon demo, this is the main endpoint the engine page should use.
- If you only need one plot and no user lap picker, calling `throttleComparison` directly is enough.
- If you want a lap selector UI, use `engine/laps` first.
- `highlights` are optional for the chart itself, but very useful for insight text and callouts.

---

## 8. `GET /api/engine/gearboxAndShift/comparison`

### What it is for
Returns lap-to-lap gearbox behavior comparison aligned by track progress.

This endpoint is designed for the Engine page to answer questions like:
- where the lap shifted earlier or later than reference
- where the lap stayed in a different gear
- where gear differences correlate with speed loss/gain

### Alignment model
This endpoint does not compare by raw timestamp alone. It aligns laps by track position:
1. builds a reference path from `x_m` / `y_m`
2. projects the selected lap onto that path
3. resamples both laps on a shared distance/progress grid

That makes shift timing comparisons meaningful at equivalent places on track.

### Signal source used
- `TopicStateEstimation.gear` (normalized to integer gears)
- `TopicStateEstimation.v_mps` (context for mismatch-zone speed delta)

### Query params

| Param | Required | Type | Notes |
|---|---|---|---|
| `lap_id` | No | string | Example: `slow:1` |
| `lap_number` | No | integer | Used together with `race_id` |
| `race_id` | No | string | Defaults to `slow` if no `lap_id` is given |
| `reference_lap_id` | No | string | Example: `fast:1` |
| `reference_lap_number` | No | integer | Used together with `reference_race_id` |
| `reference_race_id` | No | string | Defaults to `fast` if no `reference_lap_id` is given |
| `points` | No | integer | Resampled point count, must be between `200` and `1200`; default `600` |

### Selection behavior
If lap IDs are omitted, backend auto-selects fastest detected lap in each race scope.

Example default call:

```text
/api/engine/gearboxAndShift/comparison?race_id=slow&reference_race_id=fast
```

Example explicit call:

```text
/api/engine/gearboxAndShift/comparison?lap_id=slow:1&reference_lap_id=fast:1&points=450
```

### Response shape

```json
{
  "lap": {
    "lapId": "slow:1",
    "raceId": "slow",
    "lapNumber": 1,
    "startNs": 1763219626170019753,
    "endNs": 1763219698300019140,
    "durationNs": 72129999387
  },
  "referenceLap": {
    "lapId": "fast:1",
    "raceId": "fast",
    "lapNumber": 1,
    "startNs": 1763219835170015771,
    "endNs": 1763219899920028760,
    "durationNs": 64750012989
  },
  "signal": {
    "source": "TopicStateEstimation.gear",
    "gearType": "integer"
  },
  "alignment": {
    "basis": "reference_path_progress",
    "progressUnit": "ratio",
    "distanceUnit": "m",
    "referencePathLengthM": 2968.851,
    "pointCount": 450,
    "quality": {
      "lapCoverageRatio": 1.0,
      "referenceCoverageRatio": 1.0,
      "lapMedianProjectionErrorM": 0.067,
      "lapP95ProjectionErrorM": 0.344
    }
  },
  "series": {
    "progressRatio": [0.0, 0.0022, 0.0045],
    "distanceM": [0.0, 6.61, 13.21],
    "lapGear": [3, 3, 3],
    "referenceGear": [3, 3, 3],
    "gearDelta": [0, 0, 0],
    "lapSpeedMps": [28.3, 28.6, 28.9],
    "referenceSpeedMps": [29.1, 29.4, 29.6]
  },
  "shiftEvents": {
    "lap": [],
    "reference": [],
    "comparisons": []
  },
  "mismatchZones": [],
  "summary": {
    "lapShiftCount": 18,
    "referenceShiftCount": 18,
    "comparedShiftCount": 18,
    "earlierShiftCount": 10,
    "laterShiftCount": 8,
    "mismatchZoneCount": 8
  }
}
```

### Main blocks and usage
- `series`: Plot gear traces by `distanceM` or `progressRatio`.
- `shiftEvents.comparisons`: Show exact earlier/later shift markers and deltas.
- `mismatchZones`: Add highlighted regions where gear selection differs for several points.
- `summary`: Populate quick insight cards.

### Status values you can expect
- Shift comparison status:
  - `earlier_than_reference`
  - `later_than_reference`
  - `near_reference`
  - `unmatched_lap_shift`
  - `unmatched_reference_shift`
- Mismatch zone status:
  - `higher_gear_than_reference`
  - `lower_gear_than_reference`

### Error behavior
- `400` for invalid params (for example `points=50` or malformed lap IDs).
- `404` when lap lookup fails for a validly formatted selection.
- `400` when alignment quality/coverage is not reliable enough for comparison.

### Frontend usage notes
- Use this endpoint for the gearbox/shift tab on Engine page.
- Use `engine/laps` first if your UI has lap pickers.
- `distanceM` is the best x-axis for track-aware tooltips and annotations.

---

## 9. `GET /api/engine/rpm/comparison`

### What it is for
Returns lap-to-lap RPM comparison aligned by track progress.

This endpoint is for engine/performance analysis where you want to compare:
- RPM build quality on exits
- RPM range usage in key acceleration zones
- where RPM lags or leads reference at the same place on track

### Alignment model
This endpoint does not compare by raw timestamp only. It aligns both laps by track progression:
1. load lap and reference-lap state estimation points
2. build reference path from `x_m` / `y_m`
3. project selected lap samples onto the same reference path
4. interpolate both RPM traces on a shared distance/progress grid
5. return the aligned series at `5Hz`

So each plotted pair of points answers: "at this same track location, what was lap RPM vs reference RPM?"

### Signal source used
- `TopicStateEstimation.rpm`

### Query params

| Param | Required | Type | Notes |
|---|---|---|---|
| `lap_id` | No | string | Example: `slow:1` |
| `lap_number` | No | integer | Used together with `race_id` |
| `race_id` | No | string | Defaults to `slow` if no `lap_id` is given |
| `reference_lap_id` | No | string | Example: `fast:1` |
| `reference_lap_number` | No | integer | Used together with `reference_race_id` |
| `reference_race_id` | No | string | Defaults to `fast` if no `reference_lap_id` is given |
| `points` | No | integer | Resampled point count, must be between `200` and `1200`; default `600` |

### Selection behavior
If lap IDs are omitted, backend auto-selects fastest detected lap in each race scope.

Default convenience call:

```text
/api/engine/rpm/comparison?race_id=slow&reference_race_id=fast
```

Explicit lap-selection call:

```text
/api/engine/rpm/comparison?lap_id=slow:1&reference_lap_id=fast:1&points=450
```

### Response shape

```json
{
  "lap": {
    "lapId": "slow:1",
    "raceId": "slow",
    "lapNumber": 1,
    "startNs": 1763219626170019753,
    "endNs": 1763219698300019140,
    "durationNs": 72129999387
  },
  "referenceLap": {
    "lapId": "fast:1",
    "raceId": "fast",
    "lapNumber": 1,
    "startNs": 1763219835170015771,
    "endNs": 1763219899920028760,
    "durationNs": 64750012989
  },
  "signal": {
    "source": "TopicStateEstimation.rpm",
    "unit": "rpm"
  },
  "alignment": {
    "basis": "reference_path_progress",
    "progressUnit": "ratio",
    "distanceUnit": "m",
    "referencePathLengthM": 2968.851,
    "pointCount": 450,
    "outputSampleHz": 5.0,
    "quality": {
      "lapCoverageRatio": 1.0,
      "referenceCoverageRatio": 1.0,
      "lapMedianProjectionErrorM": 0.083,
      "lapP95ProjectionErrorM": 0.451
    }
  },
  "series": {
    "progressRatio": [0.0, 0.0022, 0.0045],
    "distanceM": [0.0, 6.61, 13.21],
    "lapRpm": [6210.0, 6298.0, 6402.0],
    "referenceRpm": [6480.0, 6572.0, 6691.0],
    "deltaRpm": [-270.0, -274.0, -289.0],
    "lapElapsedMs": [0.0, 240.0, 480.0],
    "referenceElapsedMs": [0.0, 210.0, 420.0]
  }
}
```

### Main blocks and usage
- `series`: Plot `lapRpm` vs `referenceRpm` with x-axis as `distanceM` or `progressRatio`.
- `deltaRpm`: Use for a difference panel or shaded region to highlight deficit/surplus zones.
- `alignment.quality`: Optional debug/confidence panel.

### Error behavior
- `400` for invalid params (for example `points=50` or malformed lap IDs).
- `404` when lap lookup fails for a validly formatted selection.
- `400` when alignment quality/coverage is not reliable enough.

### Frontend usage notes
- For meaningful coaching visuals, use `distanceM` (or `progressRatio`) as x-axis, not raw time.
- Use tooltip pairs: `lapElapsedMs` and `referenceElapsedMs` to explain timing context.
- A practical chart stack is two lines (`lapRpm`, `referenceRpm`) plus a delta band (`deltaRpm`).

---

## 10. `GET /api/steering/getSteeringAngle`

### What it is for
Returns steering-angle telemetry for all races at `5Hz`.

This endpoint is intended to quickly feed frontend overlays where you compare steering behavior between sessions/races.

### Signal choice and rationale
The endpoint uses:
- `TopicStateEstimation.delta_wheel_rad`

Why this signal:
- README identifies steering angle inside fused state-estimation stream.
- It is synchronized with the same state stream used by other performance analytics.
- It is readily available for all races and straightforward for frontend plotting.

### Query params
None.

### Sampling behavior
- Backend orders by race and timestamp.
- It downsamples each race stream to `5Hz`.
- It returns both radians and degrees for frontend convenience.

### Response shape

```json
{
  "signal": {
    "source": "TopicStateEstimation.delta_wheel_rad",
    "unit": "rad",
    "outputSampleHz": 5.0
  },
  "raceCount": 2,
  "races": [
    {
      "raceId": "fast",
      "sampleCount": 372,
      "series": {
        "tsNs": [1763219835170015771, 1763219835370015790],
        "steeringAngleRad": [0.021337, 0.019204],
        "steeringAngleDeg": [1.222, 1.1]
      }
    },
    {
      "raceId": "slow",
      "sampleCount": 418,
      "series": {
        "tsNs": [1763219626170019753, 1763219626370019770],
        "steeringAngleRad": [0.018441, 0.020005],
        "steeringAngleDeg": [1.057, 1.146]
      }
    }
  ]
}
```

### Frontend usage notes
- Quick overlay mode: plot `steeringAngleDeg` for each `raceId` on separate traces.
- If you need true corner-by-corner equivalence, a future endpoint should align steering by track progress (same model as throttle/RPM), not by raw timestamp.

### Error behavior
- Standard API error behavior applies.
- Normal successful response is `200` even when race list is empty.

---

## 11. `GET /api/steering/getOverUnderSteer`

### What it is for
Returns per-race handling-balance traces at `5Hz` and classifies each sample as:
- `understeer`
- `oversteer`
- `neutral`
- `not_cornering`

### Method used
This endpoint uses a simple bicycle-model style yaw expectation:
1. smooth steering, speed, and measured yaw-rate with EMA
2. compute expected yaw-rate from steering + speed
3. compute normalized score:
   `score = (yaw_measured - yaw_expected) / (abs(yaw_expected) + 0.05)`
4. apply cornering gates (minimum speed + steering)
5. classify understeer/oversteer/neutral only when cornering

### Signal sources
- steering: `TopicStateEstimation.delta_wheel_rad`
- speed: `TopicStateEstimation.v_mps`
- measured yaw-rate: `TopicStateEstimation.yaw_vel_rad`

### Query params

| Param | Required | Type | Default | Notes |
|---|---|---|---|---|
| `wheelbase_m` | No | float | `2.8` | Vehicle wheelbase used in expected-yaw model |
| `min_speed_mps` | No | float | `8.0` | Cornering gate |
| `min_steering_rad` | No | float | `0.03` | Cornering gate |
| `score_threshold` | No | float | `0.15` | Classification threshold |
| `ema_alpha` | No | float | `0.25` | Smoothing factor in `(0, 1]` |

### Example call

```text
/api/steering/getOverUnderSteer?wheelbase_m=2.8&min_speed_mps=10&score_threshold=0.2
```

### Response shape

```json
{
  "method": {
    "name": "yaw_rate_error_bicycle_model",
    "scoreDefinition": "(yaw_measured - yaw_expected) / (abs(yaw_expected) + 0.05)"
  },
  "config": {
    "wheelbaseM": 2.8,
    "minSpeedMps": 8.0,
    "minSteeringRad": 0.03,
    "scoreThreshold": 0.15,
    "emaAlpha": 0.25,
    "outputSampleHz": 5.0
  },
  "signal": {
    "steering": "TopicStateEstimation.delta_wheel_rad",
    "speed": "TopicStateEstimation.v_mps",
    "yawRate": "TopicStateEstimation.yaw_vel_rad"
  },
  "raceCount": 2,
  "races": [
    {
      "raceId": "fast",
      "sampleCount": 372,
      "summary": {
        "corneringSampleCount": 141,
        "understeerCount": 50,
        "oversteerCount": 37,
        "neutralCount": 54
      },
      "series": {
        "tsNs": [1763219835170015771, 1763219835370015790],
        "steeringAngleRad": [0.021337, 0.019204],
        "speedMps": [31.01, 31.45],
        "yawRateMeasuredRadPs": [0.1123, 0.1072],
        "yawRateExpectedRadPs": [0.1288, 0.1197],
        "yawRateErrorRadPs": [-0.0165, -0.0125],
        "balanceScore": [-0.1088, -0.0953],
        "balanceClass": ["neutral", "neutral"],
        "isCornering": [true, true]
      }
    }
  ]
}
```

### Frontend usage notes
- Plot `balanceScore` on a centered axis and color by `balanceClass`.
- For race comparison cards, use `summary` counts or percentages.
- Treat `not_cornering` as out-of-scope for handling-balance interpretation.

---

## 12. `GET /api/steering/getSlipCoachingMetrics`

### What it is for
Returns coaching-focused grip metrics at `5Hz` using per-wheel slip angles and lateral load.

This endpoint is designed to answer practical driver-coaching questions:
- are you below the useful slip window (leaving grip on table)?
- are you over the slip window (saturating tires/sliding)?
- is the front axle or rear axle limiting first?

### Method used
1. smooth wheel slip angles, lateral acceleration, and speed with EMA
2. convert wheel slip angles from rad to deg and compute:
   - `frontSlipDeg` = average of front-left/front-right abs slip
   - `rearSlipDeg` = average of rear-left/rear-right abs slip
   - `maxSlipDeg` = max abs slip across all four tires
3. compute `lateralG = ay_mps2 / 9.81`
4. apply cornering-demand gates:
   - `speed >= min_speed_mps`
   - `abs(lateralG) >= min_lateral_g`
5. classify grip usage:
   - `below_optimal_slip`
   - `in_optimal_window`
   - `over_limit_slip`
6. classify balance hint from front-vs-rear slip delta:
   - `front_limited`
   - `rear_limited`
   - `balanced`

### Signal sources
- `TopicStateEstimation.alpha_fl_rad`
- `TopicStateEstimation.alpha_fr_rad`
- `TopicStateEstimation.alpha_rl_rad`
- `TopicStateEstimation.alpha_rr_rad`
- `TopicStateEstimation.ay_mps2`
- `TopicStateEstimation.v_mps`

### Query params

| Param | Required | Type | Default | Notes |
|---|---|---|---|---|
| `min_speed_mps` | No | float | `10.0` | Minimum speed for coaching analysis window |
| `min_lateral_g` | No | float | `0.20` | Minimum lateral load for coaching analysis window |
| `target_slip_deg` | No | float | `6.0` | Target max-slip center for grip window |
| `slip_window_deg` | No | float | `2.0` | Half-width around target slip |
| `balance_threshold_deg` | No | float | `1.0` | Slip delta threshold for front/rear-limited hints |
| `ema_alpha` | No | float | `0.25` | Smoothing factor in `(0, 1]` |

### Example call

```text
/api/steering/getSlipCoachingMetrics?target_slip_deg=6.5&slip_window_deg=1.5
```

### Response shape

```json
{
  "method": {
    "name": "slip_window_and_balance"
  },
  "config": {
    "minSpeedMps": 10.0,
    "minLateralG": 0.2,
    "targetSlipDeg": 6.0,
    "slipWindowDeg": 2.0,
    "balanceThresholdDeg": 1.0,
    "emaAlpha": 0.25,
    "outputSampleHz": 5.0
  },
  "raceCount": 2,
  "races": [
    {
      "raceId": "fast",
      "sampleCount": 372,
      "summary": {
        "analyzedSampleCount": 141,
        "belowOptimalSlipCount": 33,
        "inOptimalWindowCount": 76,
        "overLimitSlipCount": 32,
        "frontLimitedCount": 58,
        "rearLimitedCount": 27,
        "medianMaxSlipDeg": 5.84,
        "p95MaxSlipDeg": 8.77,
        "avgAbsLateralG": 1.23
      },
      "series": {
        "tsNs": [1763219835170015771, 1763219835370015790],
        "speedMps": [31.01, 31.45],
        "lateralAccelMps2": [11.72, 12.03],
        "lateralG": [1.194, 1.226],
        "frontSlipDeg": [5.21, 5.48],
        "rearSlipDeg": [4.62, 4.69],
        "maxSlipDeg": [6.09, 6.33],
        "slipBalanceDeg": [0.59, 0.79],
        "gripUsageRatio": [1.015, 1.055],
        "coachingState": ["in_optimal_window", "in_optimal_window"],
        "balanceHint": ["balanced", "balanced"],
        "isHighDemandCornering": [true, true]
      }
    }
  ]
}
```

### Frontend usage notes
- Primary coaching card: use `summary.inOptimalWindowCount / analyzedSampleCount` as consistency metric.
- Show `overLimitSlipCount` as risk metric (sliding/saturation tendency).
- Show `frontLimitedCount` vs `rearLimitedCount` to coach balance adjustments.
- For timeseries coloring, map `coachingState` to green/amber/red and `balanceHint` to front/rear cues.

---

## 13. `GET /api/breaks/pressureComparison`

### What it is for
Returns an aligned lap-to-lap brake pressure comparison payload for plotting.

This endpoint is designed for the Brakes page to answer:
- where the selected lap starts braking earlier/later than reference
- where pressure is stronger/weaker than reference
- where peak pressure timing differs
- where brake application is longer/shorter than reference

### Why this endpoint exists
Raw timestamp overlays are misleading for driving analysis because laps do not reach the same track point at the same time.

This endpoint aligns both laps by track progression so each plotted sample represents approximately the same part of the circuit.

### Signal source and units
- Source: `TopicStateEstimation.front_brake_pressure` and `TopicStateEstimation.rear_brake_pressure`
- Default mode: `combined` (mean of front + rear when both exist)
- Optional modes: `front`, `rear`
- Unit: returned as backend native pressure units (`native_pressure_units`)

### Alignment model
The backend:
1. resolves selected lap + reference lap
2. loads `x_m/y_m` path and pressure samples
3. builds reference path progression
4. projects selected-lap samples onto reference path
5. interpolates both traces on shared distance/progress grid
6. smooths pressure series (EMA)
7. derives braking zones and high-impact differences

### Query params

| Param | Required | Type | Notes |
|---|---|---|---|
| `lap_id` | No | string | Example: `slow:1` |
| `lap_number` | No | integer | Used with `race_id` |
| `race_id` | No | string | Default `slow` if no `lap_id` |
| `reference_lap_id` | No | string | Example: `fast:1` |
| `reference_lap_number` | No | integer | Used with `reference_race_id` |
| `reference_race_id` | No | string | Default `fast` if no `reference_lap_id` |
| `points` | No | integer | Resample count, range `250..2000`, default `700` |
| `pressure_mode` | No | string | `combined`, `front`, `rear` |

### Selection behavior
If explicit lap IDs are not provided, backend resolves fastest detected lap in each race scope.

### Response shape

```json
{
  "lap": {
    "lapId": "slow:1",
    "raceId": "slow",
    "lapNumber": 1,
    "startNs": 1763219626170019753,
    "endNs": 1763219698300019140,
    "durationNs": 72129999387
  },
  "referenceLap": {
    "lapId": "fast:1",
    "raceId": "fast",
    "lapNumber": 1,
    "startNs": 1763219835170015771,
    "endNs": 1763219899920028760,
    "durationNs": 64750012989
  },
  "signal": {
    "mode": "combined",
    "source": "mean(TopicStateEstimation.front_brake_pressure, TopicStateEstimation.rear_brake_pressure)",
    "unit": "native_pressure_units",
    "smoothing": {
      "method": "ema",
      "alpha": 0.2
    },
    "activeThreshold": 0.138
  },
  "alignment": {
    "basis": "reference_path_progress",
    "progressUnit": "ratio",
    "distanceUnit": "m",
    "referencePathLengthM": 2968.851,
    "pointCount": 350,
    "outputSampleHz": 5.0,
    "quality": {
      "lapCoverageRatio": 1.0,
      "referenceCoverageRatio": 1.0,
      "lapMedianProjectionErrorM": 0.93,
      "lapP95ProjectionErrorM": 4.88
    }
  },
  "series": {
    "progressRatio": [0.0, 0.003, 0.006],
    "distanceM": [0.0, 8.9, 17.8],
    "lapBrakePressure": [0.0, 0.0, 0.01],
    "referenceBrakePressure": [0.0, 0.0, 0.0],
    "deltaBrakePressure": [0.0, 0.0, 0.01],
    "lapElapsedMs": [0.0, 216.0, 432.0],
    "referenceElapsedMs": [0.0, 193.0, 385.0]
  },
  "brakingZones": [
    {
      "zoneIndex": 1,
      "startProgress": 0.214,
      "endProgress": 0.291,
      "lap": {
        "onsetDistanceM": 638.14,
        "releaseDistanceM": 862.51,
        "peakPressure": 0.81
      },
      "reference": {
        "onsetDistanceM": 651.12,
        "releaseDistanceM": 848.77,
        "peakPressure": 0.76
      },
      "differences": {
        "onsetDeltaM": -12.98,
        "releaseDeltaM": 13.74,
        "peakPressureDelta": 0.05
      },
      "traits": ["earlier_brake_onset", "longer_brake_release", "higher_peak_pressure"],
      "severity": 0.67
    }
  ],
  "highlights": [
    {
      "zoneIndex": 1,
      "type": "earlier_brake_onset",
      "startProgress": 0.214,
      "endProgress": 0.291,
      "severity": 0.67,
      "notes": "Braking behavior differs materially from reference in this zone."
    }
  ]
}
```

### `series` block usage guidance
- Plot x-axis as `distanceM` (preferred) or `progressRatio`.
- Plot y-axis lines: `lapBrakePressure` and `referenceBrakePressure`.
- Use `deltaBrakePressure` for shaded deficit/surplus band.
- Use `brakingZones` and `highlights` for overlays and coaching callouts.

### Error behavior
- `400` for invalid params (`points`, `pressure_mode`, malformed lap ID)
- `404` for unresolved lap selection
- `400` when alignment quality/coverage is insufficient

---

## 14. `GET /api/breaks/temperatureComparison`

### What it is for
Returns brake thermal behavior over the lap, including:
- full progression trace
- per-wheel thermal values
- zone-level thermal/load summaries
- hottest zones
- optional reference overlay and deltas

### Important data-source note
This backend currently uses TPMS temperature channels as the available thermal proxy:
- `TopicBadenia560TpmsFront.tpr4_temp_fl/tpr4_temp_fr`
- `TopicBadenia560TpmsRear.tpr4_temp_rl/tpr4_temp_rr`

`topic_badenia_560_brake_disk_temp` is present in README topic descriptions, but is not modeled in this codebase currently. The response explicitly states this proxy choice in `signal.source`.

### Why this endpoint exists
The Brakes page often needs both:
- detailed trace for visual trend understanding
- compact zone summaries for actionable coaching

This endpoint returns both in one payload to reduce frontend joins.

### Processing model
For each lap:
1. load state-estimation path samples and build normalized lap progression
2. load TPMS front/rear temperature samples
3. map each wheel temp sample onto lap progression via timestamp interpolation
4. interpolate all wheel series on a shared progression grid
5. build aggregate temperature series (`mean(FL,FR,RL,RR)` where available)
6. build zone summaries with average brake pressure context
7. detect hottest zones and optional reference deltas

### Query params

| Param | Required | Type | Notes |
|---|---|---|---|
| `lap_id` | No | string | Example: `slow:1` |
| `lap_number` | No | integer | Used with `race_id` |
| `race_id` | No | string | Default `slow` |
| `reference_lap_id` | No | string | Optional reference overlay |
| `reference_lap_number` | No | integer | Optional, with `reference_race_id` |
| `reference_race_id` | No | string | Optional reference source |
| `points` | No | integer | Range `200..1500`, default `500` |
| `zone_count` | No | integer | Range `8..30`, default `16` |

### Response shape

```json
{
  "lap": { "lapId": "slow:1", "raceId": "slow", "lapNumber": 1 },
  "referenceLap": { "lapId": "fast:1", "raceId": "fast", "lapNumber": 1 },
  "signal": {
    "source": "TopicBadenia560TpmsFront/Rear temperature channels (TPMS) as brake thermal proxy",
    "unit": "degC",
    "series": {
      "aggregate": "mean(FL, FR, RL, RR) where available",
      "perWheel": ["FL", "FR", "RL", "RR"]
    }
  },
  "alignment": {
    "basis": "normalized_lap_progress_from_state_path_distance",
    "pointCount": 500,
    "zoneCount": 16
  },
  "series": {
    "progressRatio": [0.0, 0.002, 0.004],
    "distanceM": [0.0, 6.0, 12.0],
    "lapTempC": [71.4, 71.5, 71.6],
    "lapPerWheelTempC": {
      "flTempC": [72.0, 72.1, 72.3],
      "frTempC": [71.0, 71.2, 71.3],
      "rlTempC": [70.6, 70.7, 70.8],
      "rrTempC": [71.9, 72.0, 72.1]
    },
    "referenceTempC": [69.8, 69.9, 70.0],
    "deltaTempC": [1.6, 1.6, 1.6],
    "lapBrakePressure": [0.0, 0.0, 0.0]
  },
  "peaks": {
    "lap": { "maxTempC": 112.8, "atProgress": 0.4381, "atDistanceM": 1301.2 },
    "reference": { "maxTempC": 108.5, "atProgress": 0.4419, "atDistanceM": 1310.6 },
    "deltaMaxTempC": 4.3
  },
  "zoneSummary": [
    {
      "zoneIndex": 1,
      "startProgress": 0.0,
      "endProgress": 0.062,
      "lap": { "meanTempC": 72.3, "peakTempC": 74.1, "avgBrakePressure": 0.02 },
      "reference": { "meanTempC": 70.8, "peakTempC": 72.7 },
      "delta": { "meanTempC": 1.5, "peakTempC": 1.4 },
      "classification": {
        "thermal": "normal",
        "brakeLoad": "low",
        "hotUnderLoad": false
      }
    }
  ],
  "hottestZones": [
    { "zoneIndex": 9, "lap": { "meanTempC": 104.8 } }
  ],
  "comparisonSummary": {
    "hotterProgressRatio": 0.71,
    "meanTempDeltaC": 2.1,
    "maxTempDeltaC": 5.7,
    "minTempDeltaC": -0.9
  }
}
```

### Frontend usage guidance
- Overview cards: use `peaks` + `comparisonSummary`.
- Heat strip / mini-map: use `zoneSummary[].classification.hotUnderLoad` and `hottestZones`.
- Detail chart: plot `lapTempC` + optional `referenceTempC`; allow wheel toggles from `lapPerWheelTempC`.

### Error behavior
- `400` for invalid ranges (`points`, `zone_count`) or poor series completeness
- `404` for unresolved lap selection

---

## 15. `GET /api/breaks/trailBrakingAnalysis`

### What it is for
Returns explicit trail-braking zone interpretation per lap with reference deltas.

This endpoint is intended to explain how braking is carried into corner entry rather than only plotting raw pressure.

### What it identifies per zone
- braking start
- braking end
- peak brake point
- release point
- whether braking extends into corner
- trail-braking length/duration
- optional reference and deltas

### Processing model
1. load lap telemetry (`x/y`, brake pressure, steering)
2. smooth pressure (EMA)
3. detect active braking windows with adaptive threshold + gap fill
4. identify peak and release points inside each window
5. infer corner entry start when steering exceeds threshold
6. compute trail segment from `max(peak, release)` to zone end
7. match lap zones to reference zones by nearest peak progress
8. return summary + optional detailed zone traces

### Query params

| Param | Required | Type | Notes |
|---|---|---|---|
| `lap_id` / `race_id` | Yes* | string | Standard lap selection rules |
| `reference_lap_id` / `reference_race_id` | Yes* | string | Standard reference selection rules |
| `lap_number` | No | integer | With `race_id` |
| `reference_lap_number` | No | integer | With `reference_race_id` |
| `pressure_mode` | No | string | `combined`, `front`, `rear` |
| `zone_id` | No | integer | If provided, returns `detailedTrace` for that zone |

### Response shape

```json
{
  "lap": { "lapId": "slow:1", "raceId": "slow" },
  "referenceLap": { "lapId": "fast:1", "raceId": "fast" },
  "signal": {
    "pressureMode": "combined",
    "corneringSignal": "delta_wheel_rad"
  },
  "method": {
    "zoneDefinition": "pressure above adaptive threshold with short-gap fill",
    "releaseDefinition": "first sustained pressure decrease after peak",
    "trailDefinition": "segment from max(peak, releasePoint) to zone end"
  },
  "zoneCount": 7,
  "zones": [
    {
      "zoneId": 1,
      "start": { "progress": 0.2141, "distanceM": 635.8 },
      "end": { "progress": 0.2914, "distanceM": 864.2 },
      "peak": { "progress": 0.2372, "distanceM": 704.4, "brakePressure": 0.81 },
      "releasePoint": { "progress": 0.2615, "distanceM": 776.5, "brakePressure": 0.26 },
      "corner": {
        "cornerStartProgress": 0.2522,
        "extendsIntoCorner": true
      },
      "trailBraking": {
        "lengthM": 87.7,
        "durationS": 1.42,
        "intoCornerLengthM": 74.6,
        "intoCornerDurationS": 1.19
      },
      "reference": { "zoneId": 2, "trailBraking": { "lengthM": 64.1 } },
      "delta": { "trailLengthM": 23.6, "peakProgress": -0.0061 }
    }
  ],
  "detailedTrace": {
    "zoneId": 1,
    "lap": {
      "zoneProgress": [0.0, 0.008, 0.016],
      "brakePressure": [0.81, 0.79, 0.78],
      "steeringRad": [0.02, 0.025, 0.03]
    },
    "reference": {
      "zoneProgress": [0.0, 0.008, 0.016],
      "brakePressure": [0.77, 0.75, 0.73],
      "steeringRad": [0.019, 0.022, 0.026]
    }
  }
}
```

### Frontend usage guidance
- Summary panel: render `zones` in table/cards with `trailBraking` metrics.
- Track overlays: use `start/end/peak/releasePoint` positions.
- Zone inspector: use `detailedTrace` when user clicks a zone.

### Error behavior
- `400` invalid params / no zones detected due to insufficient signal quality
- `404` unresolved lap or invalid `zone_id`

---

## 16. `GET /api/breaks/releaseThrottleTransition`

### What it is for
Returns a driving-transition dataset for each braking zone that links:
- brake release behavior
- apex timing (min speed)
- throttle pickup timing

This endpoint supports a graph that tells the corner-entry to corner-exit story, not just separate brake and throttle lines.

### Core interpretation it provides
Per zone, backend computes:
- brake start / end
- peak brake
- brake release
- apex (minimum speed after peak in local window)
- throttle application (first sustained throttle-on)
- transition metrics: gap/overlap, delay vs apex, smoothness, classification

Possible transition classifications:
- `smooth`
- `hesitant`
- `delayed`
- `abrupt`
- `overlap`

### Processing model
1. load lap telemetry (`x/y`, brake pressure, gas, speed, steering)
2. normalize throttle to percent (`gas 0..1` -> `0..100`)
3. smooth brake pressure with EMA
4. detect braking zones via adaptive threshold
5. derive release/apex/throttle-on events
6. compute transition metrics
7. match zones to reference by peak progress
8. build local-detail trace around selected zone with apex-centered local axis

### Query params

| Param | Required | Type | Notes |
|---|---|---|---|
| `lap_id` / `race_id` | Yes* | string | Standard lap selection |
| `reference_lap_id` / `reference_race_id` | Yes* | string | Standard reference selection |
| `lap_number` | No | integer | With `race_id` |
| `reference_lap_number` | No | integer | With `reference_race_id` |
| `pressure_mode` | No | string | `combined`, `front`, `rear` |
| `zone_id` | No | integer | Which zone to return in `selectedZoneDetail`; defaults to first zone |
| `trace_points` | No | integer | Range `61..301`, default `141` |

### Response shape

```json
{
  "lap": { "lapId": "slow:1", "raceId": "slow" },
  "referenceLap": { "lapId": "fast:1", "raceId": "fast" },
  "signal": {
    "brakePressureMode": "combined",
    "throttleSource": "TopicStateEstimation.gas normalized to percent"
  },
  "method": {
    "releaseDefinition": "first point after peak where pressure falls near release threshold",
    "apexDefinition": "minimum speed point after peak within local lookahead",
    "throttleApplicationDefinition": "first sustained throttle >= threshold",
    "alignmentForDetail": "local normalized transition axis centered on apex",
    "throttleOnThresholdPct": 10.0
  },
  "zoneCount": 7,
  "zones": [
    {
      "zoneId": 1,
      "start": { "progress": 0.2141, "distanceM": 635.8 },
      "end": { "progress": 0.2914, "distanceM": 864.2 },
      "peakBrake": { "progress": 0.2372, "brakePressure": 0.81 },
      "brakeRelease": { "progress": 0.2621, "distanceM": 778.2 },
      "apex": { "progress": 0.2748, "distanceM": 815.9, "speedMps": 22.4 },
      "throttleApplication": { "progress": 0.2812, "distanceM": 834.9, "throttlePct": 12.7 },
      "transition": {
        "brakeToThrottleGapS": 0.31,
        "brakeToThrottleGapM": 56.7,
        "overlapS": 0.0,
        "throttleDelayVsApexS": 0.12,
        "throttleDelayVsApexM": 19.0,
        "smoothnessScore": 73.4,
        "classification": "hesitant"
      },
      "reference": {
        "zoneId": 2,
        "transition": {
          "brakeToThrottleGapS": 0.16,
          "throttleDelayVsApexS": 0.03,
          "smoothnessScore": 84.1
        }
      },
      "delta": {
        "gapS": 0.15,
        "throttleDelayVsApexS": 0.09,
        "smoothnessScore": -10.7
      }
    }
  ],
  "selectedZoneDetail": {
    "zoneId": 1,
    "lap": {
      "localProgress": [-1.0, -0.986, -0.972],
      "absoluteProgress": [0.2482, 0.2485, 0.2488],
      "brakePressure": [0.63, 0.62, 0.61],
      "throttlePct": [0.0, 0.0, 0.2],
      "markers": {
        "brakeRelease": -0.23,
        "apex": 0.0,
        "throttleApplication": 0.19
      },
      "window": {
        "startProgress": 0.2482,
        "apexProgress": 0.2748,
        "endProgress": 0.3051
      }
    },
    "reference": {
      "localProgress": [-1.0, -0.986, -0.972],
      "absoluteProgress": [0.2521, 0.2524, 0.2527],
      "brakePressure": [0.56, 0.55, 0.54],
      "throttlePct": [0.0, 0.0, 0.0],
      "markers": {
        "brakeRelease": -0.11,
        "apex": 0.0,
        "throttleApplication": 0.06
      }
    }
  }
}
```

### How to plot this endpoint effectively
- Use `zones` for zone selector and summary table.
- For selected zone graph:
  - x-axis: `selectedZoneDetail.lap.localProgress` (`-1` = before apex, `0` = apex, `+1` = after apex)
  - y1: lap/reference brake traces
  - y2: lap/reference throttle traces
  - markers: `brakeRelease`, `apex`, `throttleApplication`

This gives an intuitive "release -> apex -> throttle" story per corner.

### Error behavior
- `400` invalid params (`pressure_mode`, `trace_points`, malformed IDs)
- `404` unresolved lap or requested `zone_id` not found
- `400` if no reliable braking zones are detected

---

## Frontend Integration Recommendations

### Good overview layout
A strong overview page could map the endpoints like this:
- Lap summary: `/api/getLapTime`
- Section time loss: `/api/timeLostPerSection`
- Top speed block: `/api/topSpeed`
- Braking card: `/api/brakingEfficiency`
- Grip card: `/api/gripUtilization`
- Engine throttle plot: `/api/engine/throttleComparison`
- Engine RPM plot: `/api/engine/rpm/comparison`
- Engine gearbox/shift plot: `/api/engine/gearboxAndShift/comparison`
- Steering angle overlays: `/api/steering/getSteeringAngle`
- Steering over/understeer model: `/api/steering/getOverUnderSteer`
- Slip coaching metrics: `/api/steering/getSlipCoachingMetrics`

### Suggested fetch pattern
These endpoints are analytics-style in the current demo setup. A normal page-load fetch is enough; they do not need live polling.

### Suggested frontend formatting
- convert nanoseconds to seconds when showing user-facing times
- convert top speed from `mps` to `km/h` if needed
- show scores rounded to 0 or 1 decimal place
- for the throttle plot, keep throttle in percent and use one consistent axis from `0` to `100`
- for RPM comparison, use `distanceM` x-axis and plot `lapRpm` vs `referenceRpm` together
- for steering quick overlays, use `steeringAngleDeg` to avoid frontend conversion

### Important caveats for frontend
- Most older analytics endpoints still assume `slow` vs `fast` demo comparison.
- `topSpeed` is the only older endpoint that naturally spans all races without that assumption.
- The engine endpoints are the cleanest place to build lap-to-lap plot UX.
- If the lap detector ever returns `lapCount = 0`, the frontend should show a graceful “no comparable lap found” message instead of an empty chart.
