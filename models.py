from datetime import datetime

from extensions import db


class ShowerEvent(db.Model):
    __tablename__ = 'shower_events'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)


class CalendarEvent(db.Model):
    __tablename__ = 'calendar_events'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
