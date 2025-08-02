"""Real-time projector for TRIZ-quiz."""

from io import BytesIO
import webbrowser

from flask import Flask, render_template, request, abort, send_file, redirect
from flask_socketio import SocketIO, emit

from .config import settings
from .db import Database
from .resources import load_scenario

HOST = settings.server_host
PORT = settings.server_port

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")  # simple CORS for local network
db = Database(settings.db_file)
progress_state = db.get_state_json("progress")
rating_state = db.get_state_json("rating")

SCENARIO = load_scenario()


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
    global progress_state, rating_state
    data = request.get_json()
    event = data['event']
    payload = data['payload']
    socketio.emit(event, payload)
    if event == 'progress':
        if payload.get('inactive'):
            progress_state = None
            db.set_state_json('progress', None)
        else:
            progress_state = payload
            db.set_state_json('progress', payload)
    elif event == 'reset':
        progress_state = None
        rating_state = None
        db.set_state_json('progress', None)
        db.set_state_json('rating', None)
    elif event == 'rating':
        rating_state = payload
        db.set_state_json('rating', payload)
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
    global progress_state
    step = db.get_step() + 1
    db.set_step(step)
    if step < len(SCENARIO):
        broadcast_step(step)
    elif step == len(SCENARIO):
        # Last step finished; keep stage 2 so results remain visible.
        # No "end" signal yet to allow manual transition to rating.
        progress_state = None
    else:
        # Explicit transition to final rating after moderator presses Next again.
        db.set_stage(3)
        progress_state = None
        socketio.emit('end', {})


@app.route('/start', methods=['POST'])
def start_quiz():
    global progress_state, rating_state
    db.set_stage(2)
    progress_state = None
    rating_state = None
    db.set_state_json('progress', None)
    db.set_state_json('rating', None)
    socketio.emit('started', {})
    next_step()
    return '', 204


@app.route('/next', methods=['POST'])
def next_route():
    next_step()
    return '', 204


@app.route('/reset', methods=['GET', 'POST'])
def reset_route():
    global progress_state, rating_state
    if request.method == 'POST':
        db.reset()
        progress_state = None
        rating_state = None
        db.set_state_json('progress', None)
        db.set_state_json('rating', None)
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
        if progress_state:
            emit('progress', progress_state)
        if stage == 3:
            emit('end', {})
            if rating_state:
                emit('rating', rating_state)


def run_server():
    """Запуск веб-сервера для отображения."""
    display_host = "127.0.0.1" if HOST in ("0.0.0.0", "::") else HOST
    url = f"http://{display_host}:{PORT}/reset"
    print(f"Reset quiz data: {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
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
