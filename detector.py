import base64
import logging
import os
import threading
import time
from collections import deque
from typing import Generator

import cv2
import torch
from ultralytics import YOLO

from alert_manager import alert_helper
from database import save_detection_event

# ============================================================
# LOGGING & PATHS
# ============================================================

logger = logging.getLogger("AI_Surveillance.Detector")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VIDEO_PATH = os.path.join(BASE_DIR, "f1.mp4")

# Primary and Fallback Model Paths
PRIMARY_MODEL = os.path.join(BASE_DIR, "yolov8m.pt")
FALLBACK_MODEL = os.path.join(BASE_DIR, "yolov8n.pt")
DEFAULT_MODEL_PATH = PRIMARY_MODEL if os.path.exists(PRIMARY_MODEL) else FALLBACK_MODEL


# ============================================================
# SURVEILLANCE ENGINE CLASS
# ============================================================

class SurveillanceEngine:

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        crowd_threshold: int = 5,
        crowd_duration: float = 1.0,
        group_distance_factor: float = 1.5,
        alert_cooldown: float = 30.0,
        db_save_cooldown: float = 5.0,
    ):
        self.model_path = model_path
        self.crowd_threshold = crowd_threshold
        self.crowd_duration = crowd_duration
        self.group_distance_factor = group_distance_factor
        self.alert_cooldown = alert_cooldown
        self.db_save_cooldown = db_save_cooldown

        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"

        # Thread Lock for Safe Concurrency Across Multiple Cameras
        self.model_lock = threading.Lock()

        # Isolated Per-Camera State Dictionaries
        self.last_db_save_times = {}
        self.last_alert_times = {}
        self.crowd_start_times = {}
        self.crowd_confirmed_states = {}

        logger.info(f"[ENGINE] Loading YOLO Model from: {self.model_path}")
        logger.info(f"[ENGINE] Hardware Device Accelerator: {self.device}")

        try:
            self.model = YOLO(self.model_path)
            logger.info("[ENGINE] YOLOv8 Model loaded successfully!")
        except Exception as e:
            logger.error(f"[ERROR] Failed to load primary YOLO model '{self.model_path}': {e}")
            logger.info(f"[ENGINE] Attempting fallback to '{FALLBACK_MODEL}'...")
            self.model = YOLO(FALLBACK_MODEL)
            self.model_path = FALLBACK_MODEL

    def get_person_data(self, boxes):
        persons = []
        if boxes is None or len(boxes) == 0:
            return persons

        xyxy = boxes.xyxy.cpu().numpy()
        for box in xyxy:
            x1, y1, x2, y2 = box
            width = max(1.0, float(x2 - x1))
            height = max(1.0, float(y2 - y1))
            cx = float(x1 + x2) / 2.0
            cy = float(y1 + y2) / 2.0
            person_size = (width + height) / 2.0

            persons.append({
                "center": (cx, cy),
                "width": width,
                "height": height,
                "size": person_size,
            })

        return persons

    def are_people_close(self, person_a: dict, person_b: dict) -> bool:
        x1, y1 = person_a["center"]
        x2, y2 = person_b["center"]
        distance = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
        avg_size = (person_a["size"] + person_b["size"]) / 2.0
        allowed_distance = avg_size * self.group_distance_factor
        return distance <= allowed_distance

    def is_group_compact(self, group: list, persons: list) -> bool:
        if len(group) < self.crowd_threshold:
            return False

        group_persons = [persons[idx] for idx in group]
        avg_person_size = sum(p["size"] for p in group_persons) / len(group_persons)

        min_x = min(p["center"][0] for p in group_persons)
        max_x = max(p["center"][0] for p in group_persons)
        min_y = min(p["center"][1] for p in group_persons)
        max_y = max(p["center"][1] for p in group_persons)

        max_spread = max(max_x - min_x, max_y - min_y)
        max_allowed_spread = (
            avg_person_size * self.group_distance_factor * (len(group) ** 0.5)
        )

        return max_spread <= max_allowed_spread

    def detect_crowd_group(self, persons: list) -> bool:
        person_count = len(persons)
        if person_count < self.crowd_threshold:
            return False

        visited = set()
        groups = []

        for start_index in range(person_count):
            if start_index in visited:
                continue

            queue = deque([start_index])
            visited.add(start_index)
            current_group = []

            while queue:
                current_index = queue.popleft()
                current_group.append(current_index)
                current_person = persons[current_index]

                for other_index in range(person_count):
                    if other_index in visited:
                        continue

                    other_person = persons[other_index]
                    if self.are_people_close(current_person, other_person):
                        visited.add(other_index)
                        queue.append(other_index)

            groups.append(current_group)

        for group in groups:
            if len(group) >= self.crowd_threshold and self.is_group_compact(group, persons):
                return True

        return False

    def generate_stream_frames(
        self,
        video_source=DEFAULT_VIDEO_PATH,
        camera_key: str = "OFFI_CH01",
    ) -> Generator[bytes, None, None]:
        logger.info(f"[STREAM] Opening stream for camera [{camera_key}]: {video_source}")

        is_rtsp = str(video_source).startswith("rtsp://") or str(video_source).startswith("http://")

        # Fallback if local file doesn't exist
        if not is_rtsp and not os.path.exists(str(video_source)):
            logger.warning(f"[STREAM] Source file '{video_source}' not found. Falling back to default.")
            video_source = DEFAULT_VIDEO_PATH

        cap = cv2.VideoCapture(str(video_source), cv2.CAP_FFMPEG)
        if not cap.isOpened():
            logger.error(f"[STREAM ERROR] OpenCV failed to connect to [{camera_key}]: {video_source}")
            return

        # Initialize Camera State Dictionaries
        self.last_db_save_times.setdefault(camera_key, 0.0)
        self.last_alert_times.setdefault(camera_key, 0.0)
        self.crowd_start_times.setdefault(camera_key, None)
        self.crowd_confirmed_states.setdefault(camera_key, False)

        frame_skip = 0

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    if is_rtsp:
                        logger.warning(f"[STREAM] RTSP disconnected for [{camera_key}]. Retrying in 2 seconds...")
                        cap.release()
                        time.sleep(2)
                        cap = cv2.VideoCapture(str(video_source), cv2.CAP_FFMPEG)
                        continue
                    else:
                        # Re-loop file video
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        self.crowd_start_times[camera_key] = None
                        self.crowd_confirmed_states[camera_key] = False
                        continue

                # Process every 2nd frame to optimize multi-camera GPU usage
                frame_skip += 1
                frame = cv2.resize(frame, (640, 360))

                # Thread-safe GPU Inference
                with self.model_lock:
                    results = self.model(
                        frame,
                        device=self.device,
                        classes=[0],
                        verbose=False,
                        conf=0.4,
                    )

                boxes = results[0].boxes
                person_count = len(boxes)
                persons = self.get_person_data(boxes)
                annotated_frame = results[0].plot()

                crowd_group_detected = self.detect_crowd_group(persons)
                current_time = time.time()

                if crowd_group_detected:
                    if self.crowd_start_times[camera_key] is None:
                        self.crowd_start_times[camera_key] = current_time

                    crowd_duration = current_time - self.crowd_start_times[camera_key]

                    if crowd_duration >= self.crowd_duration:
                        if not self.crowd_confirmed_states[camera_key]:
                            self.crowd_confirmed_states[camera_key] = True
                            logger.warning(f"[{camera_key}] CROWD CONFIRMED! Persons: {person_count}")

                        # Visual Banner
                        cv2.rectangle(annotated_frame, (0, 0), (annotated_frame.shape[1], 35), (0, 0, 200), -1)
                        cv2.putText(
                            annotated_frame,
                            f"CRITICAL: CROWD SURGE! ({person_count} Persons)",
                            (10, 24),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.65,
                            (255, 255, 255),
                            2,
                        )

                        # Trigger Audio / System Alert
                        if current_time - self.last_alert_times[camera_key] >= self.alert_cooldown:
                            try:
                                alert_helper.trigger_crowd_alert(annotated_frame, camera_key=camera_key)
                                self.last_alert_times[camera_key] = current_time
                            except Exception as alert_err:
                                logger.error(f"[{camera_key}] Alert trigger failed: {alert_err}")

                        # Save Detection Snapshot to MongoDB
                        if current_time - self.last_db_save_times[camera_key] >= self.db_save_cooldown:
                            encode_ok, buffer = cv2.imencode(".jpg", annotated_frame)
                            if encode_ok:
                                base64_str = "data:image/jpeg;base64," + base64.b64encode(buffer).decode("utf-8")
                                avg_conf = float(boxes.conf.mean().cpu().numpy()) if len(boxes) > 0 else 0.85
                                try:
                                    save_detection_event(
                                        event_type="crowd detection",
                                        base64_image=base64_str,
                                        confidence=avg_conf,
                                        camera_key=camera_key,
                                    )
                                    self.last_db_save_times[camera_key] = current_time
                                    logger.info(f"[{camera_key}] Crowd detection event saved to MongoDB.")
                                except Exception as db_err:
                                    logger.error(f"[{camera_key}] Database save failed: {db_err}")
                    else:
                        remaining = self.crowd_duration - crowd_duration
                        cv2.rectangle(annotated_frame, (0, 0), (annotated_frame.shape[1], 35), (0, 120, 200), -1)
                        cv2.putText(
                            annotated_frame,
                            f"CROWD CHECKING... {remaining:.1f}s ({person_count})",
                            (10, 24),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.65,
                            (255, 255, 255),
                            2,
                        )
                else:
                    self.crowd_start_times[camera_key] = None
                    self.crowd_confirmed_states[camera_key] = False

                    cv2.rectangle(annotated_frame, (0, 0), (annotated_frame.shape[1], 35), (0, 150, 0), -1)
                    cv2.putText(
                        annotated_frame,
                        f"STATUS: NORMAL | Persons: {person_count}",
                        (10, 24),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        (255, 255, 255),
                        2,
                    )

                # MJPEG Frame Output
                encode_ok, frame_buffer = cv2.imencode(
                    ".jpg",
                    annotated_frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 75],
                )
                if not encode_ok:
                    continue

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_buffer.tobytes()
                    + b"\r\n"
                )

        finally:
            cap.release()
            logger.info(f"[STREAM] Stream released for camera [{camera_key}]")


# ============================================================
# SHARED INSTANCE
# ============================================================

detector_engine = SurveillanceEngine(
    crowd_threshold=5,
    crowd_duration=1.0,
    group_distance_factor=1.5,
    alert_cooldown=30.0,
    db_save_cooldown=5.0,
)