from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from extensions import db
from models import CalendarEvent, ShowerEvent


def _parse_iso_datetime(value):
    if not value:
        return None
    sanitized = value.replace('Z', '+00:00')
    return datetime.fromisoformat(sanitized)


def create_calendar_blueprint():
    calendar_blueprint = Blueprint('calendar', __name__)

    @calendar_blueprint.route('/calendar')
    def calendar_view():
        return render_template('calendar.html')

    @calendar_blueprint.route('/calendar_events', methods=['GET', 'POST'])
    def calendar_events():
        if request.method == 'POST':
            data = request.get_json() or {}
            title = (data.get('title') or '').strip()
            start_value = data.get('start')
            end_value = data.get('end')

            if not title or not start_value:
                return jsonify({'error': 'Title and start time are required.'}), 400

            start_time = _parse_iso_datetime(start_value)
            end_time = _parse_iso_datetime(end_value)

            new_event = CalendarEvent(
                title=title,
                start_time=start_time,
                end_time=end_time,
            )
            db.session.add(new_event)
            db.session.commit()
            return jsonify({'message': 'Event created', 'id': new_event.id}), 201

        user_events = CalendarEvent.query.order_by(CalendarEvent.start_time.asc()).all()
        shower_events = ShowerEvent.query.order_by(ShowerEvent.start_time.asc()).all()

        events = [
            {
                'id': f'user-{event.id}',
                'title': event.title,
                'start': event.start_time.isoformat(),
                'end': event.end_time.isoformat() if event.end_time else None,
                'backgroundColor': '#2563eb',
                'borderColor': '#2563eb',
            }
            for event in user_events
        ]

        events.extend(
            {
                'id': f'shower-{event.id}',
                'title': f'Duschen ({event.device_id})',
                'start': event.start_time.isoformat(),
                'end': event.end_time.isoformat() if event.end_time else None,
                'backgroundColor': '#f59e0b',
                'borderColor': '#f59e0b',
            }
            for event in shower_events
        )

        return jsonify(events)

    return calendar_blueprint
