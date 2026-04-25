import os
from datetime import datetime

import requests
from flask import Blueprint, jsonify, render_template, request

from extensions import db
from models import ChatMessage, ChatSession


OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://192.168.178.41:11434').rstrip('/')
REQUEST_TIMEOUT_SECONDS = 45

ollama_chat_blueprint = Blueprint('ollama_chat', __name__)


def _serialize_session(session):
    last_message = (
        ChatMessage.query.filter_by(session_id=session.id)
        .order_by(ChatMessage.created_at.desc())
        .first()
    )
    return {
        'id': session.id,
        'title': session.title,
        'model': session.model,
        'created_at': session.created_at.isoformat(),
        'updated_at': session.updated_at.isoformat(),
        'last_message_preview': (last_message.content[:140] if last_message else ''),
    }


def _serialize_message(message):
    return {
        'id': message.id,
        'role': message.role,
        'content': message.content,
        'created_at': message.created_at.isoformat(),
    }


def _fetch_ollama_models():
    response = requests.get(f'{OLLAMA_BASE_URL}/api/tags', timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json() or {}
    models = payload.get('models', [])
    return [model.get('name') for model in models if model.get('name')]


def _build_context_messages(session_id):
    stored_messages = (
        ChatMessage.query.filter_by(session_id=session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [{'role': item.role, 'content': item.content} for item in stored_messages]


@ollama_chat_blueprint.route('/ollama-chat')
def ollama_chat_page():
    return render_template('ollama_chat.html', ollama_base_url=OLLAMA_BASE_URL)


@ollama_chat_blueprint.route('/ollama-chat/api/models')
def ollama_models():
    try:
        models = _fetch_ollama_models()
    except requests.RequestException as exc:
        return jsonify({'error': f'Ollama nicht erreichbar ({exc}).'}), 502
    return jsonify({'models': models, 'base_url': OLLAMA_BASE_URL})


@ollama_chat_blueprint.route('/ollama-chat/api/sessions', methods=['GET'])
def list_chat_sessions():
    sessions = ChatSession.query.order_by(ChatSession.updated_at.desc()).all()
    return jsonify({'sessions': [_serialize_session(session) for session in sessions]})


@ollama_chat_blueprint.route('/ollama-chat/api/sessions', methods=['POST'])
def create_chat_session():
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip() or f'Chat {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}'
    model = (payload.get('model') or '').strip()

    session = ChatSession(title=title[:120], model=model[:120] or None)
    db.session.add(session)
    db.session.commit()
    return jsonify({'session': _serialize_session(session)})


@ollama_chat_blueprint.route('/ollama-chat/api/sessions/<int:session_id>/messages', methods=['GET'])
def list_session_messages(session_id):
    session = ChatSession.query.get_or_404(session_id)
    messages = (
        ChatMessage.query.filter_by(session_id=session.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return jsonify({
        'session': _serialize_session(session),
        'messages': [_serialize_message(message) for message in messages],
    })


@ollama_chat_blueprint.route('/ollama-chat/api/chat', methods=['POST'])
def send_chat_message():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get('session_id')
    prompt = (payload.get('prompt') or '').strip()
    model = (payload.get('model') or '').strip()

    if not session_id:
        return jsonify({'error': 'session_id fehlt.'}), 400
    if not prompt:
        return jsonify({'error': 'prompt fehlt.'}), 400
    if not model:
        return jsonify({'error': 'Bitte ein Modell auswählen.'}), 400

    session = ChatSession.query.get_or_404(int(session_id))

    user_message = ChatMessage(session_id=session.id, role='user', content=prompt)
    db.session.add(user_message)
    db.session.flush()

    context_messages = _build_context_messages(session.id)

    try:
        response = requests.post(
            f'{OLLAMA_BASE_URL}/api/chat',
            json={
                'model': model,
                'messages': context_messages,
                'stream': False,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json() or {}
        assistant_content = ((payload.get('message') or {}).get('content') or '').strip()
        if not assistant_content:
            raise ValueError('Leere Antwort von Ollama.')
    except (requests.RequestException, ValueError) as exc:
        db.session.rollback()
        return jsonify({'error': f'Ollama Fehler: {exc}'}), 502

    assistant_message = ChatMessage(session_id=session.id, role='assistant', content=assistant_content)
    db.session.add(assistant_message)

    session.model = model
    if session.title.lower().startswith('chat ') and len(prompt) > 0:
        session.title = prompt[:80]
    session.updated_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        'session': _serialize_session(session),
        'user_message': _serialize_message(user_message),
        'assistant_message': _serialize_message(assistant_message),
    })
