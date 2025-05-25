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

@streaming_blueprint.route('/streamEspImg/<cam_id>')
def stream_img(cam_id):
    if cam_id not in camera_devices:
        return f"Kamera '{cam_id}' nicht in der Konfiguration.", 404

    cam_config = camera_devices[cam_id]
    cam_ip = cam_config['ip']
    source = cam_config.get('source', 'esp')  # Standard ist ESP32

    if source == 'robot':
        # Roboter liefert Snapshots → simuliere MJPEG-Stream
        def generate_snapshots():
            while True:
                img_url = f"http://{cam_ip}/snapshot"
                cap = cv2.VideoCapture(img_url)
                ret, frame = cap.read()
                cap.release()
                if not ret:
                    continue
                _, jpeg = cv2.imencode('.jpg', frame)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
                time.sleep(0.2)

        return Response(generate_snapshots(), mimetype='multipart/x-mixed-replace; boundary=frame')

    else:
        # ESP32-CAM MJPEG-Stream
        port = cam_config.get("port", 81)
        stream_url = f"http://{cam_ip}:{port}/stream"

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

