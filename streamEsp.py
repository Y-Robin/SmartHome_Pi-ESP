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

def load_config():
    with open(Path("config.yaml"), "r") as file:
        return yaml.safe_load(file)

config = load_config()
camera_devices = config.get("camera_devices", {})
states = {}
shared_frames = {}


def init_state(cam_id):
    if cam_id not in states:
        states[cam_id] = {
            "recording": False,
            "landmarks": False,
            "lock": threading.Lock()
        }
    if cam_id not in shared_frames:
        shared_frames[cam_id] = {
            "frame": None,
            "lock": threading.Lock(),
            "recording": False,
            "buffer": [],
            "filename": None
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


def start_stream_thread(cam_id, source_type, cam_ip, port):
    def capture_loop():
        if source_type == "robot":
            snapshot_url = f"http://{cam_ip}/snapshot"
            while True:
                cap = cv2.VideoCapture(snapshot_url)
                ret, frame = cap.read()
                cap.release()
                if ret:
                    with shared_frames[cam_id]["lock"]:
                        shared_frames[cam_id]["frame"] = frame
                time.sleep(0.2)
        else:
            stream_url = f"http://{cam_ip}:{port}/stream"
            cap = cv2.VideoCapture(stream_url)
            while cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    with shared_frames[cam_id]["lock"]:
                        shared_frames[cam_id]["frame"] = frame.copy()
                        if states[cam_id]["landmarks"]:
                            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            keypoints = detect_landmarks(rgb)
                            draw_landmarks(frame, keypoints)
                        if states[cam_id]["recording"]:
                            if not shared_frames[cam_id]["recording"]:
                                shared_frames[cam_id]["recording"] = True
                                shared_frames[cam_id]["buffer"] = []
                                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                                shared_frames[cam_id]["filename"] = f"{cam_id}_{timestamp}"
                            shared_frames[cam_id]["buffer"].append(frame.copy())
                        elif shared_frames[cam_id]["recording"]:
                            shared_frames[cam_id]["recording"] = False
                            save_recording(cam_id)
                else:
                    time.sleep(0.1)
            cap.release()

    thread = threading.Thread(target=capture_loop, daemon=True)
    thread.start()


def save_recording(cam_id):
    frame_buffer = shared_frames[cam_id]["buffer"]
    filename = shared_frames[cam_id]["filename"]
    if frame_buffer and filename:
        avi_path = Path("static/videos") / f"{filename}.avi"
        mp4_path = Path("static/videos") / f"{filename}.mp4"
        avi_path.parent.mkdir(parents=True, exist_ok=True)
        h, w = frame_buffer[0].shape[:2]
        try:
            writer = cv2.VideoWriter(str(avi_path), cv2.VideoWriter_fourcc(*'MJPG'), 5, (w, h))
            for f in frame_buffer[:2000]:
                writer.write(f)
            writer.release()
            result = subprocess.run([
                "/usr/bin/ffmpeg",
                "-i", str(avi_path),
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-movflags", "+faststart",
                "-y", str(mp4_path)
            ], capture_output=True, text=True)
            if result.returncode == 0:
                avi_path.unlink()
        except Exception as e:
            print(f"[ERROR] Aufnahmefehler bei {cam_id}: {e}")


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
    cam_config = camera_devices[cam_id]
    cam_ip = cam_config['ip']
    source_type = cam_config.get("source", "esp")
    port = cam_config.get("port", 81)

    if shared_frames[cam_id]["frame"] is None:
        start_stream_thread(cam_id, source_type, cam_ip, port)

    def generate():
        while True:
            with shared_frames[cam_id]["lock"]:
                frame = shared_frames[cam_id]["frame"].copy() if shared_frames[cam_id]["frame"] is not None else None

            if frame is None:
                time.sleep(0.05)
                continue

            success, jpeg = cv2.imencode('.jpg', frame)
            if not success:
                continue
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            time.sleep(0.05)

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
