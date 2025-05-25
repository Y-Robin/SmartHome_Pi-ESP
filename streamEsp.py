from flask import Blueprint, render_template, Response, redirect, url_for, request, jsonify
import cv2
import time
import yaml
import datetime
from pathlib import Path
import threading
import numpy as np
import tflite_runtime.interpreter as tflite

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

    def generate():
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            print(f"[ERROR] Stream {cam_id} nicht erreichbar.")
            yield b''
            return

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if states[cam_id]["landmarks"]:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                keypoints = detect_landmarks(rgb)
                draw_landmarks(frame, keypoints)

            if states[cam_id]["recording"]:
                with states[cam_id]["lock"]:
                    if states[cam_id]["writer"] is None:
                        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"{cam_id}_{timestamp}.mp4"
                        out_path = Path("static/videos") / filename
                        out_path.parent.mkdir(exist_ok=True)
                        h, w = frame.shape[:2]
                        writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*'mp4v'), 20, (w, h))
                        states[cam_id]["writer"] = writer
                    states[cam_id]["writer"].write(frame)
            else:
                if states[cam_id]["writer"] is not None:
                    with states[cam_id]["lock"]:
                        states[cam_id]["writer"].release()
                        states[cam_id]["writer"] = None

            _, jpeg = cv2.imencode('.jpg', frame)
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
