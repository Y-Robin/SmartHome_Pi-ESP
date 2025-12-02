import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
import yaml
from flask import Blueprint, current_app, jsonify, render_template, request

DEFAULT_DEVICE = {
    "id": "socket-0",
    "name": "Socket 0",
    "url": "http://192.168.178.52/rpc/Switch.GetStatus?id=0",
}
POLL_INTERVAL_SECONDS = 0.2
REQUEST_TIMEOUT_SECONDS = 5


def create_power_blueprint(socketio, db):
    power_blueprint = Blueprint("power", __name__)

    class PowerData(db.Model):
        __tablename__ = "power_data"

        id = db.Column(db.Integer, primary_key=True)
        device_id = db.Column(db.String(64))
        voltage = db.Column(db.Float)
        current = db.Column(db.Float)
        power = db.Column(db.Float)
        energy = db.Column(db.Float)
        timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def _load_devices_from_config_file() -> Optional[List[Dict[str, str]]]:
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        if not os.path.exists(config_path):
            return None

        try:
            with open(config_path, "r") as config_file:
                config = yaml.safe_load(config_file) or {}
        except Exception:
            current_app.logger.exception("Failed to load power devices from config.yaml")
            return None

        socket_devices = config.get("socket_devices") or {}
        devices: List[Dict[str, str]] = []
        for device_id, props in socket_devices.items():
            ip = (props or {}).get("ip")
            if not ip:
                continue
            devices.append(
                {
                    "id": device_id,
                    "name": (props or {}).get("name") or device_id,
                    "url": f"http://{ip}/rpc/Switch.GetStatus?id=0",
                }
            )

        return devices or None

    def _get_configured_devices(app) -> List[Dict[str, str]]:
        devices = app.config.get("POWER_DEVICES")
        if devices:
            return devices

        loaded_devices = _load_devices_from_config_file()
        if loaded_devices:
            app.config["POWER_DEVICES"] = loaded_devices
            return loaded_devices

        app.config["POWER_DEVICES"] = [DEFAULT_DEVICE]
        return [DEFAULT_DEVICE]

    def _resolve_device_id(app, requested_id: Optional[str]) -> str:
        devices = _get_configured_devices(app)
        if not devices:
            return DEFAULT_DEVICE["id"]

        for device in devices:
            candidate_id = device.get("id") or device.get("url")
            if requested_id and requested_id == candidate_id:
                return candidate_id

        first_device = devices[0]
        return first_device.get("id") or first_device.get("url")

    def _parse_power_value(payload: Dict[str, Any]) -> Optional[float]:
        return payload.get("apower") or payload.get("power")

    def _parse_energy_value(payload: Dict[str, Any]) -> Optional[float]:
        energy_payload = payload.get("aenergy") or {}
        return energy_payload.get("total") or energy_payload.get("total_wh")

    def _collect_device_data(app, device_config: Dict[str, str]):
        device_url = device_config.get("url") or DEFAULT_DEVICE["url"]
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
                        energy=_parse_energy_value(payload),
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
                    app.logger.exception("Failed to collect power data from %s", device_url)

                socketio.sleep(poll_interval)

    @power_blueprint.record_once
    def start_collectors(state):
        app = state.app
        device_flags = app.extensions.setdefault("power_collectors", {})
        devices = _get_configured_devices(app)

        for device in devices:
            device_key = device.get("id") or device.get("url")
            started_key = f"started::{device_key}"
            if device_flags.get(started_key):
                continue

            device_flags[started_key] = True
            socketio.start_background_task(_collect_device_data, app, device)

    @power_blueprint.route("/power")
    def power_dashboard():
        return render_template("power.html")

    @power_blueprint.route("/get_power_data")
    def get_power_data():
        duration_seconds = request.args.get("duration_seconds", default=3600, type=int)
        limit = request.args.get("limit", default=1000, type=int)
        device_id = request.args.get("device_id")
        resolved_device_id = _resolve_device_id(current_app, device_id)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(seconds=max(duration_seconds or 0, 0))
        limited_rows = max(limit or 0, 1)

        query = (
            PowerData.query.filter(
                PowerData.timestamp.between(start_time, end_time),
                PowerData.device_id == resolved_device_id,
            )
            .order_by(PowerData.timestamp.asc())
            .limit(limited_rows)
        )

        data = [
            {
                "device_id": row.device_id,
                "voltage": row.voltage,
                "current": row.current,
                "power": row.power,
                "energy": row.energy,
                "timestamp": row.timestamp.isoformat(),
            }
            for row in query
        ]

        return jsonify(data)

    @power_blueprint.route("/get_power_devices")
    def get_power_devices():
        devices = _get_configured_devices(current_app)
        return jsonify(
            [
                {
                    "id": device.get("id") or device.get("url"),
                    "name": device.get("name") or device.get("id") or device.get("url"),
                    "url": device.get("url") or DEFAULT_DEVICE["url"],
                }
                for device in devices
            ]
        )

    return power_blueprint
