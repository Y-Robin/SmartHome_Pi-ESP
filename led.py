from flask import Blueprint, request, jsonify, render_template
import requests
from requests.exceptions import ConnectionError
from flask_socketio import SocketIO
import yaml
from pathlib import Path

def create_led_blueprint(socketio):
    led_blueprint = Blueprint('led', __name__)

    CONFIG_PATH = Path("config.yaml")

    with open(CONFIG_PATH, 'r') as file:
        config = yaml.safe_load(file)

        esp_devices = {
            device_id: {**info, "status": "unknown"}
            for device_id, info in config['devices'].items()
        }


    @led_blueprint.route('/')
    def index():
        return render_template('index.html', devices=esp_devices)


    @led_blueprint.route('/control_led/<device_id>', methods=['POST'])
    def control_led(device_id):
        command = request.form.get('command')
        send_command_to_device(device_id, command)
        emit_led_status(device_id)
        return '', 204

    def send_command_to_device(device_id, command):
        try:
            response = requests.get(f"http://{esp_devices[device_id]['ip']}/{command}", timeout=2)
            if response.status_code == 200:
                esp_devices[device_id]['status'] = command
            else:
                esp_devices[device_id]['status'] = 'error'
        except ConnectionError:
            esp_devices[device_id]['status'] = 'not connected'

    @socketio.on('connect')
    def on_connect():
        for device_id in esp_devices:
            emit_led_status(device_id)

    def emit_led_status(device_id):
        socketio.emit('led_status', {'device_id': device_id, 'status': esp_devices[device_id]['status']})

    for device_id in esp_devices:
        try:
            requests.get(f"http://{esp_devices[device_id]['ip']}/off")
            esp_devices[device_id]['status'] = 'off'
        except:
            esp_devices[device_id]['status'] = 'not connected'

    return led_blueprint
