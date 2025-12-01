from datetime import datetime, timedelta
from flask import Blueprint, jsonify, render_template, request, current_app
import requests


DEVICE_URL = "http://192.168.178.52/rpc/Switch.GetStatus?id=0"
POLL_INTERVAL_SECONDS = 0.2


def create_power_blueprint(socketio, db):
    power_blueprint = Blueprint('power', __name__)
    collector_started = {'value': False}

    class PowerData(db.Model):
        __tablename__ = 'power_data'

        id = db.Column(db.Integer, primary_key=True)
        voltage = db.Column(db.Float)
        current = db.Column(db.Float)
        power = db.Column(db.Float)
        energy = db.Column(db.Float)
        timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def collect_device_data():
        """Continuously poll the Shelly device and persist the readings."""
        with current_app.app_context():
            while True:
                try:
                    response = requests.get(DEVICE_URL, timeout=5)
                    response.raise_for_status()
                    payload = response.json()

                    record = PowerData(
                        voltage=payload.get("voltage"),
                        current=payload.get("current"),
                        power=payload.get("apower"),
                        energy=(payload.get("aenergy") or {}).get("total"),
                    )
                    db.session.add(record)
                    db.session.commit()

                    socketio.emit(
                        'power_sample',
                        {
                            'voltage': record.voltage,
                            'current': record.current,
                            'power': record.power,
                            'energy': record.energy,
                            'timestamp': record.timestamp.isoformat(),
                        },
                    )
                except Exception:
                    db.session.rollback()
                    current_app.logger.exception("Failed to collect power data")

                socketio.sleep(POLL_INTERVAL_SECONDS)

    @power_blueprint.before_app_first_request
    def start_background_collector():
        if not collector_started['value']:
            collector_started['value'] = True
            socketio.start_background_task(collect_device_data)

    @power_blueprint.route('/power')
    def power_dashboard():
        return render_template('power.html')

    @power_blueprint.route('/get_power_data')
    def get_power_data():
        duration_seconds = request.args.get('duration_seconds', default=3600, type=int)
        limit = request.args.get('limit', default=1000, type=int)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(seconds=max(duration_seconds, 1))

        query = (
            PowerData.query
            .filter(PowerData.timestamp.between(start_time, end_time))
            .order_by(PowerData.timestamp.asc())
            .limit(limit)
        )

        data = [
            {
                'voltage': record.voltage,
                'current': record.current,
                'power': record.power,
                'energy': record.energy,
                'timestamp': record.timestamp.isoformat(),
            }
            for record in query
        ]

        return jsonify(data)

    return power_blueprint
