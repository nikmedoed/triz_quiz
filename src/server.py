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
progress_state = None
rating_state = None
vote_result_state = None
quiz_result_state = None
skip_vote_results = False

SCENARIO = load_scenario()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/update', methods=['POST'])
def update():
    """
    Bot POSTs json {event: str, payload: {...}}.
    Broadcast small real-time updates to connected clients
    and store larger payloads for HTTP rendering.
    """
    if not request.is_json:
        abort(415)
    global progress_state, rating_state, vote_result_state, quiz_result_state
    data = request.get_json()
    event = data['event']
    payload = data['payload']
    if event in {'progress', 'participants', 'reset'}:
        socketio.emit(event, payload)
    if event == 'progress':
        progress_state = None if payload.get('inactive') else payload
    elif event == 'reset':
        progress_state = None
        rating_state = None
        vote_result_state = None
        quiz_result_state = None
    elif event == 'rating':
        rating_state = payload
    elif event == 'vote_result':
        vote_result_state = payload
    elif event == 'quiz_result':
        quiz_result_state = payload
    return '', 204


def get_step(idx: int | None = None) -> dict | None:
    """Return current scenario step with extra data from the database."""
    if idx is None:
        idx = db.get_step()
    if 0 <= idx < len(SCENARIO):
        step = dict(SCENARIO[idx])
        if step.get('type') == 'vote':
            step['ideas'] = [
                {"id": idea["id"], "text": idea["text"], "time": idea["time"], "user": idea["user_id"]}
                for idea in db.get_ideas(idx - 1)
            ]
        return step
    return None


def next_step() -> None:
    """Advance to the next step in the scenario."""
    global progress_state, skip_vote_results, vote_result_state, quiz_result_state
    step = db.get_step() + 1
    while True:
        if step < len(SCENARIO):
            stype = SCENARIO[step].get('type')
            if stype == 'vote_results' and skip_vote_results:
                skip_vote_results = False
                step += 1
                continue
            db.set_step(step)
            if stype == 'vote':
                ideas = db.get_ideas(step - 1)
                if not ideas:
                    skip_vote_results = True
                    return
            if stype != 'vote_results':
                vote_result_state = None
            if stype != 'quiz_results':
                quiz_result_state = None
        elif step == len(SCENARIO):
            db.set_step(step)
            # Last step finished; keep stage 2 so results remain visible.
            progress_state = None
        else:
            db.set_step(step)
            # Explicit transition to final rating after moderator presses Next again.
            db.set_stage(3)
            progress_state = None
        break


def render_current():
    """Render current state (step or rating) as HTML."""
    stage = db.get_stage()
    if stage == 3:
        if rating_state:
            return render_template("rating.html", rating=rating_state, stage=stage)
        step = {"title": "Ожидание рейтинга", "type": "slide", "content": ""}
        return render_template(
            "step.html",
            step=step,
            stage=stage,
            vote_result=vote_result_state,
            quiz_result=quiz_result_state,
        )
    step = get_step()
    return render_template(
        "step.html",
        step=step,
        stage=stage,
        vote_result=vote_result_state,
        quiz_result=quiz_result_state,
    )


@app.route('/step')
def step_route():
    return render_current()


@app.route('/start', methods=['POST'])
def start_quiz():
    global progress_state, rating_state, vote_result_state, quiz_result_state
    db.set_stage(2)
    progress_state = None
    rating_state = None
    vote_result_state = None
    quiz_result_state = None
    next_step()
    return render_current()


@app.route('/next', methods=['POST'])
def next_route():
    next_step()
    return render_current()


@app.route('/reset', methods=['GET', 'POST'])
def reset_route():
    if request.method == 'POST':
        from .bot import state
        state.reset_state()
        global progress_state, rating_state
        progress_state = None
        rating_state = None
        vote_result_state = None
        quiz_result_state = None
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
    emit("participants", {"who": people})
    if progress_state:
        emit('progress', progress_state)


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
