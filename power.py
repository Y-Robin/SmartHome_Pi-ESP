from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import requests
from flask import Blueprint, jsonify, render_template, request


DEFAULT_DEVICE_URL = "http://192.168.178.52/rpc/Switch.GetStatus?id=0"
POLL_INTERVAL_SECONDS = 0.2
REQUEST_TIMEOUT_SECONDS = 5


def create_power_blueprint(socketio, db):
    power_blueprint = Blueprint("power", __name__)

    class PowerData(db.Model):
        __tablename__ = "power_data"

        id = db.Column(db.Integer, primary_key=True)
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

    def _collect_device_data(app):
        device_url = app.config.get("POWER_DEVICE_URL", DEFAULT_DEVICE_URL)
        poll_interval = app.config.get("POWER_POLL_INTERVAL", POLL_INTERVAL_SECONDS)

        with app.app_context():
            while True:
                try:
                    response = requests.get(device_url, timeout=REQUEST_TIMEOUT_SECONDS)
                    response.raise_for_status()
                    payload = response.json() or {}

                    sample = PowerData(
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
    def start_background_collector(state):
        app = state.app
        started_flags = app.extensions.setdefault("power", {})
        if not started_flags.get("collector_started"):
            started_flags["collector_started"] = True
            socketio.start_background_task(_collect_device_data, app)

    @power_blueprint.route("/power")
    def power_dashboard():
        return render_template("power.html")

    @power_blueprint.route("/get_power_data")
    def get_power_data():
        duration_seconds = request.args.get("duration_seconds", default=3600, type=int)
        limit = request.args.get("limit", default=1000, type=int)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(seconds=max(duration_seconds, 1))
        limited_rows = max(limit, 1)

        query = (
            PowerData.query
            .filter(PowerData.timestamp.between(start_time, end_time))
            .order_by(PowerData.timestamp.asc())
            .limit(limited_rows)
        )

        data = [
            {
                "voltage": record.voltage,
                "current": record.current,
                "power": record.power,
                "energy": record.energy,
                "timestamp": record.timestamp.isoformat(),
            }
            for record in query
        ]

        return jsonify(data)

    return power_blueprint
