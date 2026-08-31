from collections import deque
import base64
import logging
import os
import threading
import time

import cv2
import torch
from ultralytics import YOLO

from alert_manager import alert_helper
from database import save_detection_event

logger = logging.getLogger("AI_Surveillance.Detector")

# Absolute Path Resolution
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VIDEO_PATH = os.path.join(BASE_DIR, "f1.mp4")
DEFAULT_MODEL_PATH = os.path.join(BASE_DIR, "yolov8m.pt")


class SurveillanceEngine:

    def __init__(
        self,
        model_path=DEFAULT_MODEL_PATH,
        crowd_threshold=5,
        crowd_duration=1.0,
        group_distance_factor=1.5,
        alert_cooldown=30.0,
        db_save_cooldown=5.0,
    ):
        self.model_path = model_path
        self.crowd_threshold = crowd_threshold
        self.crowd_duration = crowd_duration
        self.group_distance_factor = group_distance_factor
        self.alert_cooldown = alert_cooldown
        self.db_save_cooldown = db_save_cooldown

        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"

        # Thread Lock for Thread-Safe Concurrency across Multiple Cameras
        self.model_lock = threading.Lock()

        # Per-Camera State Dictionaries (Prevents State Leakage across Streams)
        self.last_db_save_times = {}
        self.last_alert_times = {}
        self.crowd_start_times = {}
        self.crowd_confirmed_states = {}

        logger.info(f"[ENGINE] Loading YOLO Model from: {self.model_path}")
        logger.info(f"[ENGINE] Hardware Accelerator: {self.device}")

        try:
            self.model = YOLO(self.model_path)
            logger.info("[ENGINE] YOLOv8 Model loaded successfully!")
        except Exception as e:
            logger.error(f"[ERROR] Failed to load YOLO model: {e}")
            raise RuntimeError(f"Could not initialize YOLO model: {e}")

    def get_person_data(self, boxes):
        persons = []
        if boxes is None or len(boxes) == 0:
            return persons

        xyxy = boxes.xyxy.cpu().numpy()
        for box in xyxy:
            x1, y1, x2, y2 = box
            width = max(1.0, x2 - x1)
            height = max(1.0, y2 - y1)
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            person_size = (width + height) / 2.0

            persons.append({
                "center": (cx, cy),
                "width": width,
                "height": height,
                "size": person_size,
            })

        return persons

    def are_people_close(self, person_a, person_b):
        x1, y1 = person_a["center"]
        x2, y2 = person_b["center"]
        distance = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
        avg_size = (person_a["size"] + person_b["size"]) / 2.0
        allowed_distance = avg_size * self.group_distance_factor
        return distance <= allowed_distance

    def is_group_compact(self, group, persons):
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

    def detect_crowd_group(self, persons):
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
            if len(
                group
            ) >= self.crowd_threshold and self.is_group_compact(group, persons):
                return True

        return False

    def generate_stream_frames(
        self, video_source=DEFAULT_VIDEO_PATH, camera_key="OFIC_CH16"
    ):
        logger.info(
            f"[STREAM] Opening stream for camera [{camera_key}]: {video_source}"
        )

        if (
            not str(video_source).startswith("rtsp")
            and not str(video_source).startswith("http")
            and not os.path.exists(str(video_source))
        ):
            logger.error(
                f"[CRITICAL ERROR] Source NOT found for [{camera_key}]: {video_source}"
            )
            return

        cap = cv2.VideoCapture(video_source, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            logger.error(
                f"[CRITICAL ERROR] OpenCV failed to open stream for [{camera_key}]:"
                f" {video_source}"
            )
            return

        # Per-Camera State Initialization
        self.last_db_save_times.setdefault(camera_key, 0)
        self.last_alert_times.setdefault(camera_key, 0)
        self.crowd_start_times.setdefault(camera_key, None)
        self.crowd_confirmed_states.setdefault(camera_key, False)

        frame_count = 0

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    if str(video_source).startswith("rtsp"):
                        logger.warning(
                            f"[STREAM] RTSP [{camera_key}] interrupted. Re-connecting..."
                        )
                        cap.release()
                        time.sleep(1)
                        cap = cv2.VideoCapture(video_source, cv2.CAP_FFMPEG)
                        continue
                    else:
                        logger.warning(
                            f"[STREAM] End of file [{camera_key}]. Resetting loop..."
                        )
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        self.crowd_start_times[camera_key] = None
                        self.crowd_confirmed_states[camera_key] = False
                        continue

                frame_count += 1
                frame = cv2.resize(frame, (854, 480))

                # Thread-safe YOLO Inference Call
                with self.model_lock:
                    results = self.model(
                        frame, device=self.device, classes=[0], verbose=False
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

                    crowd_duration = (
                        current_time - self.crowd_start_times[camera_key]
                    )

                    if crowd_duration >= self.crowd_duration:
                        if not self.crowd_confirmed_states[camera_key]:
                            self.crowd_confirmed_states[camera_key] = True
                            logger.warning(
                                f"[{camera_key}] !!! CROWD CONFIRMED !!! Persons:"
                                f" {person_count}"
                            )

                        # Red Visual Overlay Banner
                        cv2.rectangle(
                            annotated_frame,
                            (0, 0),
                            (annotated_frame.shape[1], 40),
                            (0, 0, 200),
                            -1,
                        )
                        cv2.putText(
                            annotated_frame,
                            f"CRITICAL ALERT: CROWD SURGE! ({person_count} Persons)",
                            (15, 27),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (255, 255, 255),
                            2,
                        )

                        # Protected Alert Cooldown check & execution
                        if (
                            current_time - self.last_alert_times[camera_key]
                            >= self.alert_cooldown
                        ):
                            try:
                                alert_helper.trigger_crowd_alert(
                                    annotated_frame, camera_key=camera_key
                                )
                                self.last_alert_times[camera_key] = current_time
                                logger.info(
                                    f"[{camera_key}] Crowd alert notification sent"
                                    " successfully."
                                )
                            except Exception as alert_err:
                                logger.error(
                                    f"[{camera_key}] Crowd alert notification failed:"
                                    f" {alert_err}"
                                )

                        # Protected MongoDB Save check & execution
                        if (
                            current_time - self.last_db_save_times[camera_key]
                            >= self.db_save_cooldown
                        ):
                            encode_success, img_buffer = cv2.imencode(".jpg", annotated_frame)
                            if not encode_success:
                                logger.error(
                                    f"[{camera_key}] Failed to encode annotated frame to JPEG"
                                )
                            else:
                                base64_str = "data:image/jpeg;base64," + base64.b64encode(
                                    img_buffer
                                ).decode("utf-8")
                                avg_conf = (
                                    float(boxes.conf.mean().cpu().numpy())
                                    if len(boxes) > 0
                                    else 0.85
                                )

                                try:
                                    save_detection_event(
                                        event_type="crowd detection",
                                        base64_image=base64_str,
                                        confidence=avg_conf,
                                        camera_key=camera_key,
                                    )
                                    self.last_db_save_times[camera_key] = current_time
                                    logger.info(
                                        f"[{camera_key}] Crowd detection event saved to MongoDB."
                                    )
                                except Exception as mongo_err:
                                    logger.error(
                                        f"[{camera_key}] MongoDB save failed: {mongo_err}"
                                    )

                    else:
                        remaining = self.crowd_duration - crowd_duration
                        cv2.rectangle(
                            annotated_frame,
                            (0, 0),
                            (annotated_frame.shape[1], 40),
                            (0, 120, 200),
                            -1,
                        )
                        cv2.putText(
                            annotated_frame,
                            f"CROWD CHECKING... {remaining:.1f}s",
                            (15, 27),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (255, 255, 255),
                            2,
                        )
                else:
                    # Reset state when crowd disperses
                    self.crowd_start_times[camera_key] = None
                    self.crowd_confirmed_states[camera_key] = False

                    cv2.rectangle(
                        annotated_frame,
                        (0, 0),
                        (annotated_frame.shape[1], 40),
                        (0, 150, 0),
                        -1,
                    )
                    cv2.putText(
                        annotated_frame,
                        f"STATUS: NORMAL | Person Count: {person_count}",
                        (15, 27),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (255, 255, 255),
                        2,
                    )

                # Output Stream Frame Encoding with Validation
                stream_encode_success, buffer = cv2.imencode(
                    ".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80]
                )
                if not stream_encode_success:
                    logger.error(
                        f"[{camera_key}] Failed to encode stream frame to JPEG"
                    )
                    continue

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + buffer.tobytes()
                    + b"\r\n"
                )

        finally:
            cap.release()


# Global Detector Engine Shared Instance
detector_engine = SurveillanceEngine(
    crowd_threshold=5,
    crowd_duration=1.0,
    group_distance_factor=1.5,
    alert_cooldown=30.0,
    db_save_cooldown=5.0,
)