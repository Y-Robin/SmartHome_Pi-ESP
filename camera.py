from flask import Blueprint, render_template, send_file

import os

RECORD_FLAG_FILE = 'record_flag.txt'


shared_file = 'shared_frame.jpg'
camera_blueprint = Blueprint('camera', __name__)

@camera_blueprint.route('/camera')
def camera_page():
    return render_template('camera.html')

@camera_blueprint.route('/stream')
def stream():
    return send_file(shared_file, mimetype='image/jpeg')


@camera_blueprint.route('/start_recording', methods=['POST'])
def start_recording():
    print("hier")
    open(RECORD_FLAG_FILE, 'w').close()  # Create an empty file as a flag
    return '', 204

@camera_blueprint.route('/stop_recording', methods=['POST'])
def stop_recording():
    if os.path.exists(RECORD_FLAG_FILE):
        os.remove(RECORD_FLAG_FILE)  # Remove the flag file
    return '', 204

@camera_blueprint.route('/recording_status')
def recording_status():
    if os.path.exists(RECORD_FLAG_FILE):
        return {'recording': True}
    else:
        return {'recording': False}

# Add other camera-related routes here

