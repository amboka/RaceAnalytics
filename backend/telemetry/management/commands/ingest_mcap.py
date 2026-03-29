from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from telemetry.ingestion import McapTelemetryImporter


class Command(BaseCommand):
    help = "Ingest one MCAP file into telemetry tables."

    def add_arguments(self, parser):
        parser.add_argument("--mcap", required=True, help="Path to .mcap file")
        parser.add_argument(
            "--race-id",
            required=True,
            choices=["fast", "slow"],
            help='Race label for all ingested rows: "fast" or "slow"',
        )
        parser.add_argument(
            "--progress-every",
            type=int,
            default=5000,
            help="Print progress every N seen messages (default: 5000)",
        )

    def handle(self, *args, **options):
        mcap_path = Path(options["mcap"]).expanduser().resolve()
        race_id = options["race_id"]
        progress_every = int(options["progress_every"])

        if not mcap_path.exists():
            raise CommandError(f"MCAP file not found: {mcap_path}")
        if mcap_path.suffix.lower() != ".mcap":
            raise CommandError(f"Expected a .mcap file, got: {mcap_path.name}")

        importer = McapTelemetryImporter(
            race_id=race_id,
            mcap_path=str(mcap_path),
            stdout=self.stdout,
            stderr=self.stderr,
            progress_every=progress_every,
        )

        try:
            stats = importer.run()
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        if stats.total_errors > 0:
            self.stdout.write(
                self.style.WARNING(
                    "Ingestion finished with errors: "
                    f"seen={stats.total_seen}, saved={stats.total_saved}, "
                    f"skipped={stats.total_skipped}, errors={stats.total_errors}"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Ingestion finished successfully: "
                    f"seen={stats.total_seen}, saved={stats.total_saved}, "
                    f"skipped={stats.total_skipped}, errors={stats.total_errors}"
                )
            )
