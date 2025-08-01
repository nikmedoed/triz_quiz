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
STATE_FILE=state.json
```

`BOT_TOKEN` and `ADMIN_ID` are required for the bot to operate.

`STATE_FILE` stores quiz progress so it can be restored after a restart. Admins can reset it with `/reset`.
