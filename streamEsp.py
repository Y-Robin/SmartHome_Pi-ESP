# streaming.py
from flask import Blueprint, render_template, send_file

shared_file = 'shared_frame2.jpg'
streaming_blueprint = Blueprint('streaming', __name__, template_folder='templates')

@streaming_blueprint.route('/streamEsp')
def streamEsp():
    return render_template('streamEsp.html')

@streaming_blueprint.route('/streamEspImg')
def stream():
    return send_file(shared_file, mimetype='image/jpeg')

