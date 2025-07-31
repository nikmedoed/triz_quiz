
"""
Real-time projector for TRIZ-quiz.
Run:  python server.py
"""
import os
from flask import Flask, render_template, request, abort
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")       # simple CORS for local network

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

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
