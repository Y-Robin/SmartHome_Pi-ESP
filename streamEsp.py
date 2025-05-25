from flask import Blueprint, render_template, Response, redirect, url_for
import cv2
import time
import yaml
from pathlib import Path

# === Konfiguration laden ===
def load_config():
    with open(Path("config.yaml"), "r") as file:
        return yaml.safe_load(file)

streaming_blueprint = Blueprint('streaming', __name__, template_folder='templates')

# === Kamerakonfiguration aus YAML laden ===
config = load_config()
camera_devices = config.get("camera_devices", {})

if not camera_devices:
    raise ValueError("Keine Kameras unter 'camera_devices' in config.yaml gefunden.")

# === Standard-Route: leitet auf erste verfügbare Kamera um ===
@streaming_blueprint.route('/streamEsp')
def default_stream():
    if not camera_devices:
        return "Keine Kameras verfügbar", 404
    first_cam_id = next(iter(camera_devices))
    return redirect(url_for('streaming.streamEsp', cam_id=first_cam_id))

# === HTML-Ansicht für eine Kamera ===
@streaming_blueprint.route('/streamEsp/<cam_id>')
def streamEsp(cam_id):
    if cam_id not in camera_devices:
        return f"Kamera '{cam_id}' nicht gefunden.", 404
    return render_template(
        'streamEsp.html',
        cam_id=cam_id,
        cameras=camera_devices
    )

# === MJPEG-Stream für eine Kamera ===
@streaming_blueprint.route('/streamEspImg/<cam_id>')
def stream_img(cam_id):
    if cam_id not in camera_devices:
        return f"Kamera '{cam_id}' nicht in der Konfiguration.", 404

    cam_ip = camera_devices[cam_id]['ip']
    stream_url = f"http://{cam_ip}:81/stream"

    def generate():
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            yield b''
            return

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            _, jpeg = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            time.sleep(0.05)
        cap.release()

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
