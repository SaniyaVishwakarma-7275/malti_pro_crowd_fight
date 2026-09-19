import logging
import os
from datetime import datetime, timezone
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

logger = logging.getLogger("AI_Surveillance.Database")

MONGO_URI = os.getenv("MONGO_URL", "mongodb://160.25.62.112:8127")
DB_NAME = os.getenv("MONGO_DATABASE", "cctvControl")

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]

    cameras_collection = db["cameras"]
    
    # Matching collections from your Compass
    crowd_collection = db["crowd detect"]
    fight_collection = db["events"]
    
    logger.info(f"Connected to MongoDB at {MONGO_URI}, DB: {DB_NAME}")
except Exception as e:
    logger.error("Failed to connect to MongoDB: %s", e)
    client = None
    db = None
    cameras_collection = None
    crowd_collection = None
    fight_collection = None


def fix_camera_ip(cam: dict) -> dict:
    """
    Auto-replaces the unreachable public IP (122.162.237.4)
    with the working local DVR IP (192.168.1.112).
    """
    if not cam:
        return cam
    if "rtspUrl" in cam and cam["rtspUrl"]:
        cam["rtspUrl"] = cam["rtspUrl"].replace("122.162.237.4", "192.168.1.112")
    return cam


def get_all_cameras(online_only: bool = False):
    """
    Fetch cameras from MongoDB matching your schema ('isActive: true').
    If online_only is True, only returns cameras with 'isOnline: true'.
    """
    if cameras_collection is None:
        return []
    try:
        query = {"isActive": True}
        if online_only:
            query["isOnline"] = True

        cameras = list(cameras_collection.find(query))
        for cam in cameras:
            cam["_id"] = str(cam["_id"])
            if "userId" in cam and cam["userId"]:
                cam["userId"] = str(cam["userId"])
            if "dvrId" in cam and cam["dvrId"]:
                cam["dvrId"] = str(cam["dvrId"])
            fix_camera_ip(cam)
        return cameras
    except Exception as e:
        logger.exception("Error fetching cameras: %s", e)
        return []


def get_camera_info(camera_code: str):
    """Fetch single camera configuration by 'code' or '_id' with local IP."""
    if cameras_collection is None:
        return None
    try:
        query_conditions = [{"code": camera_code}]
        if ObjectId.is_valid(camera_code):
            query_conditions.append({"_id": ObjectId(camera_code)})

        cam = cameras_collection.find_one({"$or": query_conditions})
        if cam:
            cam["_id"] = str(cam["_id"])
            if "userId" in cam and cam["userId"]:
                cam["userId"] = str(cam["userId"])
            if "dvrId" in cam and cam["dvrId"]:
                cam["dvrId"] = str(cam["dvrId"])
            fix_camera_ip(cam)
        return cam
    except Exception as e:
        logger.exception("Error fetching camera %s: %s", camera_code, e)
        return None


def save_detection_event(event_data: dict, event_type: str = "crowd"):
    """Save alert event to MongoDB."""
    try:
        target_collection = (
            fight_collection if "fight" in event_type.lower() else crowd_collection
        )
        if target_collection is None:
            logger.warning("Database collection unavailable. Alert not saved.")
            return None

        if "createdAt" not in event_data:
            event_data["createdAt"] = datetime.now(timezone.utc)

        result = target_collection.insert_one(event_data)
        return str(result.inserted_id)
    except Exception as e:
        logger.exception("Failed to save detection event: %s", e)
        return None

# import logging
# import os
# from datetime import datetime, timezone
# from bson import ObjectId
# from dotenv import load_dotenv
# from pymongo import MongoClient

# load_dotenv()

# logger = logging.getLogger("AI_Surveillance.Database")

# MONGO_URI = os.getenv("MONGO_URL", "mongodb://160.25.62.112:8127")
# DB_NAME = os.getenv("MONGO_DATABASE", "cctvControl")

# try:
#     client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
#     db = client[DB_NAME]

#     cameras_collection = db["cameras"]
    
#     # Matching the collections from your Compass sidebar
#     crowd_collection = db["crowd detect"]
#     fight_collection = db["events"]
    
#     logger.info(f"Connected to MongoDB at {MONGO_URI}, DB: {DB_NAME}")
# except Exception as e:
#     logger.error("Failed to connect to MongoDB: %s", e)
#     client = None
#     db = None
#     cameras_collection = None
#     crowd_collection = None
#     fight_collection = None


# def get_all_cameras(online_only: bool = False):
#     """
#     Fetch cameras from MongoDB matching your schema ('isActive: true').
#     If online_only is True, only returns cameras with 'isOnline: true'.
#     """
#     if cameras_collection is None:
#         return []
#     try:
#         # Matches your MongoDB field 'isActive'
#         query = {"isActive": True}
#         if online_only:
#             query["isOnline"] = True

#         cameras = list(cameras_collection.find(query))
#         for cam in cameras:
#             cam["_id"] = str(cam["_id"])
#             if "userId" in cam and cam["userId"]:
#                 cam["userId"] = str(cam["userId"])
#             if "dvrId" in cam and cam["dvrId"]:
#                 cam["dvrId"] = str(cam["dvrId"])
#         return cameras
#     except Exception as e:
#         logger.exception("Error fetching cameras: %s", e)
#         return []


# def get_camera_info(camera_code: str):
#     """Fetch single camera configuration by 'code' or '_id'."""
#     if cameras_collection is None:
#         return None
#     try:
#         query_conditions = [{"code": camera_code}]
#         if ObjectId.is_valid(camera_code):
#             query_conditions.append({"_id": ObjectId(camera_code)})

#         cam = cameras_collection.find_one({"$or": query_conditions})
#         if cam:
#             cam["_id"] = str(cam["_id"])
#             if "userId" in cam and cam["userId"]:
#                 cam["userId"] = str(cam["userId"])
#             if "dvrId" in cam and cam["dvrId"]:
#                 cam["dvrId"] = str(cam["dvrId"])
#         return cam
#     except Exception as e:
#         logger.exception("Error fetching camera %s: %s", camera_code, e)
#         return None


# def save_detection_event(event_data: dict, event_type: str = "crowd"):
#     """Save alert event to MongoDB."""
#     try:
#         target_collection = (
#             fight_collection if "fight" in event_type.lower() else crowd_collection
#         )
#         if target_collection is None:
#             logger.warning("Database collection unavailable. Alert not saved.")
#             return None

#         if "createdAt" not in event_data:
#             event_data["createdAt"] = datetime.now(timezone.utc)

#         result = target_collection.insert_one(event_data)
#         return str(result.inserted_id)
#     except Exception as e:
#         logger.exception("Failed to save detection event: %s", e)
#         return None