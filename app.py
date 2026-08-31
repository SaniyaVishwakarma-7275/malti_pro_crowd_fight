import logging
import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# Database Functions
from database import get_camera_info, get_all_cameras

# Detection Engines & API Router
from action_detector import action_engine
from api_routes import router as api_router
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
    description="Multi-stream AI Surveillance System supporting YOLOv8 Crowd & Action Detection with full REST APIs.",
)

# Enable CORS for external access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/alerts", StaticFiles(directory="alerts"), name="alerts")
app.include_router(api_router)


@app.get("/api/v1/fight-status", tags=["Live Status"])
def get_fight_status():
    is_fighting = getattr(action_engine, "is_fighting", False)
    return {"is_fighting": is_fighting}


@app.get("/alarm.wav", include_in_schema=False)
def get_alarm_sound():
    if os.path.exists("alarm.wav"):
        return FileResponse("alarm.wav", media_type="audio/wav")
    raise HTTPException(status_code=404, detail="alarm.wav file not found")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index():
    logger.info("Dashboard requested by client.")
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Enterprise AI Multi-Camera Surveillance System</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0b0e14; color: #fff; text-align: center; padding: 20px; margin: 0; }
            .grid-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 15px; margin-top: 20px; padding: 10px; }
            .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
            img.stream { border-radius: 8px; border: 2px solid #21262d; width: 100%; height: 240px; object-fit: cover; background-color: #000; }
            h3 { margin-bottom: 8px; color: #58a6ff; font-size: 14px; text-transform: uppercase; }
            
            .control-panel { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 15px; margin: 10px auto; max-width: 1200px; display: flex; justify-content: space-around; align-items: center; flex-wrap: wrap; gap: 10px; }
            input[type="number"], input[type="text"] { padding: 8px; border-radius: 6px; border: 1px solid #30363d; background: #0d1117; color: #fff; text-align: center; }
            button { background: #238636; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: bold; }
            button:hover { background: #2ea043; }
            .btn-delete { background: #da3633; color: white; border: none; padding: 4px 8px; font-size: 11px; margin-top: 5px; border-radius: 4px; cursor: pointer; }
            .btn-delete:hover { background: #f85149; }

            .gallery-section { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; width: 100%; margin-top: 20px; box-sizing: border-box; }
            .gallery-grid { display: flex; gap: 15px; overflow-x: auto; padding: 10px 0; }
            .alert-card { background: #0d1117; border: 1px solid #21262d; border-radius: 8px; padding: 8px; flex: 0 0 auto; text-align: center; }
            .alert-card img { width: 180px; height: 110px; border-radius: 6px; object-fit: cover; cursor: pointer; }
            .alert-card p { font-size: 11px; margin: 5px 0 0 0; color: #8b949e; word-break: break-all; width: 180px; }
            .alert-type { font-weight: bold; color: #f85149; text-transform: uppercase; font-size: 10px; }
            .cam-badge { background: #1f6beb; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-left: 5px; }
        </style>
    </head>
    <body>
        <h2>🛡️ Enterprise Multi-Camera AI Surveillance System</h2>
        <p>Engine: <b>FastAPI REST Architecture + OpenCV + YOLOv8 + MongoDB</b></p>
        
        <div class="control-panel">
            <div>
                <span>⚙️ <b>Live Crowd Threshold:</b> </span>
                <input type="number" id="thresholdInput" value="5" min="1">
                <button onclick="updateThreshold()">POST Update Threshold</button>
            </div>
            <div>
                <button onclick="loadCamerasGrid()">🔄 Reload Camera Streams</button>
            </div>
            <div>
                <a href="/docs" target="_blank" style="color: #58a6ff; text-decoration: none; font-weight: bold;">📑 Open Swagger API Docs</a>
            </div>
        </div>

        <!-- Dynamic Multi-Camera Live Stream Grid -->
        <div class="grid-container" id="cameraGrid">
            <p style="color: #8b949e; grid-column: 1/-1;">Fetching active cameras from database...</p>
        </div>

        <div style="max-width: 1220px; margin: 20px auto;">
            <div class="gallery-section">
                <h3>🚨 Captured Alerts Gallery (MongoDB Base64)</h3>
                <div id="gallery" class="gallery-grid">
                    <p style="color: #8b949e;">Loading alerts...</p>
                </div>
            </div>
        </div>

        <script>
            let audioCtx = null;
            let lastAudioTime = 0;

            document.addEventListener('click', () => {
                if (!audioCtx) {
                    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                }
                if (audioCtx.state === 'suspended') {
                    audioCtx.resume();
                }
            }, { once: true });

            function playBrowserBeep() {
                if (!audioCtx) return;
                const oscillator = audioCtx.createOscillator();
                const gainNode = audioCtx.createGain();

                oscillator.type = 'square';
                oscillator.frequency.setValueAtTime(1500, audioCtx.currentTime);
                gainNode.gain.setValueAtTime(0.5, audioCtx.currentTime); 

                oscillator.connect(gainNode);
                gainNode.connect(audioCtx.destination);

                oscillator.start();
                setTimeout(() => { oscillator.stop(); }, 500);
            }

            // Dynamic Camera Fetch & Grid Generator
            async function loadCamerasGrid() {
                const grid = document.getElementById('cameraGrid');
                try {
                    const res = await fetch('/api/v1/cameras');
                    const data = await res.json();
                    
                    if (!data.cameras || data.cameras.length === 0) {
                        grid.innerHTML = '<p style="color: #8b949e; grid-column: 1/-1;">No cameras registered in Database.</p>';
                        return;
                    }

                    grid.innerHTML = '';
                    data.cameras.forEach(cam => {
                        const card = document.createElement('div');
                        card.className = 'card';
                        
                        // Action/Fight cameras vs Crowd cameras selection
                        const streamType = cam.mode === 'fight' ? 'fight' : 'crowd';
                        const streamUrl = `/api/v1/stream/${streamType}?camera_code=${cam.code}`;

                        card.innerHTML = `
                            <h3>📷 ${cam.name || cam.code} <span class="cam-badge">${streamType}</span></h3>
                            <img class="stream" src="${streamUrl}" alt="${cam.code} Stream" onerror="this.src='https://via.placeholder.com/360x240/161b22/8b949e?text=Camera+Offline'">
                        `;
                        grid.appendChild(card);
                    });
                } catch (e) {
                    console.error("Error loading cameras:", e);
                    grid.innerHTML = '<p style="color: #f85149; grid-column: 1/-1;">Error fetching camera list from API.</p>';
                }
            }

            async function checkLiveFightStatus() {
                try {
                    const res = await fetch('/api/v1/fight-status');
                    const data = await res.json();
                    
                    if (data.is_fighting === true) {
                        const now = Date.now();
                        if (now - lastAudioTime > 2000) {
                            playBrowserBeep();
                            lastAudioTime = now;
                        }
                    }
                } catch (e) {
                    console.error("Error checking fight status:", e);
                }
            }

            setInterval(checkLiveFightStatus, 800);

            async function fetchAlerts() {
                try {
                    const response = await fetch('/api/v1/alerts');
                    const data = await response.json();
                    const gallery = document.getElementById('gallery');
                    
                    if (!data.alerts || data.alerts.length === 0) {
                        gallery.innerHTML = '<p style="color: #8b949e; width: 100%;">No critical alerts recorded yet in MongoDB.</p>';
                        return;
                    }

                    gallery.innerHTML = '';
                    data.alerts.forEach(item => {
                        const card = document.createElement('div');
                        card.className = 'alert-card';

                        const isObject = typeof item === 'object' && item !== null;
                        const imageSrc = isObject ? (item.image || `/alerts/${item.filename}`) : `/alerts/${item}`;
                        const eventId = isObject ? item._id : item;
                        const eventType = isObject ? (item.eventType || 'Alert') : 'Alert';
                        const confidence = isObject ? (item.confidence ? (item.confidence * 100).toFixed(0) + '%' : 'N/A') : '';

                        card.innerHTML = `
                            <a href="${imageSrc}" target="_blank">
                                <img src="${imageSrc}" alt="Alert Screenshot">
                            </a>
                            <p class="alert-type">${eventType} ${confidence ? '(' + confidence + ')' : ''}</p>
                            <button class="btn-delete" onclick="deleteAlert('${eventId}')">DELETE</button>
                        `;
                        gallery.appendChild(card);
                    });
                } catch (err) {
                    console.error("Error fetching alerts:", err);
                }
            }

            async function updateThreshold() {
                const val = document.getElementById('thresholdInput').value;
                const res = await fetch('/api/v1/settings/threshold', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ new_threshold: parseInt(val) })
                });
                const data = await res.json();
                alert(data.message);
            }

            async function deleteAlert(eventId) {
                if(!confirm(`Delete event?`)) return;
                const res = await fetch(`/api/v1/alerts/${eventId}`, { method: 'DELETE' });
                await res.json();
                fetchAlerts();
            }

            // Initialization
            loadCamerasGrid();
            setInterval(fetchAlerts, 5000);
            fetchAlerts();
        </script>
    </body>
    </html>
    """


# Streaming Endpoint for Crowd Cameras
# @app.get("/api/v1/stream/crowd", tags=["Streams"])
# def crowd_video_feed(
#     camera_code: str = Query(default="OFIC_CH01"),
#     rtsp_url: Optional[str] = Query(default=None)
# ):
#     if rtsp_url:
#         source = rtsp_url
#     else:
#         camera = get_camera_info(camera_code)
#         if not camera or "rtsp_url" not in camera:
#             source = "f1.mp4"  # Default fallback video
#         else:
#             source = camera["rtsp_url"]

#     return StreamingResponse(
#         detector_engine.generate_stream_frames(
#             video_source=source,
#             camera_key=camera_code,
#         ),
#         media_type="multipart/x-mixed-replace; boundary=frame",
#     )
@app.get("/api/v1/stream/crowd", tags=["Streams"])
def crowd_video_feed():

    source = "rtsp://admin:Msspl@1234@192.168.1.249:2001/video/live?channel=1&subtype=0"

    return StreamingResponse(
            detector_engine.generate_stream_frames(
            video_source=source,
            camera_key="OFIC_CH01",
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# Streaming Endpoint for Action / Fight Cameras
@app.get("/api/v1/stream/fight", tags=["Streams"])
def fight_video_feed(
    camera_code: str = Query(default="OFIC_CH13"),
    rtsp_url: Optional[str] = Query(default=None)
):
    if rtsp_url:
        source = rtsp_url
    else:
        camera = get_camera_info(camera_code)
        if not camera or "rtsp_url" not in camera:
            source = "fi7.avi"  # Default fallback video
        else:
            source = camera["rtsp_url"]

    return StreamingResponse(
        action_engine.detect_fight_and_stream(
            video_source=source,
            camera_key=camera_code
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/v1/health", tags=["Health Check"])
def health_check():
    return {
        "status": "online",
        "crowd_engine_device": getattr(detector_engine, "device", "cpu"),
        "action_engine_device": getattr(action_engine, "device", "cpu"),
    }


if __name__ == "__main__":
    logger.info("Starting Enterprise AI Surveillance Server on Port 8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)