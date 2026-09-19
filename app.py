import logging
import os
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from action_detector import action_engine
from api_routes import router as api_router
from database import get_camera_info
from detector import detector_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("surveillance.log"),
    ],
)
logger = logging.getLogger("AI_Surveillance.Main")

os.makedirs("alerts", exist_ok=True)

app = FastAPI(
    title="Enterprise AI Surveillance API",
    version="2.0.0",
    description="Multi-camera dynamic surveillance system powered by YOLOv8, OpenCV, and MongoDB.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/alerts",
    StaticFiles(directory="alerts"),
    name="alerts",
)

app.include_router(api_router)


@app.get("/api/v1/stream/crowd", tags=["Streams"])
def crowd_stream(camera_code: str = Query(...)):
    camera = get_camera_info(camera_code)
    if not camera:
        raise HTTPException(
            status_code=404,
            detail=f"Camera '{camera_code}' not found in database",
        )

    source = camera.get("rtspUrl")
    if not source:
        raise HTTPException(
            status_code=400,
            detail=f"Camera '{camera_code}' has no configured rtspUrl",
        )

    logger.info(f"[CROWD STREAM START] {camera_code} -> {source}")
    return StreamingResponse(
        detector_engine.generate_stream_frames(
            video_source=source,
            camera_key=camera_code,
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/v1/stream/fight", tags=["Streams"])
def fight_stream(camera_code: str = Query(...)):
    camera = get_camera_info(camera_code)
    if not camera:
        raise HTTPException(
            status_code=404,
            detail=f"Camera '{camera_code}' not found in database",
        )

    source = camera.get("rtspUrl")
    if not source:
        raise HTTPException(
            status_code=400,
            detail=f"Camera '{camera_code}' has no configured rtspUrl",
        )

    logger.info(f"[FIGHT STREAM START] {camera_code} -> {source}")
    return StreamingResponse(
        action_engine.detect_fight_and_stream(
            video_source=source,
            camera_key=camera_code,
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dynamic AI CCTV Multi-Camera Surveillance</title>
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            padding: 16px;
            background: #0d1117;
            color: #c9d1d9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        .header-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 12px;
            border-bottom: 1px solid #21262d;
            margin-bottom: 16px;
        }
        .header-bar h2 { margin: 0; color: #58a6ff; }
        .counter-badge {
            background: #1f6feb;
            color: #ffffff;
            font-size: 13px;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: bold;
        }
        .controls-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 10px 16px;
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        input[type="number"] {
            width: 75px;
            padding: 6px 10px;
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #ffffff;
        }
        button {
            background: #238636;
            color: white;
            border: none;
            padding: 7px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
        }
        button:hover { background: #2ea043; }
        .swagger-link { margin-left: auto; color: #58a6ff; text-decoration: none; }
        #cameraGrid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }
        .cam-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
        .cam-card-header {
            padding: 8px 12px;
            background: #1c2128;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .cam-video-box { width: 100%; height: 220px; background: #000; }
        .cam-video-box img { width: 100%; height: 100%; object-fit: cover; }
        .stream-offline {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: #8b949e;
        }
        .alerts-section {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 16px;
        }
        #alertsContainer { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px; }
        .alert-item {
            min-width: 190px;
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 8px;
            flex-shrink: 0;
        }
        .alert-item img { width: 100%; height: 110px; object-fit: cover; border-radius: 4px; }
    </style>
</head>
<body>

<div class="header-bar">
    <h2>🛡️ Multi-Camera Surveillance Wall</h2>
    <span id="camTotalBadge" class="counter-badge">Loading...</span>
</div>

<div class="controls-card">
    <label for="thresholdInput">Alert Threshold:</label>
    <input id="thresholdInput" type="number" min="1" value="5">
    <button onclick="updateThreshold()">Save Threshold</button>
    <button onclick="loadCamerasGrid()">🔄 Reload Grid</button>
    <a class="swagger-link" href="/docs" target="_blank">Swagger API &rarr;</a>
</div>

<div id="cameraGrid">
    <div style="grid-column: 1/-1; text-align: center; color: #8b949e;">Fetching registered cameras...</div>
</div>

<div class="alerts-section">
    <h3>🚨 Detection Alerts</h3>
    <div id="alertsContainer">
        <span style="color: #8b949e; font-size: 13px;">No alerts yet.</span>
    </div>
</div>

<script>
async function loadCamerasGrid() {
    const grid = document.getElementById("cameraGrid");
    const badge = document.getElementById("camTotalBadge");

    try {
        const response = await fetch("/api/v1/cameras");
        if (!response.ok) throw new Error("API returned " + response.status);

        const result = await response.json();
        const cameras = result.cameras || [];
        badge.innerText = cameras.length + " Cameras Online";

        if (cameras.length === 0) {
            grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color:#8b949e;">No active cameras found.</div>';
            return;
        }

        grid.innerHTML = "";
        cameras.forEach(cam => {
            const mode = (cam.mode === "fight") ? "fight" : "crowd";
            const code = cam.code || cam.camera_code || cam._id;
            const streamUrl = `/api/v1/stream/${mode}?camera_code=${encodeURIComponent(code)}`;

            const card = document.createElement("div");
            card.className = "cam-card";
            card.innerHTML = `
                <div class="cam-card-header">
                    <span>📷 ${cam.name || code}</span>
                    <span style="color:#58a6ff; font-size:11px; font-weight:bold;">${mode.toUpperCase()}</span>
                </div>
                <div class="cam-video-box">
                    <img 
                        src="${streamUrl}" 
                        alt="${code}"
                        onerror="this.parentElement.innerHTML='<div class=\\'stream-offline\\'>No RTSP Signal (${code})</div>';"
                    >
                </div>
            `;
            grid.appendChild(card);
        });
    } catch (err) {
        grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color:#f85149;">Failed to load cameras. Check backend.</div>';
        badge.innerText = "Error";
    }
}

async function loadAlerts() {
    const container = document.getElementById("alertsContainer");
    try {
        const res = await fetch("/api/v1/alerts?limit=15");
        if (!res.ok) return;
        const data = await res.json();
        const alerts = data.alerts || [];

        if (alerts.length === 0) {
            container.innerHTML = '<span style="color: #8b949e; font-size: 13px;">No alerts yet.</span>';
            return;
        }

        container.innerHTML = "";
        alerts.forEach(item => {
            const div = document.createElement("div");
            div.className = "alert-item";
            div.innerHTML = `
                ${item.image ? `<img src="${item.image}" alt="Alert Screenshot">` : ""}
                <b style="color:#f85149; font-size:12px;">${item.eventType || "Detection"}</b>
                <small style="display:block; color:#8b949e; font-size:11px;">${item.cameraId || "Camera"}</small>
            `;
            container.appendChild(div);
        });
    } catch(e) {
        console.error("Alerts fetching failed:", e);
    }
}

async function updateThreshold() {
    const val = Number(document.getElementById("thresholdInput").value);
    if (val < 1) return alert("Threshold must be at least 1");
    try {
        const res = await fetch("/api/v1/settings/threshold", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ new_threshold: val })
        });
        const json = await res.json();
        alert(json.message || "Threshold updated!");
    } catch (e) {
        alert("Failed to update threshold");
    }
}

loadCamerasGrid();
loadAlerts();
setInterval(loadAlerts, 5000);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    logger.info("Starting AI Surveillance Dynamic Server on port 8000...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
    )