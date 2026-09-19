import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from action_detector import action_engine
from database import (
    crowd_collection,
    fight_collection,
    get_all_cameras,
    get_camera_info,
)
from detector import detector_engine

logger = logging.getLogger("AI_Surveillance.APIRoutes")

router = APIRouter(
    prefix="/api/v1",
    tags=["Surveillance API"],
)


class ThresholdUpdateSchema(BaseModel):
    new_threshold: int = Field(
        ...,
        gt=0,
        description="New crowd detection threshold (must be > 0)",
    )


class EventStatusSchema(BaseModel):
    event_id: str = Field(..., description="MongoDB ObjectId string")
    is_read: bool = Field(..., description="Read or unread boolean status")
    event_type: str = Field(default="crowd", description="'crowd' or 'fight'")


def normalize_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def serialize_event(doc: dict) -> dict:
    data = dict(doc)
    if "_id" in data:
        data["_id"] = str(data["_id"])
    for field in ("cameraId", "userId", "dvrId"):
        if field in data and data[field] is not None:
            data[field] = str(data[field])
    for field in ("createdAt", "updatedAt"):
        if isinstance(data.get(field), datetime):
            data[field] = data[field].isoformat()
    return data


@router.get("/health", summary="API Health Check")
def api_health():
    return {
        "status": "online",
        "database": (
            "connected"
            if (crowd_collection is not None or fight_collection is not None)
            else "disconnected"
        ),
        "crowd_engine": getattr(detector_engine, "device", "cpu"),
        "fight_engine": getattr(action_engine, "device", "cpu"),
    }


@router.get("/cameras", summary="Get All Active Cameras Dynamically")
def list_cameras():
    try:
        cameras = get_all_cameras()
        return {
            "status": "success",
            "count": len(cameras),
            "cameras": cameras,
        }
    except Exception as e:
        logger.exception("[CAMERAS] Failed to load cameras: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Unable to load cameras from database",
        )


@router.get("/cameras/{camera_code}", summary="Get Single Camera Details")
def get_single_camera(camera_code: str):
    try:
        camera = get_camera_info(camera_code)
        if not camera:
            raise HTTPException(
                status_code=404,
                detail=f"Camera '{camera_code}' not found in database",
            )
        return {
            "status": "success",
            "camera": camera,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[CAMERAS] Failed to fetch camera %s: %s", camera_code, e)
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving camera {camera_code}",
        )


@router.get("/fight-status", summary="Get Live Fight Detection Status")
def get_fight_status(camera_key: Optional[str] = Query(default=None)):
    camera_status = getattr(action_engine, "camera_fight_status", {})
    if camera_key:
        return {
            "camera_key": camera_key,
            "is_fighting": camera_status.get(camera_key, False),
        }
    return {
        "is_fighting": getattr(action_engine, "is_fighting", False),
        "camera_details": camera_status,
    }


@router.get("/alerts/fight", summary="Get Fight Detection Alerts")
def get_fight_alerts(
    limit: int = Query(default=10, ge=1, le=100),
    camera_id: Optional[str] = Query(default=None),
):
    if fight_collection is None:
        return {"status": "success", "alerts": []}

    query = {}
    if camera_id:
        query["cameraId"] = ObjectId(camera_id) if ObjectId.is_valid(camera_id) else camera_id

    try:
        events = list(fight_collection.find(query).sort("createdAt", -1).limit(limit))
        return {
            "status": "success",
            "alerts": [serialize_event(event) for event in events],
        }
    except Exception as e:
        logger.exception("[FIGHT ALERTS] Error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to fetch fight alerts")


@router.get("/alerts/crowd", summary="Get Crowd Detection Alerts")
def get_crowd_alerts(
    limit: int = Query(default=10, ge=1, le=100),
    camera_id: Optional[str] = Query(default=None),
):
    if crowd_collection is None:
        return {"status": "success", "alerts": []}

    query = {}
    if camera_id:
        query["cameraId"] = ObjectId(camera_id) if ObjectId.is_valid(camera_id) else camera_id

    try:
        events = list(crowd_collection.find(query).sort("createdAt", -1).limit(limit))
        return {
            "status": "success",
            "alerts": [serialize_event(event) for event in events],
        }
    except Exception as e:
        logger.exception("[CROWD ALERTS] Error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to fetch crowd alerts")


@router.get("/alerts", summary="Get All Alerts Combined")
def get_all_alerts(limit: int = Query(default=20, ge=1, le=100)):
    try:
        fight_events = []
        if fight_collection is not None:
            fight_events = list(fight_collection.find({}).sort("createdAt", -1).limit(limit))

        crowd_events = []
        if crowd_collection is not None:
            crowd_events = list(crowd_collection.find({}).sort("createdAt", -1).limit(limit))

        all_events = fight_events + crowd_events
        all_events.sort(
            key=lambda event: normalize_datetime(event.get("createdAt")),
            reverse=True,
        )

        return {
            "status": "success",
            "alerts": [serialize_event(event) for event in all_events[:limit]],
        }
    except Exception as e:
        logger.exception("[ALL ALERTS] Error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to fetch alerts list")


@router.post("/settings/threshold", summary="Update Live Crowd Threshold")
def update_threshold(payload: ThresholdUpdateSchema):
    try:
        old_value = getattr(detector_engine, "crowd_threshold", None)
        detector_engine.crowd_threshold = payload.new_threshold
        logger.info("[THRESHOLD] Updated: %s -> %s", old_value, payload.new_threshold)
        return {
            "status": "success",
            "message": f"Threshold updated to {payload.new_threshold}",
            "old_threshold": old_value,
            "current_threshold": detector_engine.crowd_threshold,
        }
    except Exception as e:
        logger.exception("[THRESHOLD] Update error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to update threshold")


@router.put("/alerts/status", summary="Update Alert Read Status")
def update_alert_status(payload: EventStatusSchema):
    if not ObjectId.is_valid(payload.event_id):
        raise HTTPException(status_code=400, detail="Invalid MongoDB ObjectId format")

    event_id = ObjectId(payload.event_id)
    event_type = (payload.event_type or "crowd").lower()

    collection = fight_collection if "fight" in event_type else crowd_collection
    if collection is None:
        raise HTTPException(status_code=500, detail="Database collection is disconnected")

    try:
        result = collection.update_one(
            {"_id": event_id},
            {"$set": {"isRead": payload.is_read, "updatedAt": datetime.now(timezone.utc)}},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail=f"Event '{payload.event_id}' not found")

        return {
            "status": "success",
            "event_id": payload.event_id,
            "isRead": payload.is_read,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[UPDATE STATUS] Error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to update alert status")


@router.delete("/alerts/{event_id}", summary="Delete Detection Alert")
def delete_alert(
    event_id: str,
    event_type: str = Query(default="crowd", description="'crowd' or 'fight'"),
):
    if not ObjectId.is_valid(event_id):
        raise HTTPException(status_code=400, detail="Invalid MongoDB ObjectId format")

    obj_id = ObjectId(event_id)
    collections = (
        [fight_collection, crowd_collection]
        if "fight" in event_type.lower()
        else [crowd_collection, fight_collection]
    )

    try:
        for collection in collections:
            if collection is None:
                continue
            result = collection.delete_one({"_id": obj_id})
            if result.deleted_count > 0:
                logger.info("[DELETE] Event deleted: %s", event_id)
                return {
                    "status": "success",
                    "message": f"Event '{event_id}' deleted successfully",
                }
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[DELETE ALERT] Error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to delete alert")