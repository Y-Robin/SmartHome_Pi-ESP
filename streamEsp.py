from flask import Blueprint, render_template, Response
import cv2
import threading
import time
import yaml
from pathlib import Path

def load_config():
    with open(Path("config.yaml"), "r") as file:
        return yaml.safe_load(file)

streaming_blueprint = Blueprint('streaming', __name__, template_folder='templates')

config = load_config()
camera_devices = config.get("camera_devices", {})

if not camera_devices:
    raise ValueError("Keine Kamera in config.yaml unter 'camera_devices' gefunden.")

# Erste Kamera-IP extrahieren (oder erweitern auf mehrere bei Bedarf)
cam_info = next(iter(camera_devices.values()))
stream_url = f"http://{cam_info['ip']}:81/stream"
latest_frame = None
lock = threading.Lock()

def capture_frames():
    global latest_frame
    while True:
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            print("ESP32 nicht erreichbar – versuche erneut...")
            time.sleep(5)
            continue

        print("Verbunden mit ESP32.")
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Frame fehlgeschlagen, Verbindung neu...")
                cap.release()
                break

            _, jpeg = cv2.imencode('.jpg', frame)
            with lock:
                latest_frame = jpeg.tobytes()
            time.sleep(0.05)

# Starte Thread beim Import
capture_thread = threading.Thread(target=capture_frames, daemon=True)
capture_thread.start()

@streaming_blueprint.route('/streamEsp')
def streamEsp():
    return render_template('streamEsp.html')

@streaming_blueprint.route('/streamEspImg')
def stream():
    def generate():
        while True:
            with lock:
                frame = latest_frame
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.05)
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
