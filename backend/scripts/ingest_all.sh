#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

FAST_MCAP="${FAST_MCAP:-$ROOT_DIR/hackathon_fast_laps.mcap}"
SLOW_MCAP="${SLOW_MCAP:-$ROOT_DIR/hackathon_good_lap.mcap}"
PROGRESS_EVERY="${PROGRESS_EVERY:-10000}"

log() {
  echo "[ingest] $*"
}

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "[ingest] ERROR: missing file: $path" >&2
    exit 1
  fi
}

log "Using workspace: $ROOT_DIR"
require_file "$ROOT_DIR/manage.py"
require_file "$FAST_MCAP"
require_file "$SLOW_MCAP"

log "Sourcing ROS environment"
if [[ -f /opt/ros/humble/setup.bash ]]; then
  set +u
  # shellcheck disable=SC1091
  source /opt/ros/humble/setup.bash
  set -u
else
  echo "[ingest] ERROR: /opt/ros/humble/setup.bash not found" >&2
  exit 1
fi

log "Checking custom ROS message modules"
if ! python - <<'PY'
import sd_can_msgs
import sd_localization_msgs
print("ok")
PY
then
  log "Custom message modules not importable; building sd_msgs packages"
  python -m pip install -q "empy==3.3.4" catkin_pkg
  colcon build --base-paths sd_msgs --packages-select sd_can_msgs sd_localization_msgs sd_map_msgs vectornav_msgs
fi

if [[ -f "$ROOT_DIR/install/setup.bash" ]]; then
  log "Sourcing workspace overlay"
  set +u
  # shellcheck disable=SC1091
  source "$ROOT_DIR/install/setup.bash"
  set -u
fi

log "Running Django checks and migrations"
python manage.py check
python manage.py migrate

log "Ingesting FAST race: $FAST_MCAP"
python manage.py ingest_mcap --mcap "$FAST_MCAP" --race-id fast --progress-every "$PROGRESS_EVERY"

log "Ingesting SLOW race: $SLOW_MCAP"
python manage.py ingest_mcap --mcap "$SLOW_MCAP" --race-id slow --progress-every "$PROGRESS_EVERY"

log "Populating camera blobs for SLOW race images"
python manage.py populate_good_lap_camera_blob_table \
  --mcap "$SLOW_MCAP" \
  --race-id hackathon_good_lap \
  --telemetry-race-id slow \
  --progress-every 200 \
  --cleanup-cache

log "Populating camera blobs for FAST race images"
python manage.py populate_good_lap_camera_blob_table \
  --mcap "$FAST_MCAP" \
  --race-id hackathon_fast_laps \
  --telemetry-race-id fast \
  --progress-every 200 \
  --cleanup-cache

log "Final table counts"
python manage.py shell -c "from telemetry.models import TelemetryIdentity, TopicStateEstimation, TopicTfTransform, CameraFrameSQLiteBlob; print('identity=',TelemetryIdentity.objects.count(),'state_est=',TopicStateEstimation.objects.count(),'tf=',TopicTfTransform.objects.count(),'camera_blob=',CameraFrameSQLiteBlob.objects.count())"

log "Done"
