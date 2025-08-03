"""Simplified projector server using templates for each step."""

from io import BytesIO

from flask import Flask, render_template, request, abort, send_file, redirect

from .config import settings
from .db import Database
from .resources import load_scenario

HOST = settings.server_host
PORT = settings.server_port

app = Flask(__name__)
db = Database(settings.db_file, settings.avatar_dir)
SCENARIO = load_scenario()


@app.route("/")
def index():
    stage = db.get_stage()
    if stage == 1:
        participants = db.get_participants()
        return render_template("waiting.html", title="Ожидание начала…", participants=participants)
    step_idx = db.get_step()
    if 0 <= step_idx < len(SCENARIO):
        step = dict(SCENARIO[step_idx])
        if step["type"] == "vote":
            step["ideas"] = db.get_ideas(step_idx - 1)
        elif step["type"] == "vote_results":
            ideas = db.get_ideas(step_idx - 1)
            votes = db.get_votes(step_idx - 1)
            results = []
            for idea in ideas:
                count = sum(idea["id"] in v for v in votes.values())
                results.append({**idea, "count": count})
            step["results"] = results
        template = f"{step['type']}.html"
        return render_template(template, title=step.get("title", ""), step=step)
    rating = db.get_leaderboard()
    return render_template("rating.html", title="Итоговый рейтинг", rating=rating)


@app.get("/start")
def start_quiz():
    db.set_stage(2)
    db.set_step(0)
    return redirect("/")


@app.get("/next")
def next_step():
    step = db.get_step() + 1
    if step < len(SCENARIO):
        db.set_step(step)
    else:
        db.set_stage(3)
    return redirect("/")


@app.route("/reset", methods=["GET", "POST"])
def reset_route():
    if request.method == "POST":
        from .bot import state
        state.reset_state()
        db.reset()
        return redirect("/")
    return render_template("reset.html", title="Сбросить базу")


@app.route("/avatar/<int:user_id>")
def avatar(user_id: int):
    data = db.get_avatar(user_id)
    if not data:
        abort(404)
    return send_file(BytesIO(data), mimetype="image/jpeg")


def run_server() -> None:
    app.run(host=HOST, port=PORT)


if __name__ == "__main__":
    run_server()
