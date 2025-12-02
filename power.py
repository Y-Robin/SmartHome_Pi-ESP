import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from flask import Blueprint, current_app, jsonify, render_template, request
import yaml


DEFAULT_DEVICE_URL = "http://192.168.178.52/rpc/Switch.GetStatus?id=0"
DEFAULT_DEVICES = [
    {
        "id": "socket-0",
        "name": "Socket 0",
        "url": DEFAULT_DEVICE_URL,
    }
]
POLL_INTERVAL_SECONDS = 0.2
REQUEST_TIMEOUT_SECONDS = 5


def create_power_blueprint(socketio, db):
    power_blueprint = Blueprint("power", __name__)

    class PowerData(db.Model):
        __tablename__ = "power_data"

        id = db.Column(db.Integer, primary_key=True)
        device_id = db.Column(db.String(64), index=True)
        voltage = db.Column(db.Float)
        current = db.Column(db.Float)
        power = db.Column(db.Float)
        energy = db.Column(db.Float)
        timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def _parse_power_value(payload: Dict[str, Any]) -> Optional[float]:
        power_value = payload.get("apower")
        if power_value is None:
            power_value = payload.get("power")
        return power_value

    def _load_devices_from_config_file() -> Optional[List[Dict[str, str]]]:
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        if not os.path.exists(config_path):
            return None

        try:
            with open(config_path, "r") as file:
                config = yaml.safe_load(file) or {}
        except Exception:
            current_app.logger.exception("Failed to read power config file")
            return None

        configured = []
        for device_id, props in (config.get("socket_devices") or {}).items():
            ip = (props or {}).get("ip")
            if not ip:
                continue
            configured.append(
                {
                    "id": device_id,
                    "name": (props or {}).get("name") or device_id,
                    "url": f"http://{ip}/rpc/Switch.GetStatus?id=0",
                }
            )

        return configured or None

    def _get_configured_devices(app) -> List[Dict[str, str]]:
        configured_devices = app.config.get("POWER_DEVICES")
        if configured_devices:
            return configured_devices

        loaded = _load_devices_from_config_file()
        if loaded:
            app.config["POWER_DEVICES"] = loaded
            return loaded

        return DEFAULT_DEVICES

    def _resolve_device_id(app, device_id: Optional[str]) -> str:
        devices = _get_configured_devices(app)
        configured_ids = {d.get("id") or d.get("url") for d in devices}

        if device_id and device_id in configured_ids:
            return device_id

        return next(iter(configured_ids))

    def _collect_device_data(app, device_config: Dict[str, str]):
        device_url = device_config.get("url") or DEFAULT_DEVICE_URL
        device_id = device_config.get("id") or device_url
        poll_interval = app.config.get("POWER_POLL_INTERVAL", POLL_INTERVAL_SECONDS)

        with app.app_context():
            while True:
                try:
                    response = requests.get(device_url, timeout=REQUEST_TIMEOUT_SECONDS)
                    response.raise_for_status()
                    payload = response.json() or {}

                    sample = PowerData(
                        device_id=device_id,
                        voltage=payload.get("voltage"),
                        current=payload.get("current"),
                        power=_parse_power_value(payload),
                        energy=(payload.get("aenergy") or {}).get("total"),
                    )
                    db.session.add(sample)
                    db.session.commit()

                    socketio.emit(
                        "power_sample",
                        {
                            "device_id": sample.device_id,
                            "voltage": sample.voltage,
                            "current": sample.current,
                            "power": sample.power,
                            "energy": sample.energy,
                            "timestamp": sample.timestamp.isoformat(),
                        },
                    )
                except Exception:
                    db.session.rollback()
                    app.logger.exception(
                        "Failed to collect power data from %s", device_url
                    )

                socketio.sleep(poll_interval)

    @power_blueprint.record_once
    def start_background_collector(state):
        app = state.app
        started_flags = app.extensions.setdefault("power", {})
        devices = _get_configured_devices(app)

        for device in devices:
            device_key = f"collector_started::{device.get('id') or device.get('url')}"
            if started_flags.get(device_key):
                continue
            started_flags[device_key] = True
            socketio.start_background_task(_collect_device_data, app, device)

    @power_blueprint.route("/power")
    def power_dashboard():
        return render_template("power.html")

    @power_blueprint.route("/get_power_data")
    def get_power_data():
        duration_seconds = request.args.get("duration_seconds", default=3600, type=int)
        limit = request.args.get("limit", default=1000, type=int)
        device_id = _resolve_device_id(current_app, request.args.get("device_id"))

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(seconds=max(duration_seconds, 1))
        limited_rows = max(limit, 1)

        query = (
            PowerData.query
            .filter(PowerData.timestamp.between(start_time, end_time))
            .filter(PowerData.device_id == device_id)
            .order_by(PowerData.timestamp.asc())
            .limit(limited_rows)
        )

        data = [
            {
                "voltage": record.voltage,
                "current": record.current,
                "power": record.power,
                "energy": record.energy,
                "device_id": record.device_id,
                "timestamp": record.timestamp.isoformat(),
            }
            for record in query
        ]

        return jsonify(data)

    @power_blueprint.route("/get_power_devices")
    def get_power_devices():
        devices = _get_configured_devices(current_app)
        normalized = [
            {
                "id": device.get("id") or device.get("url"),
                "name": device.get("name") or device.get("id") or device.get("url"),
                "url": device.get("url") or DEFAULT_DEVICE_URL,
            }
            for device in devices
        ]
        return jsonify(normalized)

    return power_blueprint
