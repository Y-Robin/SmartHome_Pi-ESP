from flask import Blueprint, request, render_template, redirect, url_for
import requests
import yaml
from pathlib import Path
from flask_httpauth import HTTPBasicAuth

def load_config():
    with open(Path("config.yaml"), 'r') as file:
        return yaml.safe_load(file)

def create_stepper_blueprint():
    config = load_config()
    stepper_devices = config.get("stepper_devices", {})

    if not stepper_devices:
        raise ValueError("Keine Stepper-Geräte in config.yaml gefunden.")

    auth = HTTPBasicAuth()
    users = {
        "root": "root",  # Passwort anpassen
    }

    @auth.verify_password
    def verify_password(username, password):
        return users.get(username) == password

    stepper_blueprint = Blueprint('stepper', __name__, template_folder='templates')

    # Standard-Route zur ersten verfügbaren Stepper
    @stepper_blueprint.route('/stepper')
    @auth.login_required
    def default_stepper():
        first_stepper = next(iter(stepper_devices))
        return redirect(url_for('stepper.stepper_control', device_id=first_stepper))

    # Steuerungs-UI
    @stepper_blueprint.route('/stepper/<device_id>')
    @auth.login_required
    def stepper_control(device_id):
        if device_id not in stepper_devices:
            return f"Unbekanntes Stepper-Device '{device_id}'", 404
        return render_template('stepper.html', device_id=device_id, devices=stepper_devices)

    # Winkel setzen
    @stepper_blueprint.route('/set_angle/<device_id>', methods=['POST'])
    def set_angle(device_id):
        devices = load_config().get("stepper_devices", {})
        if device_id not in devices:
            return "Ungültiges Gerät", 404
        angle = request.form.get('angle')
        ip = devices[device_id]['ip']
        if angle:
            try:
                r = requests.get(f"http://{ip}/set_angle?angle={angle}")
                return r.text or f"Winkel gesetzt auf {angle}"
            except Exception as e:
                return f"Fehler: {e}", 500
        return "Kein Winkel angegeben", 400

    # Aktuellen Winkel holen
    @stepper_blueprint.route('/get_angle/<device_id>')
    def get_angle(device_id):
        devices = load_config().get("stepper_devices", {})
        if device_id not in devices:
            return "Ungültiges Gerät", 404
        ip = devices[device_id]['ip']
        try:
            r = requests.get(f"http://{ip}/get_angle")
            return r.text
        except Exception as e:
            return f"Fehler: {e}", 500

    return stepper_blueprint
