
"""Real-time projector for TRIZ-quiz."""

from flask import Flask, render_template, request, abort, send_file
from flask_socketio import SocketIO
from io import BytesIO

from config import settings
from db import Database

HOST = settings.server_host
PORT = settings.server_port

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")       # simple CORS for local network
db = Database(settings.db_file)

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
    socketio.emit(data['event'], data['payload'])
    return '', 204


@app.route('/start', methods=['POST'])
def start_quiz():
    db.set_stage(2)
    socketio.emit('started', {})
    return '', 204


@app.route('/avatar/<int:user_id>')
def avatar(user_id: int):
    data = db.get_avatar(user_id)
    if not data:
        abort(404)
    return send_file(BytesIO(data), mimetype='image/jpeg')


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
