from flask import Blueprint, render_template, redirect, url_for
import yaml
from pathlib import Path

def load_config():
    with open(Path("config.yaml"), 'r') as file:
        return yaml.safe_load(file)

robot_blueprint = Blueprint('robot', __name__, template_folder='templates')

@robot_blueprint.route('/robot')
def default_robot():
    config = load_config()
    robot_devices = config.get("robot_devices", {})

    if not robot_devices:
        return "Keine Robotergeräte in config.yaml gefunden.", 404

    # Redirect auf erstes Gerät
    first_robot = next(iter(robot_devices))
    return redirect(url_for('robot.robot_control', device_id=first_robot))

@robot_blueprint.route('/robot/<device_id>')
def robot_control(device_id):
    config = load_config()
    robot_devices = config.get("robot_devices", {})
    camera_devices = config.get("camera_devices", {})

    if device_id not in robot_devices:
        return f"Robotergerät '{device_id}' nicht gefunden.", 404

    # Prüfen, ob es eine Kamera mit gleichem Namen gibt
    cam_id = None
    for cam_name, cam in camera_devices.items():
        if cam['ip'] == robot_devices[device_id]['ip']:
            cam_id = cam_name
            break

    return render_template(
        'robot.html',
        device_id=device_id,
        devices=robot_devices,
        robot_ip=robot_devices[device_id]['ip'],
        cam_id=cam_id  # neu!
    )

