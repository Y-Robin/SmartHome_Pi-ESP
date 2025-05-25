from flask import Blueprint, render_template, Response, redirect, url_for, request, jsonify
import cv2
import time
import yaml
import datetime
from pathlib import Path
import threading
import numpy as np

streaming_blueprint = Blueprint('streaming', __name__, template_folder='templates')

def load_config():
    with open(Path("config.yaml"), "r") as file:
        return yaml.safe_load(file)

config = load_config()
camera_devices = config.get("camera_devices", {})

recording_flags = {}
motion_detection_flags = {}
recording_writers = {}
recording_locks = {}
last_frames = {}

@streaming_blueprint.route('/streamEsp')
def default_stream():
    first_cam_id = next(iter(camera_devices))
    return redirect(url_for('streaming.streamEsp', cam_id=first_cam_id))

@streaming_blueprint.route('/streamEsp/<cam_id>')
def streamEsp(cam_id):
    return render_template('streamEsp.html', cam_id=cam_id, cameras=camera_devices)

@streaming_blueprint.route('/streamEspImg/<cam_id>')
def stream_img(cam_id):
    cam_ip = camera_devices[cam_id]['ip']
    port = camera_devices[cam_id].get("port", 81)
    stream_url = f"http://{cam_ip}:{port}/stream"

    recording_flags.setdefault(cam_id, False)
    motion_detection_flags.setdefault(cam_id, False)
    recording_writers[cam_id] = None
    recording_locks[cam_id] = threading.Lock()
    last_frames[cam_id] = None

    def generate():
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            yield b''
            return

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (21, 21), 0)

            motion = False
            if motion_detection_flags[cam_id]:
                prev = last_frames[cam_id]
                if prev is not None:
                    delta = cv2.absdiff(prev, blurred)
                    thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
                    motion = cv2.countNonZero(thresh) > 5000  # Schwelle
                last_frames[cam_id] = blurred

            should_record = recording_flags[cam_id] or motion

            if should_record:
                with recording_locks[cam_id]:
                    if recording_writers[cam_id] is None:
                        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"{cam_id}_{timestamp}.mp4"
                        path = Path("static/videos") / filename
                        path.parent.mkdir(exist_ok=True)
                        h, w = frame.shape[:2]
                        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 20, (w, h))
                        recording_writers[cam_id] = writer
                    recording_writers[cam_id].write(frame)

            elif recording_writers[cam_id] is not None:
                with recording_locks[cam_id]:
                    recording_writers[cam_id].release()
                    recording_writers[cam_id] = None

            _, jpeg = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            time.sleep(0.05)

        cap.release()

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@streaming_blueprint.route('/start_recording/<cam_id>', methods=['POST'])
def start_recording(cam_id):
    recording_flags[cam_id] = True
    return '', 204

@streaming_blueprint.route('/stop_recording/<cam_id>', methods=['POST'])
def stop_recording(cam_id):
    recording_flags[cam_id] = False
    return '', 204

@streaming_blueprint.route('/recording_status/<cam_id>')
def recording_status(cam_id):
    return jsonify({'recording': recording_flags.get(cam_id, False)})

@streaming_blueprint.route('/toggle_motion/<cam_id>', methods=['POST'])
def toggle_motion(cam_id):
    motion_detection_flags[cam_id] = not motion_detection_flags.get(cam_id, False)
    return jsonify({'motion_enabled': motion_detection_flags[cam_id]})
