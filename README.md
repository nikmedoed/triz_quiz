# triz_quiz
A telegram quiz for a presentation about inventive situations.

## Configuration

Settings are read from environment variables. Copy `.env.example` to `.env`
and fill in your values before running. The application loads these settings via
`config.py`, so both the bot and the projector server share the same
configuration:

```
BOT_TOKEN=123456:ABCDEF
ADMIN_ID=123456789
PROJECTOR_URL=http://localhost:5000/update
SERVER_HOST=0.0.0.0
SERVER_PORT=5000
DB_FILE=quiz.db
```

`BOT_TOKEN` and `ADMIN_ID` are required for the bot to operate.

`DB_FILE` points to a SQLite database where quiz progress, participant info,
their responses, and cached avatars are persisted. Admins can reset the state
with `/reset`.

## Running

Start the quiz bot and projector server together with:

```
python main.py
```

The command launches the Flask web interface in the background and begins polling
Telegram for bot updates.

## Registration

Participants join by messaging `/start` to the bot. It asks each user for a
display name, caches their avatar, and stores everything in the SQLite
database. The projector page lists registered players in a shrinking grid and
features a **Начать** button to move from registration to the quiz.
