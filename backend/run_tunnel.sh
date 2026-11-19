#!/bin/bash
# Opens a public HTTPS tunnel to the backend (port 8000) so Twilio can reach it. Keep it running.
cd "$(dirname "$0")"
TOKEN=$(grep '^NGROK_AUTHTOKEN=' .env | cut -d= -f2-)
NGROK="$HOME/Library/Application Support/ngrok/ngrok"
"$NGROK" config add-authtoken "$TOKEN" >/dev/null
exec "$NGROK" http 8000 --log=stdout
