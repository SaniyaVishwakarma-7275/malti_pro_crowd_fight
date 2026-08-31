import base64
import logging
import os
import threading
import time
import cv2
from ultralytics import YOLO
from alert_manager import alert_helper
from database import save_detection_event  # 👈 Mongo DB Save Helper

# Pygame & Numpy for dynamic synth beep generation
try:
    import numpy as np
    import pygame

    PYGAME_AVAILABLE = True
except Exception:
    PYGAME_AVAILABLE = False

logger = logging.getLogger("AI_Surveillance.ActionDetector")


class ActionDetectorEngine:

    def __init__(self, model_filename="fight_model.pt"):
        self.device = (
            "cuda" if cv2.cuda.getCudaEnabledDeviceCount() > 0 else "cpu"
        )
        self.last_alarm_time = 0
        
        # 👈 STEP 1 FIX: Class attributes for status tracking without Circular Imports
        self.is_fighting = False
        self.camera_fight_status = {}  # Per-camera fight status mapping
        self.camera_db_save_times = {} # Per-camera database cooldown timer

        if os.path.exists(model_filename):
            try:
                self.model = YOLO(model_filename)
                logger.info(
                    f"Loaded model: {model_filename} with classes: {self.model.names}"
                )
            except Exception as e:
                logger.error(f"Error loading {model_filename}: {e}")
                self.model = YOLO("yolov8n.pt")
        else:
            self.model = YOLO("yolov8n.pt")

    def _play_sound_thread(self):
        """Generate a clean Synth Beep using Pygame + Numpy"""
        try:
            if PYGAME_AVAILABLE:
                if not pygame.mixer.get_init():
                    pygame.mixer.init(
                        frequency=44100, size=-16, channels=2, buffer=512
                    )

                sample_rate = 44100
                duration = 0.4  # seconds
                frequency = 1800  # High-pitched alert frequency (Hz)

                t = np.linspace(
                    0, duration, int(sample_rate * duration), False
                )
                sine_wave = np.sin(2 * np.pi * frequency * t)
                audio_data = (sine_wave * 32767).astype(np.int16)

                stereo_audio = np.ascontiguousarray(
                    np.repeat(audio_data[:, np.newaxis], 2, axis=1)
                )

                sound = pygame.sndarray.make_sound(stereo_audio)
                sound.play()
            else:
                print("\a", end="", flush=True)
        except Exception as e:
            logger.exception("Synth Beep Error")

    def play_system_beep(self):
        """Alarm Beep trigger with cooldown gap"""
        current_time = time.time()
        if current_time - self.last_alarm_time >= 2.5:
            self.last_alarm_time = current_time
            sound_thread = threading.Thread(
                target=self._play_sound_thread, daemon=True
            )
            sound_thread.start()

    def detect_fight_and_stream(self, video_source="fi7.avi", camera_key="OFIC_CH14"):
        """
        camera_key: Dynamic camera channel pass karein (e.g. 'OFIC_CH01' se 'OFIC_CH16' ya RTSP URL)
        """
        # 👈 STEP 5 FIX: FFMPEG backend for RTSP stream stability
        cap = cv2.VideoCapture(video_source, cv2.CAP_FFMPEG)

        if not cap.isOpened():
            logger.error(f"Cannot open video source: {video_source}")
            return

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                if str(video_source).startswith("rtsp"):
                    time.sleep(1)
                    cap = cv2.VideoCapture(video_source, cv2.CAP_FFMPEG)
                    continue
                else:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

            # Model Inference
            results = self.model(frame, conf=0.40, verbose=False)
            fight_detected = False
            max_conf = 0.0

            for result in results:
                boxes = result.boxes
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    class_name = str(self.model.names[cls_id]).lower()

                    # 🚨 CASE 1: FIGHT / VIOLENCE DETECTED (Class 1)
                    if cls_id == 1 or (
                        "violence" in class_name and "non" not in class_name
                    ):
                        fight_detected = True
                        max_conf = max(max_conf, conf)

                        # 🔴 RED Bounding Box
                        cv2.rectangle(
                            frame, (x1, y1), (x2, y2), (0, 0, 255), 3
                        )
                        label = f"FIGHT DETECTED: {int(conf * 100)}%"
                        cv2.putText(
                            frame,
                            label,
                            (x1, max(25, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 0, 255),
                            2,
                        )

                    # 🟢 CASE 2: NORMAL / NON-VIOLENCE (Class 0)
                    else:
                        cv2.rectangle(
                            frame, (x1, y1), (x2, y2), (0, 255, 0), 2
                        )
                        label = f"NORMAL: {int(conf * 100)}%"
                        cv2.putText(
                            frame,
                            label,
                            (x1, max(25, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (0, 255, 0),
                            1,
                        )

            # 🎯 SAFE STATUS SYNC (Multi-camera safe, No app import circular dependency)
            self.is_fighting = fight_detected
            self.camera_fight_status[camera_key] = fight_detected

            # 🚨 Top Alert Banner, Beep Sound, Alert Manager & MongoDB Entry
            if fight_detected:
                cv2.rectangle(
                    frame, (0, 0), (frame.shape[1], 40), (0, 0, 255), -1
                )
                cv2.putText(
                    frame,
                    "🚨 CRITICAL ALERT: FIGHT / VIOLENCE DETECTED 🚨",
                    (15, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    (255, 255, 255),
                    2,
                )

                # 🔔 Trigger Sound Alarm & Alert Manager
                self.play_system_beep()
                
                # Non-blocking Alert Triggering
                threading.Thread(
                    target=alert_helper.trigger_fight_alert,
                    args=(frame.copy(), max_conf, camera_key),
                    daemon=True
                ).start()

                # 💾 SAVE TO MONGODB (Camera-wise 5 second cooldown)
                current_time = time.time()
                last_saved = self.camera_db_save_times.get(camera_key, 0)
                
                if current_time - last_saved >= 5.0:
                    self.camera_db_save_times[camera_key] = current_time

                    def _async_db_save(saved_frame, saved_conf, channel):
                        try:
                            _, img_buffer = cv2.imencode(".jpg", saved_frame)
                            base64_str = (
                                "data:image/jpeg;base64,"
                                + base64.b64encode(img_buffer).decode("utf-8")
                            )

                            save_detection_event(
                                event_type="fight detection",
                                base64_image=base64_str,
                                confidence=saved_conf if saved_conf > 0 else 0.85,
                                camera_key=channel,
                            )
                        except Exception as err:
                            logger.error(f"Failed to async save fight detection: {err}")

                    threading.Thread(
                        target=_async_db_save,
                        args=(frame.copy(), max_conf, camera_key),
                        daemon=True
                    ).start()

            # Stream Encoding
            _, buffer = cv2.imencode(".jpg", frame)
            frame_bytes = buffer.tobytes()

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )

        cap.release()


action_engine = ActionDetectorEngine()