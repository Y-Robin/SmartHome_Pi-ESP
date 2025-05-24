import io
import os
import threading
import datetime

import numpy as np
import cv2
from flask import Blueprint, Response, render_template, request

import picamera
import tflite_runtime.interpreter as tflite
from typing import Optional, List

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
TFLITE_MODEL_PATH = os.path.join(os.path.dirname(__file__), "movenet_singlepose_lightning.tflite")
KEYPOINT_SCORE_THRES = 0.3
INPUT_SIZE = 192

interpreter = tflite.Interpreter(model_path=TFLITE_MODEL_PATH, num_threads=2)
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

_SKELETON_EDGES = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (0, 5), (0, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 6), (5, 11), (6, 12),
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)
]

camera_blueprint = Blueprint('camera', __name__, template_folder='templates')

latest_frame_jpeg: Optional[bytes] = None
recording = False
FRAMES_BUFFER: List[np.ndarray] = []
landmark_detection_enabled = False
lock = threading.Lock()

RECORD_FLAG_FILE = 'record_flag.txt'
VIDEOS_FOLDER = 'static/videos'
os.makedirs(VIDEOS_FOLDER, exist_ok=True)


def is_recording() -> bool:
    return os.path.exists(RECORD_FLAG_FILE)


def save_video(frames: List[np.ndarray], file_path: str, fps: int = 20):
    height, width, _ = frames[0].shape
    try:
        out = cv2.VideoWriter(file_path, cv2.VideoWriter_fourcc(*'X264'), fps, (width, height))
    except Exception:
        out = cv2.VideoWriter(file_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
    for frame in frames:
        out.write(frame)
    out.release()


def _movenet_detect_landmarks(rgb_img: np.ndarray) -> np.ndarray:
    img_resized = cv2.resize(rgb_img, (INPUT_SIZE, INPUT_SIZE))
    input_data = np.expand_dims(img_resized.astype(np.uint8), axis=0)
    interpreter.set_tensor(input_details[0]['index'], input_data)
    interpreter.invoke()
    keypoints_with_scores = interpreter.get_tensor(output_details[0]['index'])
    return keypoints_with_scores[0, 0]


def _draw_landmarks(frame_bgr: np.ndarray, keypoints: np.ndarray):
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


def camera_stream_thread():
    global latest_frame_jpeg, recording, FRAMES_BUFFER
    with picamera.PiCamera(resolution=(320, 240), framerate=20) as camera:
        stream = io.BytesIO()
        for _ in camera.capture_continuous(stream, format='jpeg', use_video_port=True):
            stream.seek(0)
            jpeg_data = stream.read()
            stream.seek(0)
            stream.truncate()

            img_bgr = cv2.imdecode(np.frombuffer(jpeg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

            with lock:
                if landmark_detection_enabled:
                    keypoints = _movenet_detect_landmarks(img_rgb)
                    _draw_landmarks(img_bgr, keypoints)

            ret, jpg_annotated = cv2.imencode('.jpg', img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ret:
                continue
            jpeg_data_annotated = jpg_annotated.tobytes()

            with lock:
                latest_frame_jpeg = jpeg_data_annotated

            if is_recording():
                if not recording:
                    FRAMES_BUFFER = []
                    recording = True
                FRAMES_BUFFER.append(img_bgr.copy())
            elif recording:
                recording = False
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"video_{timestamp}.mp4"
                filepath = os.path.join(VIDEOS_FOLDER, filename)
                save_video(FRAMES_BUFFER, filepath)
                FRAMES_BUFFER = []


threading.Thread(target=camera_stream_thread, daemon=True).start()


@camera_blueprint.route('/camera')
def camera_page():
    return render_template('camera.html')


@camera_blueprint.route('/stream')
def stream():
    def generate():
        while True:
            with lock:
                frame = latest_frame_jpeg
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    response = Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['Content-Type'] = 'multipart/x-mixed-replace; boundary=frame'
    return response


@camera_blueprint.route('/start_recording', methods=['POST'])
def start_recording():
    open(RECORD_FLAG_FILE, 'w').close()
    return '', 204


@camera_blueprint.route('/stop_recording', methods=['POST'])
def stop_recording():
    if os.path.exists(RECORD_FLAG_FILE):
        os.remove(RECORD_FLAG_FILE)
    return '', 204


@camera_blueprint.route('/recording_status')
def recording_status():
    return {'recording': is_recording()}


@camera_blueprint.route('/toggle_landmarks', methods=['POST'])
def toggle_landmarks():
    global landmark_detection_enabled
    with lock:
        landmark_detection_enabled = not landmark_detection_enabled
    return {"landmark_detection": landmark_detection_enabled}
