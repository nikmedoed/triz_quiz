"""Real-time projector for TRIZ-quiz."""

from io import BytesIO

from flask import Flask, render_template, request, abort, send_file, redirect
from flask_socketio import SocketIO, emit

from .config import settings
from .db import Database
from .resources import load_scenario

HOST = settings.server_host
PORT = settings.server_port

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")  # simple CORS for local network
db = Database(settings.db_file, settings.avatar_dir)

SCENARIO = load_scenario()


def build_rating(rows: list[dict]) -> list[dict]:
    return [
        {"id": r["id"], "name": r["name"], "score": r["score"], "place": r["place"]}
        for r in rows
    ]


def compute_progress() -> dict | None:
    step = db.get_step()
    if step < 0 or step >= len(SCENARIO):
        return None
    stype = SCENARIO[step].get('type')
    if stype not in ('open', 'quiz', 'vote'):
        return None
    total = len(db.get_participants())
    if stype == 'vote':
        votes = db.get_votes(step)
        answered = sum(1 for v in votes.values() if v)
    else:
        answers = db.get_responses(step, stype)
        answered = len(answers)
    ts = db.get_last_answer_ts()
    return {"answered": answered, "total": total, "ts": ts if answered else None}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/update', methods=['POST'])
def update():
    """
    Bot POSTs json {event: str, payload: {...}}.
    We just broadcast to all connected clients.
    """
    if not request.is_json:
        abort(415)
    data = request.get_json()
    event = data['event']
    payload = data['payload']
    socketio.emit(event, payload)
    return '', 204


def broadcast_step(idx: int) -> None:
    if 0 <= idx < len(SCENARIO):
        step = dict(SCENARIO[idx])
        if step.get('type') == 'vote':
            step['ideas'] = [
                {"id": idea["id"], "text": idea["text"], "time": idea["time"], "user": idea["user_id"]}
                for idea in db.get_ideas(idx - 1)
            ]
        socketio.emit('step', step)
    # Do not emit anything if scenario index is out of range.


def next_step() -> None:
    step = db.get_step() + 1
    while True:
        if step < len(SCENARIO):
            stype = SCENARIO[step].get('type')
            # Skip vote results if there were no ideas
            if (
                stype == 'vote_results'
                and step > 0
                and SCENARIO[step - 1].get('type') == 'vote'
                and not db.get_ideas(step - 1)
            ):
                step += 1
                continue
            db.set_step(step)
            if stype == 'vote':
                ideas = db.get_ideas(step - 1)
                if not ideas:
                    socketio.emit('step', {**SCENARIO[step], 'ideas': []})
                    return
            broadcast_step(step)
        elif step == len(SCENARIO):
            db.set_step(step)
            # Last step finished; keep stage 2 so results remain visible.
        else:
            db.set_step(step)
            # Explicit transition to final rating after moderator presses Next again.
            db.set_stage(3)
            socketio.emit('end', {})
        break


@app.route('/start', methods=['POST'])
def start_quiz():
    db.set_stage(2)
    socketio.emit('started', {})
    next_step()
    return '', 204


@app.route('/next', methods=['POST'])
def next_route():
    next_step()
    return '', 204


@app.route('/reset', methods=['GET', 'POST'])
def reset_route():
    if request.method == 'POST':
        from .bot import state
        state.reset_state()
        socketio.emit('participants', {'who': []})
        socketio.emit('reset', {})
        return redirect('/')
    return render_template('reset.html')


@app.route('/avatar/<int:user_id>')
def avatar(user_id: int):
    data = db.get_avatar(user_id)
    if not data:
        abort(404)
    return send_file(BytesIO(data), mimetype='image/jpeg')


@socketio.on('connect')
def handle_connect():
    people = [
        {"id": row["id"], "name": row["name"]} for row in db.get_participants()
    ]
    stage = db.get_stage()
    if stage == 1:
        emit("participants", {"who": people})
    else:
        emit("started", {})
        step = db.get_step()
        if step < len(SCENARIO):
            broadcast_step(step)
        prog = compute_progress()
        if prog:
            emit('progress', prog)
        if stage == 3:
            emit('end', {})
            rows = db.get_leaderboard()
            emit('rating', build_rating(rows))


def run_server():
    """Запуск веб-сервера для отображения."""
    # Flask-SocketIO 6.x forbids the development server unless explicitly allowed.
    # We only use this simple Werkzeug server for local demos, so it is safe to
    # enable the "unsafe" mode here.
    socketio.run(
        app,
        host=HOST,
        port=PORT,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )


if __name__ == '__main__':
    run_server()
