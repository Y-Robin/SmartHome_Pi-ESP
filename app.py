import os
import sqlite3
import yaml
from flask import Flask, render_template, request, jsonify
from sqlalchemy import event
from flask_socketio import SocketIO
import temperature
import power
import led
import stepper
from camera_streamer import camera_blueprint
from streamEsp import streaming_blueprint, camera_devices
from videoLib import videoLib_blueprint
from robot import robot_blueprint  # Neuer Import
from calendar_routes import create_calendar_blueprint
from games import games_blueprint
from ollama_chat import ollama_chat_blueprint
from extensions import db
from monitoring import get_recent_events
from db_repair import repair_sqlite_database


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {
        'timeout': 30,
        'check_same_thread': False,
    }
}
db.init_app(app)
socketio = SocketIO(app)


def _set_sqlite_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA journal_mode=WAL;')
    cursor.execute('PRAGMA synchronous=NORMAL;')
    cursor.execute('PRAGMA busy_timeout=5000;')
    cursor.close()


with app.app_context():
    event.listen(db.engine, 'connect', _set_sqlite_pragma)


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


def _get_sqlite_db_path() -> str:
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite:///'):
        return ''

    relative_or_absolute = db_uri.replace('sqlite:///', '', 1)
    if os.path.isabs(relative_or_absolute):
        return relative_or_absolute
    return os.path.join(app.instance_path, relative_or_absolute)


def _sqlite_quick_check():
    db_path = _get_sqlite_db_path()
    if not db_path:
        return {'status': 'unsupported', 'message': 'Nur für SQLite verfügbar.'}
    if not os.path.exists(db_path):
        return {'status': 'missing', 'message': 'Datenbankdatei noch nicht vorhanden.', 'db_path': db_path}

    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute('PRAGMA quick_check;').fetchone()
        check_result = (row[0] if row else 'unknown').strip().lower()
        if check_result == 'ok':
            return {'status': 'ok', 'message': 'SQLite quick_check ist ok.', 'db_path': db_path}
        return {
            'status': 'corrupt',
            'message': 'SQLite meldet eine beschädigte Datenbankdatei.',
            'db_path': db_path,
            'quick_check': check_result,
        }
    except Exception as error:
        return {
            'status': 'error',
            'message': 'quick_check konnte nicht ausgeführt werden.',
            'db_path': db_path,
            'error': str(error),
        }


power_devices = _load_power_devices_from_config()
if power_devices:
    app.config['POWER_DEVICES'] = power_devices

try:
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    if os.path.exists(config_path):
        with open(config_path, 'r') as file:
            cfg = yaml.safe_load(file) or {}
        poll_interval = cfg.get('power_poll_interval_seconds')
        if isinstance(poll_interval, (int, float)) and poll_interval > 0:
            app.config['POWER_POLL_INTERVAL'] = float(poll_interval)
except Exception:
    app.logger.exception('Konnte power_poll_interval_seconds nicht aus config.yaml laden')

led_blueprint = led.create_led_blueprint(socketio, db)
temperature_blueprint = temperature.create_temperature_blueprint(socketio, db)
power_blueprint = power.create_power_blueprint(socketio, db)
stepper_blueprint = stepper.create_stepper_blueprint()
calendar_blueprint = create_calendar_blueprint()

# Register blueprints
app.register_blueprint(temperature_blueprint)
app.register_blueprint(power_blueprint)
app.register_blueprint(led_blueprint)
app.register_blueprint(camera_blueprint)
app.register_blueprint(stepper_blueprint)
app.register_blueprint(streaming_blueprint, url_prefix='/')
app.register_blueprint(videoLib_blueprint)
app.register_blueprint(robot_blueprint)  # Registrierung des Roboter-Blueprints
app.register_blueprint(calendar_blueprint)
app.register_blueprint(games_blueprint)
app.register_blueprint(ollama_chat_blueprint)


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


@app.route('/monitoring/errors')
def monitoring_errors():
    component = request.args.get('component')
    limit = request.args.get('limit', default=30, type=int)
    return jsonify(get_recent_events(component=component, limit=limit))


@app.route('/monitoring/db_status')
def monitoring_db_status():
    return jsonify(_sqlite_quick_check())


@app.route('/monitoring/db_repair', methods=['POST'])
def monitoring_db_repair():
    db_path = _get_sqlite_db_path()
    if not db_path:
        return jsonify({'ok': False, 'message': 'Nur SQLite wird unterstützt.'}), 400

    result = repair_sqlite_database(db_path)
    status_code = 200 if result.get('ok') else 500
    return jsonify(result), status_code


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
