# triz_quiz
A telegram quiz for a presentation about inventive situations.

## Configuration

Settings are read from environment variables.  Copy `.env.example` to `.env`
and fill in your values before running:

```
BOT_TOKEN=123456:ABCDEF
ADMIN_ID=123456789
PROJECTOR_URL=http://localhost:5000/update
SERVER_HOST=0.0.0.0
SERVER_PORT=5000
```

`BOT_TOKEN` and `ADMIN_ID` are required for the bot to operate.
