from flask import Blueprint, request, render_template
import requests
from flask_httpauth import HTTPBasicAuth

def create_stepper_blueprint():
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
    ESP8266_IP = "http://192.168.178.45"  # Replace with the IP of your ESP8266

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

