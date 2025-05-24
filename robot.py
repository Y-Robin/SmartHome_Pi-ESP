from flask import Blueprint, render_template
import yaml
from pathlib import Path

def load_config():
    with open(Path("config.yaml"), 'r') as file:
        return yaml.safe_load(file)

robot_blueprint = Blueprint('robot', __name__, template_folder='templates')

@robot_blueprint.route('/robot')
def robot_control():
    config = load_config()
    robot_config = config.get("robot_devices", {})
    
    if not robot_config:
        raise ValueError("Kein Roboter in config.yaml unter 'robot_devices' gefunden.")

    robot_ip = next(iter(robot_config.values()))['ip']
    
    return render_template('robot.html', robot_ip=robot_ip)
