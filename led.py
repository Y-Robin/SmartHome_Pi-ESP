from datetime import datetime
from pathlib import Path
from typing import Dict, List

import requests
import yaml
from flask import Blueprint, jsonify, render_template, request
from flask_socketio import SocketIO
from requests.exceptions import ConnectionError, RequestException
from sqlalchemy import and_, func


def _safe_load_config(config_path: Path) -> Dict:
    if not config_path.exists():
        return {}

    with open(config_path, "r") as file:
        return yaml.safe_load(file) or {}

def create_led_blueprint(socketio: SocketIO, db):
    led_blueprint = Blueprint('led', __name__)

    CONFIG_PATH = Path("config.yaml")
    config = _safe_load_config(CONFIG_PATH)

    class TemperatureData(db.Model):
        __tablename__ = "temperature_data"

        id = db.Column(db.Integer, primary_key=True)
        device_id = db.Column(db.String(50))
        temperature = db.Column(db.Float, nullable=False)
        humidity = db.Column(db.Float, nullable=False)
        timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def init_devices(section: str) -> Dict[str, Dict]:
        devices = {}
        for device_id, info in config.get(section, {}).items():
            info = info or {}
            devices[device_id] = {
                **info,
                "name": info.get("name", device_id),
                "room": info.get("room", "Allgemein"),
                "status": "unknown",
            }
        return devices

    esp_devices = init_devices('devices')
    socket_devices = init_devices('socket_devices')


    @led_blueprint.route('/')
    def index():
        latest_readings = fetch_latest_readings()
        grouped_devices = group_devices_by_room(latest_readings)
        weather = fetch_weather()

        return render_template(
            'index.html',
            device_rooms=grouped_devices,
            weather=weather,
            has_devices=bool(grouped_devices),
        )


    @led_blueprint.route('/control_led/<device_id>', methods=['POST'])
    def control_led(device_id):
        command = request.form.get('command')
        if device_id not in esp_devices:
            return jsonify({"error": "Unknown device"}), 404

        send_command_to_device(device_id, command)
        emit_led_status(device_id)
        return '', 204

    @led_blueprint.route('/control_socket/<device_id>', methods=['POST'])
    def control_socket(device_id):
        command = request.form.get('command')
        if device_id not in socket_devices:
            return jsonify({"error": "Unknown socket"}), 404

        send_socket_command(device_id, command)
        update_socket_status(device_id)
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
            if command == 'toggle':
                response = requests.post(
                    f"http://{socket_devices[device_id]['ip']}/rpc/Switch.Toggle",
                    json={"id": 0},
                    timeout=2
                )
            else:
                response = requests.post(
                    f"http://{socket_devices[device_id]['ip']}/rpc/Switch.Set",
                    json={"id": 0, "on": command == 'on'},
                    timeout=2
                )

            if response.status_code != 200:
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

    def fetch_latest_readings():
        subquery = (
            db.session.query(
                TemperatureData.device_id,
                func.max(TemperatureData.timestamp).label("latest_timestamp"),
            )
            .group_by(TemperatureData.device_id)
            .subquery()
        )

        latest_entries = (
            db.session.query(TemperatureData)
            .join(
                subquery,
                and_(
                    TemperatureData.device_id == subquery.c.device_id,
                    TemperatureData.timestamp == subquery.c.latest_timestamp,
                ),
            )
            .all()
        )

        return {
            entry.device_id: {
                "temperature": entry.temperature,
                "humidity": entry.humidity,
                "timestamp": entry.timestamp,
            }
            for entry in latest_entries
        }

    def group_devices_by_room(latest_readings):
        rooms: Dict[str, List[Dict]] = {}
        for device_id, device in {**esp_devices, **socket_devices}.items():
            elements = device.get("elements", [])
            if not is_actionable(elements):
                continue

            room = device.get("room", "Allgemein")
            status = device.get("status", "unknown")
            connection_status = derive_connection_status(status)
            rooms.setdefault(room, []).append(
                {
                    "id": device_id,
                    "name": device.get("name", device_id),
                    "ip": device.get("ip", "-"),
                    "elements": elements,
                    "status": status,
                    "type": "socket" if device_id in socket_devices else "esp",
                    "connection_status": connection_status,
                    "reading": latest_readings.get(device_id)
                    if connection_status == "connected"
                    else None,
                }
            )

        for device_list in rooms.values():
            device_list.sort(key=lambda item: item["name"].lower())

        return dict(sorted(rooms.items(), key=lambda item: item[0].lower()))

    def is_actionable(elements: List[str]) -> bool:
        actionable_elements = {"Led", "Socket", "Temperature"}
        return any(elem in actionable_elements for elem in elements)

    def derive_connection_status(status: str) -> str:
        status = (status or "").lower()
        if status in {"not connected"}:
            return "disconnected"
        if status in {"error"}:
            return "error"
        if status in {"on", "off", "unknown"}:
            return "connected" if status in {"on", "off"} else "unknown"
        return "unknown"

    def fetch_weather():
        locations = {
            "Saarburg": {"latitude": 49.6097, "longitude": 6.5438},
            "Schengen": {"latitude": 49.4683, "longitude": 6.3667},
            "Saarbrücken": {"latitude": 49.2402, "longitude": 6.9969},
        }

        def weather_symbol(code):
            if code is None:
                return "—"
            if code == 0:
                return "☀️"
            if code in {1, 2}:
                return "🌤️"
            if code == 3:
                return "☁️"
            if code in {45, 48}:
                return "🌫️"
            if 51 <= code <= 57:
                return "🌦️"
            if 61 <= code <= 67:
                return "🌧️"
            if 71 <= code <= 77:
                return "🌨️"
            if 80 <= code <= 82:
                return "🌦️"
            if 85 <= code <= 86:
                return "🌨️"
            if code in {95, 96, 99}:
                return "⛈️"
            return "—"

        weather_reports = []
        for name, coords in locations.items():
            try:
                response = requests.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": coords["latitude"],
                        "longitude": coords["longitude"],
                        "current": "temperature_2m,relative_humidity_2m,weather_code",
                        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                        "forecast_days": 1,
                        "timezone": "Europe/Berlin",
                    },
                    timeout=5,
                )
                response.raise_for_status()
                payload = response.json()
                current = payload.get("current", {})
                daily = payload.get("daily", {})

                weather_reports.append(
                    {
                        "location": name,
                        "temperature": current.get("temperature_2m"),
                        "humidity": current.get("relative_humidity_2m"),
                        "weather_code": current.get("weather_code"),
                        "symbol": weather_symbol(current.get("weather_code")),
                        "forecast_max": (daily.get("temperature_2m_max") or [None])[0],
                        "forecast_min": (daily.get("temperature_2m_min") or [None])[0],
                        "precipitation_probability": (daily.get("precipitation_probability_max") or [None])[0],
                    }
                )
            except (RequestException, ValueError, KeyError):
                weather_reports.append(
                    {
                        "location": name,
                        "temperature": None,
                        "humidity": None,
                        "weather_code": None,
                        "symbol": "—",
                        "forecast_max": None,
                        "forecast_min": None,
                        "precipitation_probability": None,
                        "error": "Wetterdaten konnten nicht geladen werden",
                    }
                )

        return weather_reports

    return led_blueprint
