import os
import sqlite3
from datetime import datetime
from pathlib import Path

import requests
from flask import Blueprint, jsonify, render_template, request


OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://192.168.178.41:11434').rstrip('/')
REQUEST_TIMEOUT_SECONDS = 45
CHAT_DB_PATH = Path(__file__).resolve().parent / 'ollama_chat.db'

ollama_chat_blueprint = Blueprint('ollama_chat', __name__)


def _utc_now_iso():
    return datetime.utcnow().isoformat(timespec='seconds')


def _get_conn():
    conn = sqlite3.connect(CHAT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_chat_db():
    with _get_conn() as conn:
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                model TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES chat_sessions(id)
            )
            '''
        )


_init_chat_db()


def _fetch_ollama_models():
    response = requests.get(f'{OLLAMA_BASE_URL}/api/tags', timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json() or {}
    models = payload.get('models', [])
    return [model.get('name') for model in models if model.get('name')]


def _session_exists(conn, session_id):
    row = conn.execute('SELECT id FROM chat_sessions WHERE id = ?', (session_id,)).fetchone()
    return bool(row)


def _serialize_session_row(conn, row):
    last_message_row = conn.execute(
        '''
        SELECT content
        FROM chat_messages
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT 1
        ''',
        (row['id'],),
    ).fetchone()

    return {
        'id': row['id'],
        'title': row['title'],
        'model': row['model'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'last_message_preview': (last_message_row['content'][:140] if last_message_row else ''),
    }


def _serialize_message_row(row):
    return {
        'id': row['id'],
        'role': row['role'],
        'content': row['content'],
        'created_at': row['created_at'],
    }


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
    with _get_conn() as conn:
        rows = conn.execute(
            '''
            SELECT id, title, model, created_at, updated_at
            FROM chat_sessions
            ORDER BY updated_at DESC
            '''
        ).fetchall()
        sessions = [_serialize_session_row(conn, row) for row in rows]
    return jsonify({'sessions': sessions})


@ollama_chat_blueprint.route('/ollama-chat/api/sessions', methods=['POST'])
def create_chat_session():
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip() or f'Chat {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}'
    model = (payload.get('model') or '').strip() or None
    now = _utc_now_iso()

    with _get_conn() as conn:
        cur = conn.execute(
            '''
            INSERT INTO chat_sessions(title, model, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ''',
            (title[:120], model[:120] if model else None, now, now),
        )
        session_id = cur.lastrowid
        row = conn.execute(
            'SELECT id, title, model, created_at, updated_at FROM chat_sessions WHERE id = ?',
            (session_id,),
        ).fetchone()
        session = _serialize_session_row(conn, row)

    return jsonify({'session': session})


@ollama_chat_blueprint.route('/ollama-chat/api/sessions/<int:session_id>/messages', methods=['GET'])
def list_session_messages(session_id):
    with _get_conn() as conn:
        session_row = conn.execute(
            'SELECT id, title, model, created_at, updated_at FROM chat_sessions WHERE id = ?',
            (session_id,),
        ).fetchone()
        if not session_row:
            return jsonify({'error': 'Chat nicht gefunden.'}), 404

        message_rows = conn.execute(
            '''
            SELECT id, role, content, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY id ASC
            ''',
            (session_id,),
        ).fetchall()

        return jsonify({
            'session': _serialize_session_row(conn, session_row),
            'messages': [_serialize_message_row(row) for row in message_rows],
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

    now = _utc_now_iso()

    with _get_conn() as conn:
        if not _session_exists(conn, int(session_id)):
            return jsonify({'error': 'Chat nicht gefunden.'}), 404

        conn.execute(
            '''
            INSERT INTO chat_messages(session_id, role, content, created_at)
            VALUES (?, 'user', ?, ?)
            ''',
            (int(session_id), prompt, now),
        )

        context_rows = conn.execute(
            '''
            SELECT role, content
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY id ASC
            ''',
            (int(session_id),),
        ).fetchall()

        context_messages = [{'role': row['role'], 'content': row['content']} for row in context_rows]

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
            ollama_payload = response.json() or {}
            assistant_content = ((ollama_payload.get('message') or {}).get('content') or '').strip()
            if not assistant_content:
                raise ValueError('Leere Antwort von Ollama.')
        except (requests.RequestException, ValueError) as exc:
            conn.rollback()
            return jsonify({'error': f'Ollama Fehler: {exc}'}), 502

        assistant_now = _utc_now_iso()
        user_row_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        assistant_cur = conn.execute(
            '''
            INSERT INTO chat_messages(session_id, role, content, created_at)
            VALUES (?, 'assistant', ?, ?)
            ''',
            (int(session_id), assistant_content, assistant_now),
        )
        assistant_row_id = assistant_cur.lastrowid

        session_title_row = conn.execute('SELECT title FROM chat_sessions WHERE id = ?', (int(session_id),)).fetchone()
        session_title = session_title_row['title'] if session_title_row else ''
        if session_title.lower().startswith('chat ') and prompt:
            session_title = prompt[:80]

        conn.execute(
            'UPDATE chat_sessions SET model = ?, title = ?, updated_at = ? WHERE id = ?',
            (model, session_title, assistant_now, int(session_id)),
        )

        session_row = conn.execute(
            'SELECT id, title, model, created_at, updated_at FROM chat_sessions WHERE id = ?',
            (int(session_id),),
        ).fetchone()
        user_row = conn.execute(
            'SELECT id, role, content, created_at FROM chat_messages WHERE id = ?',
            (user_row_id,),
        ).fetchone()
        assistant_row = conn.execute(
            'SELECT id, role, content, created_at FROM chat_messages WHERE id = ?',
            (assistant_row_id,),
        ).fetchone()

        session = _serialize_session_row(conn, session_row)

    return jsonify({
        'session': session,
        'user_message': _serialize_message_row(user_row),
        'assistant_message': _serialize_message_row(assistant_row),
    })
