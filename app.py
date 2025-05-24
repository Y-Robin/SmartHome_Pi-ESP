from flask import Flask
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
import temperature 
import led 
import stepper 
from camera_streamer import camera_blueprint
from streamEsp import streaming_blueprint
from videoLib import videoLib_blueprint
from robot import robot_blueprint  # Neuer Import


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
db = SQLAlchemy(app)
socketio = SocketIO(app)

led_blueprint = led.create_led_blueprint(socketio)
temperature_blueprint = temperature.create_temperature_blueprint(socketio, db)
stepper_blueprint = stepper.create_stepper_blueprint()

# Register blueprints
app.register_blueprint(temperature_blueprint)
app.register_blueprint(led_blueprint)
app.register_blueprint(camera_blueprint)
app.register_blueprint(stepper_blueprint)
app.register_blueprint(streaming_blueprint, url_prefix='/')
app.register_blueprint(videoLib_blueprint)
app.register_blueprint(robot_blueprint)  # Registrierung des Roboter-Blueprints

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, host='0.0.0.0', port=80, debug=True, use_reloader=False, extra_files=None, log_output=True, allow_unsafe_werkzeug=True)