import os
import yaml
from flask import Flask, render_template, request
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
import temperature
import power
import led
import stepper
from camera_streamer import camera_blueprint
from streamEsp import streaming_blueprint, camera_devices
from videoLib import videoLib_blueprint
from robot import robot_blueprint  # Neuer Import


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
db = SQLAlchemy(app)
socketio = SocketIO(app)


def _load_power_devices_from_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    if not os.path.exists(config_path):
        return None

    with open(config_path, 'r') as file:
        config = yaml.safe_load(file) or {}

    devices_cfg = config.get('socket_devices', {})
    devices = []
    for device_id, props in devices_cfg.items():
        ip = (props or {}).get('ip')
        if not ip:
            continue
        devices.append({
            'id': device_id,
            'name': props.get('name') or device_id,
            'url': f"http://{ip}/rpc/Switch.GetStatus?id=0",
        })

    return devices or None


power_devices = _load_power_devices_from_config()
if power_devices:
    app.config['POWER_DEVICES'] = power_devices

led_blueprint = led.create_led_blueprint(socketio, db)
temperature_blueprint = temperature.create_temperature_blueprint(socketio, db)
power_blueprint = power.create_power_blueprint(socketio, db)
stepper_blueprint = stepper.create_stepper_blueprint()

# Register blueprints
app.register_blueprint(temperature_blueprint)
app.register_blueprint(power_blueprint)
app.register_blueprint(led_blueprint)
app.register_blueprint(camera_blueprint)
app.register_blueprint(stepper_blueprint)
app.register_blueprint(streaming_blueprint, url_prefix='/')
app.register_blueprint(videoLib_blueprint)
app.register_blueprint(robot_blueprint)  # Registrierung des Roboter-Blueprints


@app.route('/videoStreams')
def video_streams():
    source = request.args.get('source')
    cam_id = request.args.get('cam_id')
    selected_cam = cam_id if cam_id in camera_devices else None
    if not selected_cam and camera_devices:
        selected_cam = next(iter(camera_devices))

    default_source = 'esp' if camera_devices else 'pi'
    selected_source = source if source in {'pi', 'esp'} else default_source
    if selected_source == 'esp' and not camera_devices:
        selected_source = 'pi'
    return render_template(
        'video_streams.html',
        selected_source=selected_source,
        cam_id=selected_cam,
        cameras=camera_devices,
    )


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(
        app,
        host='0.0.0.0',
        port=80,
        debug=True,
        use_reloader=False,
        extra_files=None,
        log_output=True,
        allow_unsafe_werkzeug=True,
    )
