#!/usr/bin/env bash
# Start the synthetic-data demo so its link keeps working: the server runs detached (closing
# the terminal does not stop it), sign-ins survive restarts (fixed session secret), and the
# admin password is random rather than a published default. Safe to run repeatedly.
# Usage: scripts/demo-up.sh [--foreground]
set -euo pipefail
cd "$(dirname "$0")/.."

PORT=8000
CREDS=data/demo-credentials.txt
LOG=data/demo-server.log

[ -d .venv ] || make install
. .venv/bin/activate
mkdir -p data
touch .env

# A fixed secret keeps sessions valid across server restarts. .env is gitignored.
if ! grep -q '^BI_SESSION_SECRET=.' .env; then
  echo "BI_SESSION_SECRET=$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" >> .env
fi

# In Codespaces the forwarded URL is HTTPS, so allow its host and mark cookies Secure.
if [ -n "${CODESPACE_NAME:-}" ]; then
  host="$CODESPACE_NAME-$PORT.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  url="https://$host"
  grep -q '^BI_ALLOWED_HOSTS=' .env || echo "BI_ALLOWED_HOSTS=localhost,127.0.0.1,$host" >> .env
  grep -q '^BI_SECURE_COOKIES=' .env || echo "BI_SECURE_COOKIES=true" >> .env
else
  url="http://127.0.0.1:$PORT"
fi

if [ ! -f data/warehouse.db ]; then
  brand-insights demo-data
  brand-insights run-pipeline
fi

# Generate the admin password once; it replaces any earlier demo password for "admin".
if [ ! -f "$CREDS" ]; then
  password="$(python -c 'import secrets; print(secrets.token_urlsafe(18))')"
  BI_NEW_USER_PASSWORD="$password" brand-insights create-user admin --role admin
  printf 'username: admin\npassword: %s\n' "$password" > "$CREDS"
  chmod 600 "$CREDS"  # explicit: workspace ACLs can override umask
fi

echo "Demo URL: $url"
echo "Sign-in details: $(pwd)/$CREDS"

if [ "${1:-}" = "--foreground" ]; then
  exec brand-insights serve --port "$PORT"
fi
if curl -fsS "http://127.0.0.1:$PORT/healthz" > /dev/null 2>&1; then
  echo "Server already running on port $PORT."
else
  setsid nohup brand-insights serve --port "$PORT" >> "$LOG" 2>&1 < /dev/null &
  echo "Server started in the background (log: $LOG). Stop it with: make demo-down"
fi
