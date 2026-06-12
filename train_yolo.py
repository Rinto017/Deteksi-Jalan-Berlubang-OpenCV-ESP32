from ultralytics import YOLO

model = YOLO("yolov8n.pt")

model.train(
    data="dataset_yolo/data.yaml",
    epochs=5,
    imgsz=640,
    batch=8,
    device="cpu"
)

print("Training YOLO selesai.")