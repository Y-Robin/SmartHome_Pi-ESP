from flask import Blueprint, render_template, send_file
import os

VIDEOS_FOLDER = 'videos'

videoLib_blueprint = Blueprint('videoLib', __name__)

@videoLib_blueprint.route('/videoLib')
def list_videos():
    video_files = [f for f in os.listdir(os.path.join('static', VIDEOS_FOLDER)) if f.endswith('.mp4')]
    video_files.sort(reverse=True)  # Sort in descending order; change to `False` for ascending order
    return render_template('videos.html', video_files=video_files)

@videoLib_blueprint.route('/videos/<filename>')
def stream_video(filename):
    def generate():
        with open(os.path.join(VIDEOS_FOLDER, filename), "rb") as video_file:
            data = video_file.read(1024)
            while data:
                yield data
                data = video_file.read(1024)

    return Response(generate(), mimetype="video/mp4")