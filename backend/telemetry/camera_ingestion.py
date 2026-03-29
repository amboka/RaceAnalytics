"""Extract and cache camera images from MCAP files."""

import os
from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from django.conf import settings


@dataclass
class CameraImageExtractorStats:
    total_messages: int = 0
    total_saved: int = 0
    total_errors: int = 0


CAMERA_TOPIC_MAP = {
    "/constructor0/sensor/camera_fl/compressed_image": {"camera": 0, "name": "cam0", "label": "front-left"},
    "/constructor0/sensor/camera_r/compressed_image": {"camera": 1, "name": "cam1", "label": "rear"},
}


class McapCameraImageExtractor:
    """Extract camera images from MCAP files and cache them."""

    def __init__(self, mcap_path: str, race_id: str, stdout=None, stderr=None):
        self.mcap_path = str(Path(mcap_path))
        self.race_id = race_id
        self.stdout = stdout
        self.stderr = stderr
        self.stats = CameraImageExtractorStats()
        self._cache_root = Path(settings.MEDIA_ROOT) / "frames" / race_id
        self._frame_counts: Dict[int, int] = {}  # camera -> current frame count

    def run(self) -> CameraImageExtractorStats:
        """Extract all camera images from MCAP and save to disk."""
        self._log_info(f"Starting camera extraction: race_id={self.race_id}, file={self.mcap_path}")
        
        if not Path(self.mcap_path).exists():
            raise RuntimeError(f"MCAP file not found: {self.mcap_path}")
        
        try:
            import rosbag2_py
            from rclpy.serialization import deserialize_message
            from rosidl_runtime_py.utilities import get_message
        except ImportError as exc:
            raise RuntimeError("rosbag2_py not available. Ensure ROS2 + rosbag2_storage_mcap are installed.") from exc
        
        reader = rosbag2_py.SequentialReader()
        reader.open(
            rosbag2_py.StorageOptions(uri=self.mcap_path, storage_id="mcap"),
            rosbag2_py.ConverterOptions(
                input_serialization_format="cdr",
                output_serialization_format="cdr",
            ),
        )
        
        topic_types = reader.get_all_topics_and_types()
        type_map = {t.name: t.type for t in topic_types}
        
        # Cache for message classes
        msg_type_cache = {}
        
        while reader.has_next():
            try:
                topic, raw_data, bag_timestamp = reader.read_next()
            except Exception as exc:
                self._log_error(f"Failed to read next message: {exc}")
                self.stats.total_errors += 1
                continue
            
            if topic not in CAMERA_TOPIC_MAP:
                continue
            
            self.stats.total_messages += 1
            
            # Get message type
            msg_type_name = type_map.get(topic)
            if not msg_type_name:
                self._log_error(f"Missing type for topic {topic}")
                self.stats.total_errors += 1
                continue
            
            try:
                # Deserialize CompressedImage message
                msg_cls = msg_type_cache.get(msg_type_name)
                if msg_cls is None:
                    msg_cls = get_message(msg_type_name)
                    msg_type_cache[msg_type_name] = msg_cls
                
                msg = deserialize_message(raw_data, msg_cls)
                
                # Extract and save image
                camera_info = CAMERA_TOPIC_MAP[topic]
                camera = camera_info["camera"]
                timestamp_ns = self._get_timestamp_ns(msg)
                
                self._save_image(msg=msg, camera=camera, timestamp_ns=timestamp_ns)
                self.stats.total_saved += 1
                
            except Exception as exc:
                self._log_error(f"Error processing topic {topic}: {exc}")
                self.stats.total_errors += 1
        
        self._log_info(
            f"Camera extraction complete: "
            f"seen={self.stats.total_messages} saved={self.stats.total_saved} errors={self.stats.total_errors}"
        )
        return self.stats

    def _save_image(self, msg, camera: int, timestamp_ns: int):
        """Extract image data from CompressedImage message and save to disk."""
        # CompressedImage has a 'data' field with the compressed image bytes
        image_data = getattr(msg, "data", None)
        if not image_data:
            raise ValueError(f"No image data in CompressedImage message")
        
        # Convert list of bytes to bytes
        if isinstance(image_data, list):
            image_data = bytes(image_data)
        
        # Create output directory
        camera_info = next(v for k, v in CAMERA_TOPIC_MAP.items() if v["camera"] == camera)
        camera_name = camera_info["name"]
        cache_dir = self._cache_root / camera_name
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Get next frame number for this camera
        frame_number = self._frame_counts.get(camera, 0)
        self._frame_counts[camera] = frame_number + 1
        
        # Save image file
        filename = f"frame_{frame_number:04d}.jpg"
        file_path = cache_dir / filename
        
        with open(file_path, "wb") as f:
            f.write(image_data)
        
        # Convert timestamp_ns to seconds (from start of recording)
        timestamp_seconds = timestamp_ns / 1_000_000_000
        
        # Store in database for quick lookup
        from .models import CameraFrame
        
        CameraFrame.objects.update_or_create(
            race_id=self.race_id,
            camera=camera,
            frame_number=frame_number,
            defaults={
                "timestamp_seconds": timestamp_seconds,
                "fps": 5,  # Default, will be updated if needed
                "file_path": f"frames/{self.race_id}/{camera_name}/{filename}",
            }
        )

    @staticmethod
    def _get_timestamp_ns(msg) -> int:
        """Extract nanosecond timestamp from message header."""
        header = getattr(msg, "header", None)
        if header is None:
            return 0
        
        stamp = getattr(header, "stamp", None)
        if stamp is None:
            return 0
        
        sec = getattr(stamp, "sec", 0)
        nanosec = getattr(stamp, "nanosec", 0)
        return int(sec) * 1_000_000_000 + int(nanosec)

    def _log_info(self, msg: str):
        if self.stdout:
            self.stdout.write(msg)

    def _log_error(self, msg: str):
        if self.stderr:
            self.stderr.write(f"ERROR: {msg}")
        else:
            print(f"ERROR: {msg}")
