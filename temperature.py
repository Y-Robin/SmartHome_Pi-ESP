from flask import Blueprint, render_template, request, jsonify
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import and_
import yaml
import os

def load_devices_from_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)
    return list(config.get('devices', {}).keys())

def create_temperature_blueprint(socketio, db):
    temperature_blueprint = Blueprint('temperature', __name__)

    class TemperatureData(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        device_id = db.Column(db.String(50))  # New field for device ID
        temperature = db.Column(db.Float, nullable=False)
        humidity = db.Column(db.Float, nullable=False)
        timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    @temperature_blueprint.route('/temperature')
    def temperature():
        return render_template('temperature.html')
    
    @temperature_blueprint.route('/get_available_devices')
    def get_available_devices():
        device_list = load_devices_from_config()
        return jsonify(device_list)

    @temperature_blueprint.route('/record_temperature', methods=['POST'])
    def record_temperature():
        data = request.get_json()
        new_record = TemperatureData(
            device_id=data['device_id'],  # Handle device_id
            temperature=data['temperature'], 
            humidity=data['humidity']
        )
        db.session.add(new_record) 
        db.session.commit()
        # Emit the new temperature data
        socketio.emit('new_temperature_data', {
            'device_id': data['device_id'],  # Include device_id in the emitted data
            'temperature': data['temperature'], 
            'humidity': data['humidity']
        })
        return jsonify({"message": "Data recorded"}), 201

    @temperature_blueprint.route('/get_temperature_data')
    def get_temperature_data():
        device_id = request.args.get('device_id', 'ESP_01')
        date_str = request.args.get('date', None)

        query = TemperatureData.query.filter_by(device_id=device_id)

        if date_str:
            try:
                selected_date = datetime.strptime(date_str, '%Y-%m-%d')
                start = datetime.combine(selected_date, datetime.min.time())
                end = datetime.combine(selected_date, datetime.max.time())
                query = query.filter(TemperatureData.timestamp.between(start, end))
            except ValueError:
                return jsonify({"error": "Invalid date format"}), 400
        else:
            # Default: Letzte 24 Stunden
            end = datetime.utcnow()
            start = end - timedelta(hours=24)
            query = query.filter(TemperatureData.timestamp.between(start, end))

        data = query.order_by(TemperatureData.timestamp.asc()).all()

        return jsonify([
            {
                'device_id': record.device_id,
                'temperature': record.temperature,
                'humidity': record.humidity,
                'timestamp': record.timestamp.isoformat()
            }
            for record in data
        ])
    return temperature_blueprint