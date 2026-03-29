from __future__ import annotations

from bisect import bisect_left
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from telemetry.camera_ingestion import McapCameraImageExtractor
from telemetry.models import CameraFrame, CameraFrameSQLiteBlob, TopicStateEstimation


RACE_ID = "hackathon_good_lap"
TELEMETRY_RACE_ID = "slow"
DEFAULT_MCAP = "/workspace/hackathon_good_lap.mcap"


class Command(BaseCommand):
    help = (
        "Create/fill camera_frame_sqlite_blob with all images from both cameras "
        "for a given race_id, including timestamp and nearest XYZ."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--mcap",
            default=DEFAULT_MCAP,
            help="Path to hackathon_good_lap.mcap (default: /workspace/hackathon_good_lap.mcap)",
        )
        parser.add_argument(
            "--race-id",
            default=RACE_ID,
            help="Camera race_id to populate in blob table (default: hackathon_good_lap)",
        )
        parser.add_argument(
            "--telemetry-race-id",
            default=TELEMETRY_RACE_ID,
            help="Telemetry race_id used for XYZ lookup (default: slow)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Bulk insert batch size for blob rows (default: 100)",
        )
        parser.add_argument(
            "--progress-every",
            type=int,
            default=200,
            help="Print progress every N processed frames (default: 200)",
        )
        parser.add_argument(
            "--cleanup-cache",
            action="store_true",
            help="Delete media/frames/<race-id> after blob population",
        )

    def handle(self, *args, **options):
        mcap_path = Path(options["mcap"]).expanduser().resolve()
        race_id = str(options["race_id"]).strip()
        telemetry_race_id = str(options["telemetry_race_id"]).strip()
        batch_size = int(options["batch_size"])
        progress_every = int(options["progress_every"])
        cleanup_cache = bool(options["cleanup_cache"])

        if not race_id:
            raise CommandError("--race-id cannot be empty")
        if not telemetry_race_id:
            raise CommandError("--telemetry-race-id cannot be empty")

        if batch_size <= 0:
            raise CommandError("--batch-size must be greater than 0")
        if progress_every <= 0:
            raise CommandError("--progress-every must be greater than 0")
        if not mcap_path.exists():
            raise CommandError(f"MCAP file not found: {mcap_path}")

        self._ensure_camera_frames_exist(mcap_path, race_id)

        frames = list(
            CameraFrame.objects.filter(race_id=race_id, camera__in=[0, 1])
            .order_by("camera", "frame_number")
            .only("race_id", "camera", "frame_number", "timestamp_seconds", "file_path")
        )
        if not frames:
            raise CommandError(f"No camera frames found for race_id='{race_id}'")

        states = list(
            TopicStateEstimation.objects.filter(
                record__race_id=telemetry_race_id,
                x_m__isnull=False,
                y_m__isnull=False,
                z_m__isnull=False,
            )
            .order_by("record__ts_ns")
            .values_list("record__ts_ns", "x_m", "y_m", "z_m")
        )
        if not states:
            raise CommandError(
                f"No telemetry positions found for race_id='{telemetry_race_id}'"
            )

        state_ts = [row[0] for row in states]

        with transaction.atomic():
            CameraFrameSQLiteBlob.objects.filter(race_id=race_id).delete()

            pending = []
            saved = 0
            errors = 0

            for index, frame in enumerate(frames, start=1):
                abs_ts_ns = int(round(frame.timestamp_seconds * 1_000_000_000))
                nearest = _nearest_state(abs_ts_ns, state_ts, states)

                image_file = Path(settings.MEDIA_ROOT) / frame.file_path
                try:
                    image_blob = image_file.read_bytes()
                except OSError as exc:
                    errors += 1
                    self.stderr.write(
                        f"ERROR: unable to read image for camera={frame.camera}, "
                        f"frame={frame.frame_number}: {exc}"
                    )
                    continue

                pending.append(
                    CameraFrameSQLiteBlob(
                        race_id=frame.race_id,
                        camera=frame.camera,
                        frame_number=frame.frame_number,
                        timestamp_seconds=frame.timestamp_seconds,
                        timestamp_ns=abs_ts_ns,
                        x_m=nearest[1],
                        y_m=nearest[2],
                        z_m=nearest[3],
                        telemetry_race_id=telemetry_race_id,
                        telemetry_ts_ns=nearest[0],
                        file_path=frame.file_path,
                        image_format="jpg",
                        image_size_bytes=len(image_blob),
                        image_blob=image_blob,
                    )
                )

                if len(pending) >= batch_size:
                    CameraFrameSQLiteBlob.objects.bulk_create(pending, batch_size=batch_size)
                    saved += len(pending)
                    pending.clear()

                if index % progress_every == 0:
                    self.stdout.write(
                        f"Processed {index}/{len(frames)} frames (saved={saved}, errors={errors})"
                    )

            if pending:
                CameraFrameSQLiteBlob.objects.bulk_create(pending, batch_size=batch_size)
                saved += len(pending)

        self.stdout.write(
            self.style.SUCCESS(
                "camera_frame_sqlite_blob populated successfully: "
                f"race_id={race_id} frames_seen={len(frames)} saved={saved} errors={errors}"
            )
        )

        if cleanup_cache:
            cache_dir = Path(settings.MEDIA_ROOT) / "frames" / race_id
            if cache_dir.exists():
                for p in sorted(cache_dir.rglob("*"), reverse=True):
                    if p.is_file():
                        p.unlink()
                    elif p.is_dir():
                        p.rmdir()
                cache_dir.rmdir()
                self.stdout.write(f"Removed cache directory: {cache_dir}")

    def _ensure_camera_frames_exist(self, mcap_path: Path, race_id: str) -> None:
        existing = CameraFrame.objects.filter(race_id=race_id, camera__in=[0, 1]).count()
        if existing > 0:
            self.stdout.write(
                f"Using existing CameraFrame rows for race '{race_id}' (count={existing})"
            )
            return

        self.stdout.write(
            f"No CameraFrame rows found for '{race_id}'. Extracting from {mcap_path}..."
        )
        extractor = McapCameraImageExtractor(
            mcap_path=str(mcap_path),
            race_id=race_id,
            stdout=self.stdout,
            stderr=self.stderr,
        )
        stats = extractor.run()
        self.stdout.write(
            f"Extraction complete: messages={stats.total_messages} "
            f"saved={stats.total_saved} errors={stats.total_errors}"
        )


def _nearest_state(target_ts_ns: int, state_ts: list[int], states: list[tuple[int, float, float, float]]):
    idx = bisect_left(state_ts, target_ts_ns)
    if idx <= 0:
        return states[0]
    if idx >= len(states):
        return states[-1]

    prev_state = states[idx - 1]
    next_state = states[idx]

    if abs(prev_state[0] - target_ts_ns) <= abs(next_state[0] - target_ts_ns):
        return prev_state
    return next_state
