import cv2
import torch
from ultralytics import YOLO
import time
import os

# Create directory for saving alert snapshots
os.makedirs("alerts", exist_ok=True)

# 1. Device Setup for RTX 4060 Ti
device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
print(f"==================================================")
print(f"[INFO] Initializing Detection System on: {device}")
if torch.cuda.is_available():
    print(f"[INFO] Active GPU: {torch.cuda.get_device_name(0)}")
print(f"==================================================")

# 2. Load Lightweight YOLOv8 Model
#model = YOLO("yolov8n.pt")  # Auto-downloads pretrained weights on first run
# Ab Medium model ke liye:
@st.cache_resource
def load_yolo():
    return YOLO("yolov8m.pt")
# 3. Input Video Source 
# (Replace with 0 for WebCam, or path to a local video file like 'sample.mp4')
video_source = "f1.mp4"
cap = cv2.VideoCapture(video_source)

# Parameters
CROWD_THRESHOLD = 8  # Crowd warning limit
frame_count = 0
prev_time = time.time()

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("[INFO] Video Stream Ended or Source Unavailable.")
        break
    
    frame_count += 1
    
    # Run YOLOv8 on NVIDIA GPU (device=0)
    # Filter class 0 = Person only
    results = model(frame, device=0, classes=[0], verbose=False)
    
    # Calculate Persons Detected
    person_boxes = results[0].boxes
    person_count = len(person_boxes)
    
    # Get Frame with Bounding Boxes
    annotated_frame = results[0].plot()
    
    # Calculate FPS (Frames Per Second) to verify GPU performance
    curr_time = time.time()
    fps = 1 / (curr_time - prev_time)
    prev_time = curr_time
    
    # Crowd Logic
    if person_count >= CROWD_THRESHOLD:
        status_text = f"ALERT: CROWD SURGE ({person_count} People)"
        color = (0, 0, 255) # Red Color (BGR)
    else:
        status_text = f"Status: Normal ({person_count} People)"
        color = (0, 255, 0) # Green Color (BGR)
        
    # Overlay Info on Screen
    cv2.putText(annotated_frame, status_text, (20, 40), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
    cv2.putText(annotated_frame, f"FPS: {int(fps)} | GPU: RTX 4060 Ti", (20, 80), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    
    # Save Snapshot if Crowd Exceeds Threshold
    if person_count >= CROWD_THRESHOLD and frame_count % 30 == 0:
        snapshot_filename = f"alerts/crowd_{int(time.time())}.jpg"
        cv2.imwrite(snapshot_filename, annotated_frame)
        print(f"⚠️ [ALERT SAVED] Snapshot: {snapshot_filename}")

    # Render Display Output
    cv2.imshow("Crowd Safety System (NVIDIA Accelerated)", annotated_frame)
    
    # Press 'q' to Exit
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()