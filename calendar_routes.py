from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from extensions import db
from models import CalendarEvent, ShowerEvent


def _parse_iso_datetime(value):
    if not value:
        return None
    sanitized = value.replace('Z', '+00:00')
    return datetime.fromisoformat(sanitized)


def _parse_event_reference(event_id):
    if not event_id or '-' not in event_id:
        return None, None
    event_type, raw_id = event_id.split('-', 1)
    try:
        return event_type, int(raw_id)
    except ValueError:
        return None, None


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
                'type': 'user',
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
                'type': 'shower',
                'deviceId': event.device_id,
            }
            for event in shower_events
        )

        return jsonify(events)

    @calendar_blueprint.route('/calendar_events/<event_id>', methods=['PATCH'])
    def update_calendar_event(event_id):
        event_type, raw_id = _parse_event_reference(event_id)
        if not event_type:
            return jsonify({'error': 'Invalid event id.'}), 400

        if event_type == 'user':
            event = CalendarEvent.query.get(raw_id)
            if not event:
                return jsonify({'error': 'Event not found.'}), 404

            data = request.get_json() or {}
            title = (data.get('title') or event.title).strip()
            start_value = data.get('start')
            end_value = data.get('end')

            if not title:
                return jsonify({'error': 'Title is required.'}), 400

            if start_value:
                event.start_time = _parse_iso_datetime(start_value)
            if end_value is not None:
                event.end_time = _parse_iso_datetime(end_value)
            event.title = title
            db.session.commit()
            return jsonify({'message': 'Event updated'})

        if event_type == 'shower':
            event = ShowerEvent.query.get(raw_id)
            if not event:
                return jsonify({'error': 'Event not found.'}), 404

            data = request.get_json() or {}
            start_value = data.get('start')
            end_value = data.get('end')

            if start_value:
                event.start_time = _parse_iso_datetime(start_value)
            if end_value is not None:
                event.end_time = _parse_iso_datetime(end_value)
            db.session.commit()
            return jsonify({'message': 'Event updated'})

        return jsonify({'error': 'Invalid event id.'}), 400

    @calendar_blueprint.route('/calendar_events/<event_id>', methods=['DELETE'])
    def delete_calendar_event(event_id):
        event_type, raw_id = _parse_event_reference(event_id)
        if not event_type:
            return jsonify({'error': 'Invalid event id.'}), 400

        if event_type == 'user':
            event = CalendarEvent.query.get(raw_id)
        elif event_type == 'shower':
            event = ShowerEvent.query.get(raw_id)
        else:
            return jsonify({'error': 'Invalid event id.'}), 400

        if not event:
            return jsonify({'error': 'Event not found.'}), 404

        db.session.delete(event)
        db.session.commit()
        return jsonify({'message': 'Event deleted'})

    return calendar_blueprint
