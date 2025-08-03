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
skip_vote_results = False
quiz_result_state = None
vote_result_state = None

SCENARIO = load_scenario()


def get_step_data(idx: int) -> dict:
    """Return scenario step enriched with dynamic data."""
    step = dict(SCENARIO[idx])
    if step.get("type") == "vote":
        step["ideas"] = [
            {
                "id": idea["id"],
                "text": idea["text"],
                "time": idea["time"],
                "user": idea["user_id"],
            }
            for idea in db.get_ideas(idx - 1)
        ]
    return step


def render_step(step: dict) -> str:
    """Render HTML for a step using its type-specific template."""
    stype = step['type']
    if stype == 'quiz' and quiz_result_state:
        return render_template('steps/quiz_results.html', step=step, result=quiz_result_state)
    if stype == 'vote_results':
        return render_template('steps/vote_results.html', step=step, result=vote_result_state)
    return render_template(f"steps/{stype}.html", step=step)


def current_step_html() -> str:
    idx = db.get_step()
    if 0 <= idx < len(SCENARIO):
        return render_step(get_step_data(idx))
    return ""


@app.route("/current")
def current_step_route():
    html = current_step_html()
    if html:
        return html
    return "", 204


@app.route("/")
def index():
    return render_template("index.html")


@app.route('/update', methods=['POST'])
def update():
    """
    Bot POSTs json {event: str, payload: {...}}.
    We just broadcast to all connected clients.
    """
    if not request.is_json:
        abort(415)
    global progress_state, rating_state, quiz_result_state, vote_result_state
    data = request.get_json()
    event = data['event']
    payload = data['payload']
    socketio.emit(event, payload)
    if event == 'progress':
        progress_state = None if payload.get('inactive') else payload
    elif event == 'reset':
        progress_state = None
        rating_state = None
        quiz_result_state = None
        vote_result_state = None
    elif event == 'rating':
        rating_state = payload
    elif event == 'quiz_result':
        quiz_result_state = payload
        progress_state = None
        socketio.emit('reload', {})
    elif event == 'vote_result':
        vote_result_state = payload
        progress_state = None
        socketio.emit('reload', {})
    return '', 204


def next_step() -> dict | None:
    """Advance scenario and return new step data if available."""
    global progress_state, skip_vote_results, quiz_result_state, vote_result_state
    prev_idx = db.get_step()
    prev_type = SCENARIO[prev_idx].get('type') if 0 <= prev_idx < len(SCENARIO) else None
    if prev_type == 'quiz':
        quiz_result_state = None
    elif prev_type in ('vote', 'vote_results'):
        vote_result_state = None
    step = prev_idx + 1
    while True:
        if step < len(SCENARIO):
            stype = SCENARIO[step].get("type")
            if stype == "vote_results" and skip_vote_results:
                skip_vote_results = False
                step += 1
                continue
            db.set_step(step)
            if stype == "vote":
                ideas = db.get_ideas(step - 1)
                if not ideas:
                    skip_vote_results = True
                    return {**SCENARIO[step], "ideas": []}
            return get_step_data(step)
        elif step == len(SCENARIO):
            db.set_step(step)
            progress_state = None
            return None
        else:
            db.set_step(step)
            db.set_stage(3)
            progress_state = None
            socketio.emit("end", {})
            return None


@app.route('/start', methods=['POST'])
def start_quiz():
    global progress_state, rating_state, quiz_result_state, vote_result_state
    db.set_stage(2)
    progress_state = None
    rating_state = None
    quiz_result_state = None
    vote_result_state = None
    socketio.emit('started', {})
    step = next_step()
    socketio.emit('reload', {})
    if step:
        return render_step(step)
    return "", 204


@app.route('/next', methods=['POST'])
def next_route():
    idx = db.get_step()
    stype = SCENARIO[idx]['type'] if 0 <= idx < len(SCENARIO) else None
    if stype == 'quiz' and quiz_result_state is None:
        return "", 204
    if stype == 'vote' and vote_result_state is None:
        return "", 204
    step = next_step()
    socketio.emit('reload', {})
    if step:
        return render_step(step)
    return "", 204


@app.route('/reset', methods=['GET', 'POST'])
def reset_route():
    if request.method == 'POST':
        from .bot import state
        state.reset_state()
        global progress_state, rating_state, quiz_result_state, vote_result_state
        progress_state = None
        rating_state = None
        quiz_result_state = None
        vote_result_state = None
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
        if progress_state:
            emit('progress', progress_state)
        if stage == 3:
            emit('end', {})
            if rating_state:
                emit('rating', rating_state)


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
