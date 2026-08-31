import logging
import os
from datetime import datetime, timezone
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

load_dotenv()

logger = logging.getLogger("AI_Surveillance.Database")

# Environment Variable with fallback to Atlas URI
MONGO_DETAILS = os.getenv(
    "MONGO_URI",
    os.getenv(
        "MONGO_URL",
        "YOUR_MONGODB_ATLAS_CONNECTION_STRING",
    ),
)

# Common User ID & DVR ID
DEFAULT_USER_ID = "6a297267444fad049b868973"
DEFAULT_DVR_ID = "6a48cb6a17e14a857b2af360"

# ✅ 1 TO 16 ALL CAMERAS MAPPED WITH MODE (Crowd / Fight)
# CAMERA_MAPPING = {
#     "OFIC_CH01": {
#         "camera_id": "6a48cb6a17e14a857b2af361",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=1&ids=2",
#         "mode": "crowd",
#         "name": "Camera 01 (Crowd)"
#     },
#     "OFIC_CH02": {
#         "camera_id": "6a48cb6a17e14a857b2af362",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=2&ids=2",
#         "mode": "crowd",
#         "name": "Camera 02 (Crowd)"
#     },
#     "OFIC_CH03": {
#         "camera_id": "6a48cb6a17e14a857b2af363",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=3&ids=2",
#         "mode": "crowd",
#         "name": "Camera 03 (Crowd)"
#     },
#     "OFIC_CH04": {
#         "camera_id": "6a48cb6a17e14a857b2af364",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=4&ids=2",
#         "mode": "crowd",
#         "name": "Camera 04 (Crowd)"
#     },
#     "OFIC_CH05": {
#         "camera_id": "6a48cb6a17e14a857b2af365",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=5&ids=2",
#         "mode": "crowd",
#         "name": "Camera 05 (Crowd)"
#     },
#     "OFIC_CH06": {
#         "camera_id": "6a48cb6a17e14a857b2af366",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=6&ids=2",
#         "mode": "crowd",
#         "name": "Camera 06 (Crowd)"
#     },
#     "OFIC_CH07": {
#         "camera_id": "6a48cb6a17e14a857b2af367",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=7&ids=2",
#         "mode": "crowd",
#         "name": "Camera 07 (Crowd)"
#     },
#     "OFIC_CH08": {
#         "camera_id": "6a48cb6a17e14a857b2af368",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=8&ids=2",
#         "mode": "crowd",
#         "name": "Camera 08 (Crowd)"
#     },
#     "OFIC_CH09": {
#         "camera_id": "6a48cb6a17e14a857b2af369",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=9&ids=2",
#         "mode": "crowd",
#         "name": "Camera 09 (Crowd)"
#     },
#     "OFIC_CH10": {
#         "camera_id": "6a48cb6a17e14a857b2af36a",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=10&ids=2",
#         "mode": "crowd",
#         "name": "Camera 10 (Crowd)"
#     },
#     "OFIC_CH11": {
#         "camera_id": "6a48cb6a17e14a857b2af36b",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=11&ids=2",
#         "mode": "crowd",
#         "name": "Camera 11 (Crowd)"
#     },
#     "OFIC_CH12": {
#         "camera_id": "6a48cb6a17e14a857b2af36c",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=12&ids=2",
#         "mode": "crowd",
#         "name": "Camera 12 (Crowd)"
#     },
#     "OFIC_CH13": {
#         "camera_id": "6a48cb6a17e14a857b2af36d",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=13&ids=2",
#         "mode": "fight",
#         "name": "Camera 13 (Fight)"
#     },
#     "OFIC_CH14": {
#         "camera_id": "6a48cb6a17e14a857b2af36e",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=14&ids=2",
#         "mode": "fight",
#         "name": "Camera 14 (Fight)"
#     },
#     "OFIC_CH15": {
#         "camera_id": "6a48cb6a17e14a857b2af36f",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=15&ids=2",
#         "mode": "fight",
#         "name": "Camera 15 (Fight)"
#     },
#     "OFIC_CH16": {
#         "camera_id": "6a48cb6a17e14a857b2af370",
#         "rtsp_url": "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=16&ids=2",
#         "mode": "fight",
#         "name": "Camera 16 (Fight)"
#     },
# }

CAMERA_MAPPING = {
    "OFIC_CH01": {
        "camera_id": "6a48cb6a17e14a857b2af361",
        "rtsp_url": "rtsp://admin:Msspl@1234@192.168.1.249:2001/video/live?channel=1&subtype=0",
        "mode": "crowd",
        "name": "Camera 01 (Crowd)"
    }
}

print(camera_mapping := CAMERA_MAPPING)  # Debugging: Print the camera mapping

client = None
database = None
crowd_collection = None
fight_collection = None

try:
    client = MongoClient(MONGO_DETAILS, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")

    database = client["surveillance_db"]
    crowd_collection = database["crowd_events"]
    fight_collection = database["fight_events"]

    logger.info("[DATABASE] Connected to MongoDB Atlas Successfully!")

except (ConnectionFailure, ServerSelectionTimeoutError) as e:
    logger.error(
        f"[DATABASE] Could not connect to MongoDB (Timeout/Network): {e}"
    )
except Exception as e:
    logger.error(f"[DATABASE] Unexpected Database connection error: {e}")


def get_camera_info(camera_key: str):
    """Camera Code (OFIC_CH16) ya RTSP URL se dynamic camera data dhundega."""
    if not camera_key:
        return CAMERA_MAPPING["OFIC_CH16"]

    # Direct match by Code
    if camera_key in CAMERA_MAPPING:
        return CAMERA_MAPPING[camera_key]

    # Match by RTSP URL
    for code, info in CAMERA_MAPPING.items():
        if info["rtsp_url"] == camera_key:
            return info

    # Fallback to Channel 16
    return CAMERA_MAPPING["OFIC_CH16"]


# 🚀 NEW FUNCTION ADDED FOR MULTI-CAMERA DASHBOARD GRID
def get_all_cameras():
    """Returns a list of all registered cameras for dynamic UI generation."""
    cameras_list = []
    for code, info in CAMERA_MAPPING.items():
        cameras_list.append({
            "code": code,
            "camera_id": info["camera_id"],
            "rtsp_url": info["rtsp_url"],
            "mode": info.get("mode", "crowd"),
            "name": info.get("name", code)
        })
    return cameras_list


def save_detection_event(
    event_type: str,
    base64_image: str,
    confidence: float,
    camera_key: str = "OFIC_CH16",
    user_id: str = None,
    dvr_id: str = None,
):
    """Saves detection event with dynamic Camera ID, RTSP URL, User ID & DVR ID."""
    if database is None:
        logger.error(
            "[DATABASE] Cannot save event: MongoDB is not connected."
        )
        return None

    try:
        now = datetime.now(timezone.utc)

        cam_info = get_camera_info(camera_key)
        cam_id = cam_info["camera_id"]
        rtsp_url = cam_info["rtsp_url"]

        u_id = user_id if user_id else DEFAULT_USER_ID
        d_id = dvr_id if dvr_id else DEFAULT_DVR_ID

        document = {
            "cameraId": ObjectId(cam_id)
            if ObjectId.is_valid(cam_id)
            else cam_id,
            "userId": ObjectId(u_id) if ObjectId.is_valid(u_id) else u_id,
            "dvrId": ObjectId(d_id) if ObjectId.is_valid(d_id) else d_id,
            "rtspUrl": rtsp_url,
            "eventType": event_type,
            "image": base64_image,
            "isRead": False,
            "confidence": round(float(confidence), 4),
            "createdAt": now,
            "updatedAt": now,
        }

        if "fight" in str(event_type).lower():
            target_collection = fight_collection
        else:
            target_collection = crowd_collection

        result = target_collection.insert_one(document)
        logger.info(
            f"[DATABASE] Saved in '{target_collection.name}' | Type: '{event_type}' | CamID: {cam_id} | Mongo ID: {result.inserted_id}"
        )
        return str(result.inserted_id)

    except Exception as e:
        logger.error(f"[DATABASE] Failed to insert event: {e}")
        return None