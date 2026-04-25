import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
import yaml
from flask import Blueprint, current_app, jsonify, render_template, request
from monitoring import report_error

DEFAULT_DEVICE = {
    "id": "socket-0",
    "name": "Socket 0",
    "url": "http://192.168.178.52/rpc/Switch.GetStatus?id=0",
}
POLL_INTERVAL_SECONDS = 1.0
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
        timestamp = db.Column(
            db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
        )

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

    def _resolve_device_aliases(app, canonical_device_id: str) -> List[str]:
        aliases: List[str] = []

        def _add(value: Optional[str]):
            if value and value not in aliases:
                aliases.append(value)

        for device in _get_configured_devices(app):
            device_id = device.get("id")
            device_url = device.get("url")
            if canonical_device_id in {device_id, device_url}:
                _add(device_id)
                _add(device_url)
                break

        _add(canonical_device_id)
        _add(DEFAULT_DEVICE.get("id"))
        _add(DEFAULT_DEVICE.get("url"))
        return aliases

    def _first_present_number(payload: Dict[str, Any], keys: List[str]) -> Optional[float]:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def _normalize_payload(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = raw_payload.get("result") if isinstance(raw_payload, dict) else None
        if not isinstance(payload, dict):
            payload = raw_payload if isinstance(raw_payload, dict) else {}

        for candidate in ("switch:0", "em:0"):
            nested = payload.get(candidate)
            if isinstance(nested, dict):
                payload = {**payload, **nested}
                break

        return payload

    def _parse_power_value(payload: Dict[str, Any]) -> Optional[float]:
        return _first_present_number(payload, ["apower", "power", "active_power"])

    def _parse_energy_value(payload: Dict[str, Any]) -> Optional[float]:
        energy_payload = payload.get("aenergy")
        if isinstance(energy_payload, dict):
            parsed = _first_present_number(energy_payload, ["total", "total_wh", "total_act"])
            if parsed is not None:
                return parsed
        return _first_present_number(payload, ["energy", "total_energy", "total_wh", "total_act"])

    def _collect_device_data(app, device_config: Dict[str, str]):
        device_url = device_config.get("url") or DEFAULT_DEVICE["url"]
        device_id = device_config.get("id") or device_url
        poll_interval = app.config.get("POWER_POLL_INTERVAL", POLL_INTERVAL_SECONDS)

        with app.app_context():
            while True:
                try:
                    response = requests.get(device_url, timeout=REQUEST_TIMEOUT_SECONDS)
                    response.raise_for_status()
                    payload = _normalize_payload(response.json() or {})

                    sample = PowerData(
                        device_id=device_id,
                        voltage=_first_present_number(payload, ["voltage", "a_voltage"]),
                        current=_first_present_number(payload, ["current", "a_current"]),
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
                            "timestamp": (sample.timestamp or datetime.utcnow())
                            .replace(tzinfo=timezone.utc)
                            .isoformat(),
                        },
                    )
                except Exception:
                    db.session.rollback()
                    app.logger.exception("Failed to collect power data from %s", device_url)
                    report_error(
                        "power",
                        "Fehler beim Erfassen von Power-Daten",
                        {"device_id": device_id, "url": device_url},
                    )

                socketio.sleep(poll_interval)

    def _cleanup_old_data(app):
        retention_days = app.config.get("POWER_RETENTION_DAYS", 7) or 7
        cleanup_interval_seconds = max(retention_days, 1) * 24 * 60 * 60

        with app.app_context():
            while True:
                try:
                    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
                    deleted = PowerData.query.filter(PowerData.timestamp < cutoff).delete()
                    db.session.commit()
                    app.logger.info(
                        "Power cleanup removed %s rows older than %s days",
                        deleted,
                        retention_days,
                    )
                except Exception:
                    db.session.rollback()
                    app.logger.exception("Power cleanup failed")
                    report_error("power", "Fehler beim Bereinigen alter Power-Daten")

                socketio.sleep(cleanup_interval_seconds)

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

        cleanup_key = "started::power_cleanup"
        if not device_flags.get(cleanup_key):
            device_flags[cleanup_key] = True
            socketio.start_background_task(_cleanup_old_data, app)

    @power_blueprint.route("/power")
    def power_dashboard():
        return render_template("power.html")

    @power_blueprint.route("/get_power_data")
    def get_power_data():
        duration_seconds = request.args.get("duration_seconds", default=3600, type=int)
        device_id = request.args.get("device_id")
        resolved_device_id = _resolve_device_id(current_app, device_id)
        device_aliases = _resolve_device_aliases(current_app, resolved_device_id)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(seconds=max(duration_seconds or 0, 0))

        try:
            query = (
                PowerData.query.filter(
                    PowerData.timestamp.between(start_time, end_time),
                    PowerData.device_id.in_(device_aliases),
                )
                .order_by(PowerData.timestamp.asc())
            )

            data = []
            for row in query:
                timestamp = row.timestamp or datetime.utcnow()
                aware_ts = timestamp.replace(tzinfo=timezone.utc)
                data.append(
                    {
                        "device_id": row.device_id,
                        "voltage": row.voltage,
                        "current": row.current,
                        "power": row.power,
                        "energy": row.energy,
                        "timestamp": aware_ts.isoformat(),
                    }
                )

            if not data:
                latest_row = (
                    PowerData.query.filter(PowerData.device_id.in_(device_aliases))
                    .order_by(PowerData.timestamp.desc())
                    .first()
                )
                if latest_row is not None:
                    timestamp = latest_row.timestamp or datetime.utcnow()
                    aware_ts = timestamp.replace(tzinfo=timezone.utc)
                    data.append(
                        {
                            "device_id": resolved_device_id,
                            "voltage": latest_row.voltage,
                            "current": latest_row.current,
                            "power": latest_row.power,
                            "energy": latest_row.energy,
                            "timestamp": aware_ts.isoformat(),
                        }
                    )

            return jsonify(data)
        except Exception:
            report_error(
                "power",
                "Fehler beim Laden von Power-Daten aus der Datenbank",
                {"device_id": device_id, "duration_seconds": duration_seconds},
            )
            return jsonify({"error": "Power-Daten konnten nicht geladen werden"}), 500

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
