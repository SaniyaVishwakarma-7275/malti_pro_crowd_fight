import base64
import logging
import os
import threading
import time
from datetime import datetime, timezone
import cv2
from database import save_detection_event  # 👈 Schema matching Mongo Helper

try:
    import winsound
except ImportError:
    winsound = None

logger = logging.getLogger("AI_Surveillance.AlertManager")


class AlertManager:

    def __init__(self, cooldown_seconds=5):
        self.alerts_dir = "alerts"
        os.makedirs(self.alerts_dir, exist_ok=True)
        self.cooldown_seconds = cooldown_seconds
        self.last_alert_time = {}

    def is_on_cooldown(self, alert_type: str) -> bool:
        current_time = time.time()
        if alert_type in self.last_alert_time:
            elapsed = current_time - self.last_alert_time[alert_type]
            if elapsed < self.cooldown_seconds:
                return True
        return False

    def play_alarm_sound(self):
        def sound_thread():
            try:
                if winsound:
                    winsound.Beep(1000, 800)
                else:
                    print("\a", end="", flush=True)
            except Exception as e:
                logger.error(f"[SOUND ENGINE] Error playing alarm sound: {e}")

        threading.Thread(target=sound_thread, daemon=True).start()

    def save_alert_and_log_db(
        self,
        frame,
        alert_type="Fight Alert",
        confidence=0.85,
        camera_key="OFIC_CH14",
    ):
        if self.is_on_cooldown(alert_type):
            return None

        try:
            self.last_alert_time[alert_type] = time.time()
            self.play_alarm_sound()

            now_utc = datetime.now(timezone.utc)
            timestamp_str = now_utc.strftime("%Y%m%d_%H%M%S_%f")[:19]
            filename = f"alert_{timestamp_str}.jpg"
            filepath = os.path.join(self.alerts_dir, filename)

            # 1. Local Image Save
            success = cv2.imwrite(filepath, frame)
            if success:
                logger.info(f"[ALERT] Saved alert screenshot: {filename}")
            else:
                logger.error(f"[ALERT] Failed to save screenshot locally: {filename}")

            # 2. Convert Frame to Base64 String
            _, img_buffer = cv2.imencode(".jpg", frame)
            base64_str = (
                "data:image/jpeg;base64,"
                + base64.b64encode(img_buffer).decode("utf-8")
            )

            event_type_mapped = (
                "fight detection"
                if "fight" in alert_type.lower()
                else "crowd detection"
            )

            # 3. MongoDB Log in Background Thread
            def log_to_db():
                try:
                    save_detection_event(
                        event_type=event_type_mapped,
                        base64_image=base64_str,
                        confidence=confidence,
                        camera_key=camera_key,
                    )
                    logger.info(
                        f"[DATABASE] Logged {event_type_mapped} Base64 event for camera: {camera_key}."
                    )
                except Exception as db_err:
                    logger.error(f"[DATABASE] MongoDB Insertion failed: {db_err}")

            threading.Thread(target=log_to_db, daemon=True).start()
            return filename

        except Exception as e:
            logger.error(f"Error handling alert execution: {e}")
            return None

    def trigger_fight_alert(
        self, frame, confidence=0.85, camera_key="OFIC_CH14"
    ):
        return self.save_alert_and_log_db(
            frame,
            alert_type="Fight Alert",
            confidence=confidence,
            camera_key=camera_key,
        )

    def trigger_crowd_alert(
        self, frame, confidence=0.85, camera_key="OFIC_CH16"
    ):
        return self.save_alert_and_log_db(
            frame,
            alert_type="Crowd Alert",
            confidence=confidence,
            camera_key=camera_key,
        )


alert_helper = AlertManager(cooldown_seconds=5)