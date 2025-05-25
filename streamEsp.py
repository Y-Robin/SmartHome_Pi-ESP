from flask import Blueprint, render_template, Response, redirect, url_for, request, jsonify
import cv2
import time
import yaml
import datetime
from pathlib import Path
import threading
import numpy as np
import tflite_runtime.interpreter as tflite
import subprocess

streaming_blueprint = Blueprint('streaming', __name__, template_folder='templates')

# === MoveNet Setup ===
TFLITE_MODEL_PATH = "movenet_singlepose_lightning.tflite"
INPUT_SIZE = 192
KEYPOINT_SCORE_THRES = 0.3
_SKELETON_EDGES = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (0, 5), (0, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 6), (5, 11), (6, 12),
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)
]

interpreter = tflite.Interpreter(model_path=TFLITE_MODEL_PATH, num_threads=2)
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

# === Konfiguration laden ===
def load_config():
    with open(Path("config.yaml"), "r") as file:
        return yaml.safe_load(file)

config = load_config()
camera_devices = config.get("camera_devices", {})

states = {}

def init_state(cam_id):
    if cam_id not in states:
        states[cam_id] = {
            "recording": False,
            "landmarks": False,
            "writer": None,
            "lock": threading.Lock()
        }

def detect_landmarks(rgb_img):
    img_resized = cv2.resize(rgb_img, (INPUT_SIZE, INPUT_SIZE))
    input_data = np.expand_dims(img_resized.astype(np.uint8), axis=0)
    interpreter.set_tensor(input_details[0]['index'], input_data)
    interpreter.invoke()
    return interpreter.get_tensor(output_details[0]['index'])[0, 0]

def draw_landmarks(frame_bgr, keypoints):
    h, w, _ = frame_bgr.shape
    points = []
    for kp in keypoints:
        y, x, score = kp
        cx, cy = int(x * w), int(y * h)
        points.append((cx, cy, score))
        if score > KEYPOINT_SCORE_THRES:
            cv2.circle(frame_bgr, (cx, cy), 3, (0, 255, 0), -1)
    for i, j in _SKELETON_EDGES:
        if points[i][2] > KEYPOINT_SCORE_THRES and points[j][2] > KEYPOINT_SCORE_THRES:
            cv2.line(frame_bgr, points[i][:2], points[j][:2], (0, 255, 255), 1)

@streaming_blueprint.route('/streamEsp')
def default_stream():
    first_cam_id = next(iter(camera_devices))
    return redirect(url_for('streaming.streamEsp', cam_id=first_cam_id))

@streaming_blueprint.route('/streamEsp/<cam_id>')
def streamEsp(cam_id):
    return render_template('streamEsp.html', cam_id=cam_id, cameras=camera_devices)

@streaming_blueprint.route('/streamEspImg/<cam_id>')
def stream_img(cam_id):
    init_state(cam_id)
    cam_ip = camera_devices[cam_id]['ip']
    port = camera_devices[cam_id].get("port", 81)
    stream_url = f"http://{cam_ip}:{port}/stream"

    # Aufnahme-Kontext
    recording_active = False
    frame_buffer = []
    max_frames = 2000
    filename = None

    def generate():
        nonlocal recording_active, frame_buffer, filename

        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            print(f"[ERROR] Kamera {cam_id} nicht erreichbar: {stream_url}")
            yield b''
            return

        while True:
            ret, frame = cap.read()
            if not ret or frame is None or frame.size == 0:
                continue  # Frame überspringen

            # Pose-Detection (optional)
            if states[cam_id]["landmarks"]:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                keypoints = detect_landmarks(rgb)
                draw_landmarks(frame, keypoints)

            # === Aufnahme starten ===
            if states[cam_id]["recording"]:
                if not recording_active:
                    print(f"[INFO] Starte Aufnahme für {cam_id}")
                    recording_active = True
                    frame_buffer = []
                    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"{cam_id}_{timestamp}.mp4"
                frame_buffer.append(frame.copy())

            # === Aufnahme stoppen und speichern ===
            elif recording_active:
                print(f"[INFO] Stoppe Aufnahme für {cam_id}")
                recording_active = False
                if frame_buffer:
                    out_path = Path("static/videos") / filename
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    h, w = frame.shape[:2]

                    try:
                        # Datei schreiben
                        writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*'mp4v'), 20, (w, h))
                        for f in frame_buffer[:max_frames]:
                            writer.write(f)
                        writer.release()
                        print(f"[OK] Video gespeichert: {out_path}")

                        # === ffmpeg: optimieren für Browser ===
                        fixed_path = out_path.with_name("fixed_" + out_path.name)
                        result = subprocess.run([
                            "ffmpeg", "-i", str(out_path),
                            "-movflags", "+faststart",
                            "-c", "copy",
                            "-y",
                            str(fixed_path)
                        ], capture_output=True, text=True)

                        if result.returncode != 0:
                            print(f"[FFMPEG ERROR] {result.stderr}")
                        else:
                            out_path.unlink()
                            fixed_path.rename(out_path)
                            print(f"[OK] Web-optimiertes Video: {out_path.name}")

                    except Exception as e:
                        print(f"[ERROR] Fehler beim Speichern oder Konvertieren: {e}")

                frame_buffer = []

            # === MJPEG-Ausgabe ===
            success, jpeg = cv2.imencode('.jpg', frame)
            if not success:
                continue
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            time.sleep(0.05)

        cap.release()

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@streaming_blueprint.route('/start_recording/<cam_id>', methods=['POST'])
def start_recording(cam_id):
    init_state(cam_id)
    states[cam_id]["recording"] = True
    return '', 204

@streaming_blueprint.route('/stop_recording/<cam_id>', methods=['POST'])
def stop_recording(cam_id):
    init_state(cam_id)
    states[cam_id]["recording"] = False
    return '', 204

@streaming_blueprint.route('/toggle_landmarks/<cam_id>', methods=['POST'])
def toggle_landmarks(cam_id):
    init_state(cam_id)
    states[cam_id]["landmarks"] = not states[cam_id]["landmarks"]
    return jsonify({"landmarks_enabled": states[cam_id]["landmarks"]})

@streaming_blueprint.route('/recording_status/<cam_id>')
def recording_status(cam_id):
    init_state(cam_id)
    return jsonify({'recording': states[cam_id]["recording"]})
