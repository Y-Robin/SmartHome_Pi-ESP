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

        def init_devices(section):
            return {
                device_id: {**info, "status": "unknown"}
                for device_id, info in config.get(section, {}).items()
            }

        esp_devices = init_devices('devices')
        camera_devices = init_devices('camera_devices')
        robot_devices = init_devices('robot_devices')
        socket_devices = init_devices('socket_devices')


    @led_blueprint.route('/')
    def index():
        return render_template('index.html',
                       devices=esp_devices,
                       cameras=camera_devices,
                       robots=robot_devices,
                       sockets=socket_devices)


    @led_blueprint.route('/control_led/<device_id>', methods=['POST'])
    def control_led(device_id):
        command = request.form.get('command')
        send_command_to_device(device_id, command)
        emit_led_status(device_id)
        return '', 204

    @led_blueprint.route('/control_socket/<device_id>', methods=['POST'])
    def control_socket(device_id):
        command = request.form.get('command')
        send_socket_command(device_id, command)
        emit_socket_status(device_id)
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

    def send_socket_command(device_id, command):
        try:
            response = requests.get(
                f"http://{socket_devices[device_id]['ip']}/rpc/Switch.Set",
                params={"id": 0, "on": command == 'on'},
                timeout=2
            )
            if response.status_code == 200:
                socket_devices[device_id]['status'] = command
            else:
                socket_devices[device_id]['status'] = 'error'
        except ConnectionError:
            socket_devices[device_id]['status'] = 'not connected'

    def update_socket_status(device_id):
        try:
            response = requests.get(
                f"http://{socket_devices[device_id]['ip']}/rpc/Switch.GetStatus",
                params={"id": 0},
                timeout=2
            )
            if response.status_code == 200:
                data = response.json()
                socket_devices[device_id]['status'] = 'on' if data.get('output') else 'off'
            else:
                socket_devices[device_id]['status'] = 'unknown'
        except ConnectionError:
            socket_devices[device_id]['status'] = 'not connected'

    @socketio.on('connect')
    def on_connect():
        for device_id in esp_devices:
            emit_led_status(device_id)
        for device_id in socket_devices:
            emit_socket_status(device_id)

    def emit_led_status(device_id):
        socketio.emit('led_status', {'device_id': device_id, 'status': esp_devices[device_id]['status']})

    def emit_socket_status(device_id):
        socketio.emit('socket_status', {'device_id': device_id, 'status': socket_devices[device_id]['status']})

    for device_id in esp_devices:
        try:
            requests.get(f"http://{esp_devices[device_id]['ip']}/off")
            esp_devices[device_id]['status'] = 'off'
        except:
            esp_devices[device_id]['status'] = 'not connected'

    for device_id in socket_devices:
        update_socket_status(device_id)
        emit_socket_status(device_id)

    return led_blueprint
