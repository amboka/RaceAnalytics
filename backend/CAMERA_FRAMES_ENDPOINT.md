# Camera Frames Endpoint Documentation

## Overview

The camera frames endpoint serves a sequence of onboard camera images starting from a given lap-relative timestamp. This enables the frontend to display a "flipbook" of driving mistakes.

## Endpoint

```
GET /api/camera/frames
```

## Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `race_id` | string | Yes | Session/race identifier (e.g., `"r12"`) |
| `camera` | int | Yes | Camera index: `0` = front-left, `1` = rear |
| `start_ts` | string | Yes | Lap-relative timestamp in `M:SS.d` format (e.g., `"0:08.4"` = 8.4 seconds) |
| `duration` | int | No | Seconds of footage to return (default: `10`) |

### Timestamp Format

Timestamps use the `M:SS.d` format:
- `M` = minutes (1-2 digits)
- `SS` = seconds (2 digits)
- `d` = tenths of a second (1 digit)

**Examples:**
- `"0:08.4"` → 8.4 seconds
- `"1:23.5"` → 83.5 seconds
- `"2:05.0"` → 125.0 seconds

## Response Format

### Success (200 OK)

```json
{
  "raceId": "r12",
  "camera": 0,
  "fps": 5,
  "frameCount": 50,
  "frames": [
    "http://localhost:8000/media/frames/r12/cam0/frame_0042.jpg",
    "http://localhost:8000/media/frames/r12/cam0/frame_0043.jpg",
    "..."
  ]
}
```

### Field Details

- **`raceId`** (string): The race ID from the request
- **`camera`** (int): The camera index (0 or 1)
- **`fps`** (int): Actual capture rate for this camera (5 or 10)
- **`frameCount`** (int): Number of frames returned (equals `frames.length`)
- **`frames`** (string[]): Ordered array of absolute URLs to JPEG/PNG images

**Frontend Usage:**
```javascript
const interval = 1000 / response.fps; // milliseconds between frames
let currentFrameIndex = 0;

setInterval(() => {
  imageElement.src = response.frames[currentFrameIndex];
  currentFrameIndex = (currentFrameIndex + 1) % response.frameCount;
}, interval);
```

### Empty Result (200 OK)

When no frames exist for a race/camera combination:

```json
{
  "raceId": "r12",
  "camera": 0,
  "fps": 5,
  "frameCount": 0,
  "frames": []
}
```

## Error Responses

### Missing Required Parameter (400 Bad Request)

```json
{
  "error": "Missing required parameter: race_id"
}
```

### Invalid Timestamp Format (400 Bad Request)

```json
{
  "error": "Invalid timestamp format 'invalid'. Expected 'M:SS.d'"
}
```

### Invalid Camera (400 Bad Request)

```json
{
  "error": "Camera must be 0 (front-left) or 1 (rear)"
}
```

### Invalid Duration (400 Bad Request)

```json
{
  "error": "Duration must be greater than 0"
}
```

### Server Error (500 Internal Server Error)

```json
{
  "error": "Unable to load camera frames.",
  "details": "..."
}
```

## Implementation Details

### Database Model

The `CameraFrame` model stores metadata for each frame:

```python
class CameraFrame(models.Model):
    race_id = models.TextField()              # Session identifier
    camera = models.IntegerField()            # 0 or 1
    frame_number = models.IntegerField()      # Sequential index
    timestamp_seconds = models.FloatField()   # Lap-relative time in seconds
    fps = models.IntegerField()               # 5 or 10
    file_path = models.TextField()            # Relative path to image
    created_at = models.DateTimeField(auto_now_add=True)
```

**Constraints:**
- Unique: `(race_id, camera, frame_number)`
- Indexes: `(race_id, camera)`, `(race_id, camera, timestamp_seconds)`

### File Storage

Images are stored in a structure like:

```
media/
  frames/
    r12/
      cam0/
        frame_0000.jpg
        frame_0001.jpg
        ...
      cam1/
        frame_0000.jpg
        frame_0001.jpg
        ...
    r13/
      cam0/
        ...
```

The `file_path` field stores relative paths (e.g., `"frames/r12/cam0/frame_0042.jpg"`).

### Frame Calculation

Given a `start_ts` and `duration`:

1. Parse timestamp: `"0:08.4"` → `8.4` seconds
2. Calculate starting frame: `start_frame = floor(8.4 * 5) = 42`
3. Calculate frame count: `frames = 10 * 5 = 50`
4. Query frames `42` to `91` for the given `race_id` and `camera`
5. Return ordered URLs

### CORS Configuration

The endpoint respects the Django CORS configuration. For local development, CORS is enabled for all origins via environment variable `DJANGO_CORS_ALLOW_ALL`.

## Example Requests

### Get first 10 seconds of a mistake at 8.4 seconds (front camera)

```bash
curl "http://localhost:8000/api/camera/frames?race_id=r12&camera=0&start_ts=0:08.4&duration=10"
```

### Get 5 seconds of rear camera footage

```bash
curl "http://localhost:8000/api/camera/frames?race_id=r12&camera=1&start_ts=1:23.5&duration=5"
```

## Database Setup

### Create Migration

```bash
python manage.py makemigrations telemetry
```

### Apply Migration

```bash
python manage.py migrate
```

### Populate Sample Data

```bash
python manage.py shell << 'EOF'
from telemetry.models import CameraFrame

for frame_num in range(600):  # 2 minutes of video at 5 FPS
    ts_seconds = frame_num / 5.0
    CameraFrame.objects.create(
        race_id="r12",
        camera=0,
        frame_number=frame_num,
        timestamp_seconds=ts_seconds,
        fps=5,
        file_path=f"frames/r12/cam0/frame_{frame_num:04d}.jpg"
    )
EOF
```

## Frontend Integration Example

### React Component

```jsx
import React, { useState, useEffect } from 'react';

export function CameraFlipbook({ raceId, camera, startTs, duration = 10 }) {
  const [frames, setFrames] = useState([]);
  const [fps, setFps] = useState(5);
  const [currentFrame, setCurrentFrame] = useState(0);

  useEffect(() => {
    // Fetch frames from endpoint
    fetch(`/api/camera/frames?race_id=${raceId}&camera=${camera}&start_ts=${startTs}&duration=${duration}`)
      .then(r => r.json())
      .then(data => {
        setFrames(data.frames);
        setFps(data.fps);
      });
  }, [raceId, camera, startTs, duration]);

  // Auto-play flipbook
  useEffect(() => {
    if (frames.length === 0) return;
    
    const interval = setInterval(() => {
      setCurrentFrame(prev => (prev + 1) % frames.length);
    }, 1000 / fps);

    return () => clearInterval(interval);
  }, [frames, fps]);

  if (frames.length === 0) {
    return <div>No frames available</div>;
  }

  return (
    <div className="flipbook">
      <img src={frames[currentFrame]} alt={`Frame ${currentFrame}`} />
      <p>{currentFrame + 1} / {frames.length}</p>
    </div>
  );
}
```

## Notes

- The frontend doesn't need to know the video format, FPS, or frame numbering — the server provides everything
- Frame URLs are absolute and can be cached or proxied by the frontend
- If `start_ts` is beyond available frames, the endpoint returns whatever frames are available (partial or empty)
- The system is designed to handle both 5 Hz and 10 Hz camera capture rates
- CORS headers allow cross-origin requests from the frontend for local development
