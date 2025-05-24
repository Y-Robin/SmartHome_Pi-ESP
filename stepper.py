from flask import Blueprint, request, render_template
import requests
from flask_httpauth import HTTPBasicAuth
import yaml
from pathlib import Path

def load_config():
    with open(Path("config.yaml"), 'r') as file:
        return yaml.safe_load(file)

def create_stepper_blueprint():

    config = load_config()
    # Finde die IP von dem ESP, der das Stepper-Modul hat
    stepper_device_ip = None
    for device in config["devices"].values():
        if "Stepper" in device["elements"]:
            stepper_device_ip = f"http://{device['ip']}"
            break

    if not stepper_device_ip:
        raise ValueError("Kein Gerät mit Stepper-Element in der config.yaml gefunden.")


    auth = HTTPBasicAuth()
    users = {
        "root": "root",  # Replace with your desired username and password
    }

    @auth.verify_password
    def verify_password(username, password):
        if username in users:
            return users.get(username) == password
        return False

    stepper_blueprint = Blueprint('stepper', __name__, template_folder='templates')
    ESP8266_IP = stepper_device_ip  # Replace with the IP of your ESP8266

    @stepper_blueprint.route('/stepper')
    @auth.login_required  # This decorator should be applied directly to the route function
    def stepper():
        return render_template('stepper.html')

    @stepper_blueprint.route('/set_angle', methods=['POST'])
    def set_angle():
        angle = request.form.get('angle')
        if angle:
            requests.get(f"{ESP8266_IP}/set_angle?angle={angle}")
            return "Angle set to " + angle
        else:
            return "No angle provided", 400

    @stepper_blueprint.route('/get_angle')
    def get_angle():
        response = requests.get(f"{ESP8266_IP}/get_angle")
        return response.text

    return stepper_blueprint
