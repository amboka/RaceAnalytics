# Spatial Camera Frames Endpoint

## Overview

Get camera frames between two XYZ positions on the track, instead of by timestamp. Perfect for location-based video analysis (e.g., "show me video from Turn 3 entry to Turn 3 exit").

## Endpoint

```
GET /api/camera/frames-by-location
```

## Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `race_id` | string | Yes | Session identifier (e.g., "0", "slow", "fast") |
| `camera` | int | Yes | Camera: `0` = front-left, `1` = rear |
| `start_x` | float | Yes | Starting X position (meters) |
| `start_y` | float | Yes | Starting Y position (meters) |
| `start_z` | float | No | Starting Z position (default: 0) |
| `end_x` | float | Yes | Ending X position (meters) |
| `end_y` | float | Yes | Ending Y position (meters) |
| `end_z` | float | No | Ending Z position (default: 0) |
| `position_tolerance` | float | No | Max distance to match positions (default: 10.0 meters) |

## Response Format

### Success (200 OK)

```json
{
  "raceId": "slow",
  "camera": 0,
  "fps": 5,
  "frameCount": 75,
  "frames": [
    "http://localhost:8000/media/frames/hackathon_good_lap/cam0/frame_0125.jpg",
    "http://localhost:8000/media/frames/hackathon_good_lap/cam0/frame_0126.jpg",
    "..."
  ],
  "startPosition": {
    "x": -17.05,
    "y": 1.88,
    "z": 0.0
  },
  "endPosition": {
    "x": 197.59,
    "y": 313.07,
    "z": 0.0
  },
  "matchedStartDistance": 0.29,
  "matchedEndDistance": 6.57
}
```

### Field Details

- **`raceId`**: The race ID from the request
- **`camera`**: Camera index (0 or 1)
- **`fps`**: Capture rate (5 or 10 Hz)
- **`frameCount`**: Number of frames returned
- **`frames`**: Array of image URLs in chronological order
- **`startPosition`**: Actual matched track position (nearest to requested start)
- **`endPosition`**: Actual matched track position (nearest to requested end)
- **`matchedStartDistance`**: Distance error between requested and actual start position (meters)
- **`matchedEndDistance`**: Distance error between requested and actual end position (meters)

## Error Responses

### Missing Required Parameter (400 Bad Request)
```json
{
  "error": "Missing required parameter: race_id"
}
```

### Invalid Position (400 Bad Request)
```json
{
  "error": "Invalid start position. start_x, start_y, start_z must be numbers."
}
```

### No Position Found Within Tolerance (400 Bad Request)
```json
{
  "error": "No track position found within 10.0m of start position (-17.05, 1.88, 0)"
}
```

### Server Error (500 Internal Server Error)
```json
{
  "error": "Unable to load camera frames by location.",
  "details": "..."
}
```

## How It Works

### Spatial Lookup Algorithm

1. **Parse XYZ positions**: Extract start and end coordinates from request
2. **Query telemetry**: Get all TopicStateEstimation records for the race
3. **Find nearest start**: Compute Euclidean distance to every telemetry point, find minimum
   - If `distance > position_tolerance`: return 400 error
4. **Find nearest end**: Repeat for end position
5. **Get time range**: Extract timestamps (ts_ns) from the matched telemetry records
6. **Query camera frames**: Find all CameraFrame records between start_ts_ns and end_ts_ns
7. **Build URLs**: Generate absolute URLs for all frames in range

### Distance Calculation

```
distance = √((x_state - x_target)² + (y_state - y_target)² + (z_state - z_target)²)
```

All positions in meters. Z defaults to 0 for 2D track queries.

## Example Usage

### Get video from Turn 3 entry to exit

```bash
curl "http://localhost:8000/api/camera/frames-by-location?race_id=slow&camera=0&start_x=-17.05&start_y=1.88&end_x=197.59&end_y=313.07&position_tolerance=10"
```

### Get rear camera view of same section

```bash
curl "http://localhost:8000/api/camera/frames-by-location?race_id=slow&camera=1&start_x=-17.05&start_y=1.88&end_x=197.59&end_y=313.07"
```

### Use display race ID aliases

```bash
# Race ID "0" maps to "slow" telemetry and "hackathon_good_lap" video
curl "http://localhost:8000/api/camera/frames-by-location?race_id=0&camera=0&start_x=-17.05&start_y=1.88&end_x=197.59&end_y=313.07"
```

## Race ID Mapping

The endpoint supports multiple race_id formats:

| Display ID | Telemetry Race | MCAP File | Camera Storage |
|-----------|--------|-----------|-----------|
| `0` | `slow` | hackathon_good_lap.mcap | hackathon_good_lap |
| `1` | `fast` | hackathon_fast_laps.mcap | hackathon_fast_laps |
| `slow` | `slow` | hackathon_good_lap.mcap | hackathon_good_lap |
| `fast` | `fast` | hackathon_fast_laps.mcap | hackathon_fast_laps |

## Frontend Integration

### React Component Example

```jsx
import React, { useState, useEffect } from 'react';

export function SpatialCameraView({ raceId, camera, startX, startY, endX, endY }) {
  const [frames, setFrames] = useState([]);
  const [fps, setFps] = useState(5);
  const [matchedStart, setMatchedStart] = useState(null);
  const [matchedEnd, setMatchedEnd] = useState(null);
  const [currentFrame, setCurrentFrame] = useState(0);

  useEffect(() => {
    // Fetch frames by spatial location
    const params = new URLSearchParams({
      race_id: raceId,
      camera: camera,
      start_x: startX,
      start_y: startY,
      end_x: endX,
      end_y: endY,
      position_tolerance: 20
    });

    fetch(`/api/camera/frames-by-location?${params}`)
      .then(r => r.json())
      .then(data => {
        setFrames(data.frames);
        setFps(data.fps);
        setMatchedStart(data.startPosition);
        setMatchedEnd(data.endPosition);
      });
  }, [raceId, camera, startX, startY, endX, endY]);

  // Auto-play flipbook
  useEffect(() => {
    if (frames.length === 0) return;
    
    const interval = setInterval(() => {
      setCurrentFrame(prev => (prev + 1) % frames.length);
    }, 1000 / fps);

    return () => clearInterval(interval);
  }, [frames, fps]);

  if (frames.length === 0) {
    return <div>No frames in spatial range</div>;
  }

  return (
    <div>
      <img src={frames[currentFrame]} alt="Camera view" />
      <p>Frame {currentFrame + 1} / {frames.length}</p>
      <p>
        From {matchedStart?.x.toFixed(1)}, {matchedStart?.y.toFixed(1)}
        to {matchedEnd?.x.toFixed(1)}, {matchedEnd?.y.toFixed(1)}
      </p>
    </div>
  );
}
```

## Use Cases

1. **Corner Analysis**: "Show me cameras during Turn 3 entry, apex, and exit"
   - Start: entry point (x, y)
   - End: exit point (x, y)

2. **Braking Point Comparison**: "Compare two drivers' braking zones at the same location"
   - Same spatial range for different races

3. **Incident Analysis**: "Show all cameras as the car approaches the crash site"
   - Start: position before incident
   - End: incident location

4. **Overtake Rewind**: "Show overtake corner from both cars' perspectives"
   - Get frames for lead car and following car at same spatial region

## Notes

- Position tolerance defaults to 10m; increase for coarse matching, decrease for precision
- Frames are returned in chronological order (earliest first)
- Both XYZ coordinates must be within tolerance of actual track points
- If no telemetry data exists for the race_id, returns empty frames array (200 OK)
- Camera frames are extracted on-demand and cached on first request
- Z coordinate typically 0 for road surfaces; useful for 3D track sections (elevation changes)

## Performance

- **First request per race**: ~30-120 seconds (extracts frames from MCAP)
- **Subsequent requests**: <100ms (database lookup only)
- Position matching: ~1ms (Euclidean distance calculation)
- Frame URL building: ~10ms for typical 100-frame requests
