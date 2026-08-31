import glob
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from action_detector import action_engine
from database import crowd_collection, fight_collection, get_all_cameras
from detector import detector_engine

logger = logging.getLogger("AI_Surveillance.APIRoutes")

router = APIRouter(prefix="/api/v1", tags=["Surveillance Management APIs"])


# --- Pydantic Data Models ---
class ThresholdUpdateSchema(BaseModel):
    new_threshold: int = Field(
        ..., gt=0, description="New crowd threshold limit"
    )


class EventStatusSchema(BaseModel):
    event_id: str = Field(..., description="MongoDB ObjectId as string")
    is_read: bool = Field(..., description="Status e.g. True or False")
    event_type: str = Field(
        default="crowd",
        description="Event type: 'fight' or 'crowd' to identify collection",
    )


# Helper function to format Mongo Document
def serialize_event(doc):
    doc["_id"] = str(doc["_id"])
    doc["cameraId"] = str(doc.get("cameraId", ""))
    doc["userId"] = str(doc.get("userId", ""))
    doc["dvrId"] = str(doc.get("dvrId", ""))
    if isinstance(doc.get("createdAt"), datetime):
        doc["createdAt"] = doc["createdAt"].isoformat()
    if isinstance(doc.get("updatedAt"), datetime):
        doc["updatedAt"] = doc["updatedAt"].isoformat()
    return doc


# Helper function to get raw timestamp safely for sorting
def get_sort_key(doc):
    created = doc.get("createdAt")
    if isinstance(created, datetime):
        if created.tzinfo is None:
            return created.replace(tzinfo=timezone.utc)
        return created
    elif isinstance(created, str):
        try:
            return datetime.fromisoformat(created.replace("Z", "+00:00"))
        except Exception:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


# 📹 STREAM ENDPOINT 1: Crowd Detection Stream
@router.get("/video_feed/crowd", summary="Stream Crowd Surge Video Feed")
def video_feed_crowd(
    source: str = Query("f1.mp4", description="Video file path or RTSP URL"),
    camera_key: str = Query("OFIC_CH16", description="Camera Identification Key"),
):
    return StreamingResponse(
        detector_engine.generate_stream_frames(
            video_source=source, camera_key=camera_key
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# 📹 STREAM ENDPOINT 2: Fight Detection Stream
@router.get("/video_feed/fight", summary="Stream Fight/Violence Video Feed")
def video_feed_fight(
    source: str = Query("fi7.avi", description="Video file path or RTSP URL"),
    camera_key: str = Query("OFIC_CH14", description="Camera Identification Key"),
):
    return StreamingResponse(
        action_engine.detect_fight_and_stream(
            video_source=source, camera_key=camera_key
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# 📊 REALTIME FIGHT STATUS API
@router.get("/fight-status", summary="Get Live Fight Detection Status")
def get_fight_status(
    camera_key: Optional[str] = Query(
        None, description="Optional Camera Key"
    )
):
    if camera_key:
        return {
            "camera_key": camera_key,
            "is_fighting": action_engine.camera_fight_status.get(
                camera_key, False
            ),
        }

    return {
        "is_fighting": action_engine.is_fighting,
        "camera_details": action_engine.camera_fight_status,
    }


# 🚀 Dynamic 16 Camera List Endpoint for Frontend Grid
@router.get("/cameras", summary="Get List of All Registered Cameras")
def list_cameras():
    """Returns all camera mappings (1 to 16) for dynamic UI rendering."""
    try:
        cameras = get_all_cameras()
        return {
            "status": "success",
            "count": len(cameras),
            "cameras": cameras,
        }
    except Exception as e:
        logger.error(f"Error fetching cameras list: {e}")
        raise HTTPException(
            status_code=500, detail="Unable to fetch camera configuration"
        )


# 1. GET: Fight Events Only
@router.get("/alerts/fight", summary="Get Recent Fight Detection Events")
def get_fight_alerts(
    limit: int = Query(10, ge=1, le=100),
    camera_id: Optional[str] = Query(
        None, description="Filter by camera ObjectId string"
    ),
):
    try:
        if fight_collection is not None:
            query = {}
            if camera_id:
                try:
                    query["cameraId"] = ObjectId(camera_id)
                except Exception:
                    query["cameraId"] = camera_id

            events = list(
                fight_collection.find(query).sort("createdAt", -1).limit(limit)
            )
            return {
                "status": "success",
                "alerts": [serialize_event(e) for e in events],
            }
        return {"status": "success", "alerts": []}
    except Exception as e:
        logger.error(f"Error fetching fight alerts: {e}")
        raise HTTPException(
            status_code=500, detail="Unable to fetch fight events"
        )


# 2. GET: Crowd Events Only
@router.get("/alerts/crowd", summary="Get Recent Crowd Detection Events")
def get_crowd_alerts(
    limit: int = Query(10, ge=1, le=100),
    camera_id: Optional[str] = Query(
        None, description="Filter by camera ObjectId string"
    ),
):
    try:
        if crowd_collection is not None:
            query = {}
            if camera_id:
                try:
                    query["cameraId"] = ObjectId(camera_id)
                except Exception:
                    query["cameraId"] = camera_id

            events = list(
                crowd_collection.find(query).sort("createdAt", -1).limit(limit)
            )
            return {
                "status": "success",
                "alerts": [serialize_event(e) for e in events],
            }
        return {"status": "success", "alerts": []}
    except Exception as e:
        logger.error(f"Error fetching crowd alerts: {e}")
        raise HTTPException(
            status_code=500, detail="Unable to fetch crowd events"
        )


# 3. GET: All Alerts Combined
@router.get("/alerts", summary="Get All Detection Events Combined")
def get_all_alerts(limit: int = Query(10, ge=1, le=100)):
    try:
        fight_events = (
            list(
                fight_collection.find({})
                .sort("createdAt", -1)
                .limit(limit)
            )
            if fight_collection is not None
            else []
        )
        crowd_events = (
            list(
                crowd_collection.find({})
                .sort("createdAt", -1)
                .limit(limit)
            )
            if crowd_collection is not None
            else []
        )

        all_events = sorted(
            fight_events + crowd_events,
            key=get_sort_key,
            reverse=True,
        )[:limit]

        return {
            "status": "success",
            "alerts": [serialize_event(e) for e in all_events],
        }
    except Exception as e:
        logger.error(f"Error fetching all alerts: {e}")
        raise HTTPException(
            status_code=500, detail="Unable to fetch detection events"
        )


# 4. POST: Dynamic Threshold Update
@router.post("/settings/threshold", summary="Update Crowd Threshold Live")
def update_crowd_threshold(payload: ThresholdUpdateSchema):
    old_threshold = detector_engine.crowd_threshold
    detector_engine.crowd_threshold = payload.new_threshold

    logger.info(
        f"Crowd threshold updated from {old_threshold} to {payload.new_threshold}"
    )

    return {
        "status": "success",
        "message": f"Threshold updated to {payload.new_threshold}!",
        "current_threshold": detector_engine.crowd_threshold,
    }


# 5. PUT: Update Alert Status (isRead)
@router.put("/alerts/status", summary="Update Read/Unread Status of an Event")
def update_alert_status(payload: EventStatusSchema):
    try:
        obj_id = ObjectId(payload.event_id)
    except Exception:
        raise HTTPException(
            status_code=400, detail="Invalid MongoDB ObjectId format"
        )

    target_coll = (
        fight_collection
        if "fight" in payload.event_type.lower()
        else crowd_collection
    )
    if target_coll is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    result = target_coll.update_one(
        {"_id": obj_id},
        {
            "$set": {
                "isRead": payload.is_read,
                "updatedAt": datetime.now(timezone.utc),
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Event ID '{payload.event_id}' not found.",
        )

    return {
        "status": "success",
        "event_id": payload.event_id,
        "isRead": payload.is_read,
    }


# 6. DELETE: Remove Event Document
@router.delete("/alerts/{event_id}", summary="Delete Detection Event")
def delete_alert_image(event_id: str, event_type: str = "crowd"):
    try:
        obj_id = ObjectId(event_id)
    except Exception:
        raise HTTPException(
            status_code=400, detail="Invalid MongoDB ObjectId format"
        )

    if fight_collection is None or crowd_collection is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    primary_coll = (
        fight_collection
        if "fight" in event_type.lower()
        else crowd_collection
    )
    secondary_coll = (
        crowd_collection
        if "fight" in event_type.lower()
        else fight_collection
    )

    db_result = primary_coll.delete_one({"_id": obj_id})

    if db_result.deleted_count == 0:
        db_result = secondary_coll.delete_one({"_id": obj_id})

    if db_result.deleted_count > 0:
        return {
            "status": "success",
            "message": f"Event '{event_id}' deleted successfully.",
        }

    raise HTTPException(
        status_code=404, detail=f"Event '{event_id}' not found."
    )