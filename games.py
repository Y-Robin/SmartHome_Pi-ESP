from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import desc

from extensions import db
from models import SnakeScore


games_blueprint = Blueprint('games', __name__)


def _fetch_top_scores(limit=5):
    return (
        SnakeScore.query.order_by(desc(SnakeScore.score), SnakeScore.created_at)
        .limit(limit)
        .all()
    )


def _serialize_scores(scores):
    return [
        {
            'name': score.player_name,
            'score': score.score,
            'created_at': score.created_at.isoformat(),
        }
        for score in scores
    ]


@games_blueprint.route('/games')
def games():
    top_scores = _fetch_top_scores()
    return render_template('games.html', top_scores=top_scores)


@games_blueprint.route('/games/snake/scores')
def snake_scores():
    top_scores = _fetch_top_scores()
    return jsonify({'scores': _serialize_scores(top_scores)})


@games_blueprint.route('/games/snake/score', methods=['POST'])
def submit_snake_score():
    payload = request.get_json(silent=True) or request.form
    name = (payload.get('name') or '').strip()
    score_value = payload.get('score')

    try:
        score_int = int(score_value)
    except (TypeError, ValueError):
        return jsonify({'error': 'Ungültiger Score.'}), 400

    if not name:
        return jsonify({'error': 'Bitte einen Namen eingeben.'}), 400

    if score_int < 0:
        return jsonify({'error': 'Score muss positiv sein.'}), 400

    trimmed_name = name[:80]
    new_score = SnakeScore(player_name=trimmed_name, score=score_int)
    db.session.add(new_score)
    db.session.commit()

    top_scores = _fetch_top_scores()
    return jsonify({'scores': _serialize_scores(top_scores)})
