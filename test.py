from ultralytics import YOLO

model = YOLO("fight_model.pt")
print("Model Classes:", model.names)