from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from django.db import IntegrityError, transaction

from .models import TelemetryIdentity
from .topic_registry import TOPIC_REGISTRY, TopicSpec


@dataclass
class ImportStats:
    race_id: str
    mcap_path: str
    total_seen: int = 0
    total_saved: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    rows_written: int = 0
    skipped_by_topic: Dict[str, int] = field(default_factory=dict)
    errors_by_topic: Dict[str, int] = field(default_factory=dict)


class McapTelemetryImporter:
    """Simple registry-driven MCAP importer for telemetry tables."""

    def __init__(self, race_id: str, mcap_path: str, stdout, stderr, progress_every: int = 5000):
        self.race_id = race_id
        self.mcap_path = str(Path(mcap_path))
        self.stdout = stdout
        self.stderr = stderr
        self.progress_every = progress_every
        self.stats = ImportStats(race_id=race_id, mcap_path=self.mcap_path)
        self._msg_type_cache: Dict[str, Any] = {}
        self._skip_log_budget: Dict[str, int] = {}

    def run(self) -> ImportStats:
        self._log_info(f"Starting import: race_id={self.race_id}, file={self.mcap_path}")
        reader, type_map = self._open_reader_and_types(self.mcap_path)

        while reader.has_next():
            self.stats.total_seen += 1
            try:
                topic, raw_data, bag_timestamp = reader.read_next()
            except Exception as exc:  # pragma: no cover
                self._record_error("__reader__", f"read_next failed: {exc}")
                continue

            spec = TOPIC_REGISTRY.get(topic)
            if spec is None:
                self._record_skip(topic, "unsupported topic")
                self._log_progress()
                continue

            msg_type_name = type_map.get(topic)
            if not msg_type_name:
                self._record_error(topic, "missing topic type metadata")
                self._log_progress()
                continue

            try:
                msg = self._decode_message(raw_data, msg_type_name)
            except Exception as exc:
                self._record_error(topic, f"decode failed: {exc}")
                self._log_progress()
                continue

            try:
                self._save_message(topic=topic, msg=msg, bag_timestamp=bag_timestamp, spec=spec)
                self.stats.total_saved += 1
            except Exception as exc:
                self._record_error(topic, f"db save failed: {exc}")

            self._log_progress()

        self._log_summary()
        return self.stats

    def _open_reader_and_types(self, mcap_path: str):
        try:
            import rosbag2_py
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "rosbag2_py is not available. Ensure ROS2 + rosbag2_storage_mcap are installed and sourced."
            ) from exc

        reader = rosbag2_py.SequentialReader()
        reader.open(
            rosbag2_py.StorageOptions(uri=mcap_path, storage_id="mcap"),
            rosbag2_py.ConverterOptions(
                input_serialization_format="cdr",
                output_serialization_format="cdr",
            ),
        )
        topic_types = reader.get_all_topics_and_types()
        type_map = {t.name: t.type for t in topic_types}
        return reader, type_map

    def _decode_message(self, raw_data: bytes, msg_type_name: str):
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message

        msg_cls = self._msg_type_cache.get(msg_type_name)
        if msg_cls is None:
            msg_cls = get_message(msg_type_name)
            self._msg_type_cache[msg_type_name] = msg_cls
        return deserialize_message(raw_data, msg_cls)

    def _save_message(self, topic: str, msg: Any, bag_timestamp: int, spec: TopicSpec) -> None:
        identity_data = self._identity_data(topic=topic, msg=msg, bag_timestamp=bag_timestamp)

        with transaction.atomic():
            identity, _ = TelemetryIdentity.objects.get_or_create(
                race_id=identity_data["race_id"],
                topic_name=identity_data["topic_name"],
                ts_ns=identity_data["ts_ns"],
                frame_id=identity_data["frame_id"],
                source_seq=identity_data["source_seq"],
                defaults={},
            )

            if spec.repeated:
                rows = self._build_repeated_rows(spec=spec, msg=msg)
                for row in rows:
                    row["record"] = identity
                    spec.model.objects.update_or_create(
                        record=identity,
                        transform_index=row["transform_index"],
                        defaults=row,
                    )
                    self.stats.rows_written += 1
                return

            payload = self._build_payload(spec=spec, msg=msg)
            spec.model.objects.update_or_create(record=identity, defaults=payload)
            self.stats.rows_written += 1

    def _identity_data(self, topic: str, msg: Any, bag_timestamp: int) -> Dict[str, Any]:
        frame_id = ""
        source_seq = -1
        ts_ns = int(bag_timestamp)

        header = getattr(msg, "header", None)
        if header is not None:
            frame_id = str(getattr(header, "frame_id", "") or "")
            source_seq = int(getattr(header, "seq", -1) if hasattr(header, "seq") else -1)
            header_stamp = getattr(header, "stamp", None)
            if header_stamp is not None:
                ts_ns = self._to_ns(header_stamp, default=ts_ns)

        # TFMessage has no top-level header. For identity dedupe, keep ts/frame based on
        # bag message metadata (not per-transform frame context). Per-transform stamp/frame
        # is stored in TopicTfTransform rows.
        if topic == "/tf" and hasattr(msg, "transforms") and msg.transforms:
            frame_id = ""
            ts_ns = int(bag_timestamp)

        return {
            "race_id": self.race_id,
            "frame_id": frame_id,
            "ts_ns": ts_ns,
            "topic_name": topic,
            "source_seq": source_seq,
        }

    def _build_payload(self, spec: TopicSpec, msg: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for source_path, model_field in spec.field_map.items():
            value = self._extract_path(msg, source_path)
            payload[model_field] = self._normalize_value(value)
        return payload

    def _build_repeated_rows(self, spec: TopicSpec, msg: Any) -> list[Dict[str, Any]]:
        transforms = getattr(msg, "transforms", None)
        if transforms is None:
            raise ValueError("Expected TFMessage with transforms[]")

        rows: list[Dict[str, Any]] = []
        for idx, transform in enumerate(transforms):
            row: Dict[str, Any] = {}
            for source_path, model_field in spec.field_map.items():
                if source_path == "transforms[] index":
                    row[model_field] = idx
                    continue
                if not source_path.startswith("transforms[]"):
                    continue
                child_path = source_path.replace("transforms[].", "", 1)
                value = self._extract_path(transform, child_path)
                row[model_field] = self._normalize_value(value)
            rows.append(row)
        return rows

    @staticmethod
    def _extract_path(obj: Any, path: str) -> Any:
        current = obj
        for part in path.split("."):
            current = getattr(current, part)
        return current

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        if hasattr(value, "sec") and hasattr(value, "nanosec"):
            return int(value.sec) * 1_000_000_000 + int(value.nanosec)
        return value

    @staticmethod
    def _to_ns(stamp: Any, default: int) -> int:
        if stamp is None:
            return int(default)
        if hasattr(stamp, "sec") and hasattr(stamp, "nanosec"):
            return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
        return int(default)

    def _record_skip(self, topic: str, reason: str) -> None:
        self.stats.total_skipped += 1
        self.stats.skipped_by_topic[topic] = self.stats.skipped_by_topic.get(topic, 0) + 1

        budget = self._skip_log_budget.get(topic, 0)
        if budget < 3:
            self._skip_log_budget[topic] = budget + 1
            self._log_warn(f"Skipping topic={topic}: {reason}")
        elif budget == 3:
            self._skip_log_budget[topic] = budget + 1
            self._log_warn(f"Skipping topic={topic}: further skip logs suppressed")

    def _record_error(self, topic: str, reason: str) -> None:
        self.stats.total_errors += 1
        self.stats.errors_by_topic[topic] = self.stats.errors_by_topic.get(topic, 0) + 1
        self._log_error(f"Error topic={topic}: {reason}")

    def _log_progress(self) -> None:
        if self.progress_every <= 0:
            return
        if self.stats.total_seen % self.progress_every != 0:
            return
        self._log_info(
            "Progress "
            f"seen={self.stats.total_seen} saved={self.stats.total_saved} "
            f"skipped={self.stats.total_skipped} errors={self.stats.total_errors}"
        )

    def _log_summary(self) -> None:
        self._log_info("Import complete")
        self._log_info(f"  file: {self.mcap_path}")
        self._log_info(f"  race_id: {self.race_id}")
        self._log_info(f"  total_seen: {self.stats.total_seen}")
        self._log_info(f"  total_saved: {self.stats.total_saved}")
        self._log_info(f"  total_skipped: {self.stats.total_skipped}")
        self._log_info(f"  total_errors: {self.stats.total_errors}")
        self._log_info(f"  rows_written: {self.stats.rows_written}")

    def _log_info(self, msg: str) -> None:
        self.stdout.write(msg)

    def _log_warn(self, msg: str) -> None:
        self.stdout.write(f"WARN: {msg}")

    def _log_error(self, msg: str) -> None:
        self.stderr.write(f"ERROR: {msg}")
