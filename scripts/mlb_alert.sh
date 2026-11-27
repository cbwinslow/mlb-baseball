#!/usr/bin/env bash
# Failure alert hook for `mlb nightly` (set as alert_command in mlb.toml).
# The message arrives as the last argument. It is always appended to the local
# alert file (shown at login by mlb_alert_banner.sh) and, when configured, sent
# to Discord and/or ntfy. Channel settings come from ~/.mlb/alert.env
# (chmod 600, never committed):
#   MLB_DISCORD_WEBHOOK=https://discord.com/api/webhooks/...
#   MLB_NTFY_URL=https://ntfy.sh/<your-topic>
# A failing remote send is reported on stderr and does not lose the local record.
set -euo pipefail

MLB_HOME="${MLB_HOME:-$HOME/.mlb}"
ALERT_FILE="$MLB_HOME/alerts.log"
ENV_FILE="$MLB_HOME/alert.env"

message="${*: -1}"
if [[ -z "$message" ]]; then
  echo "mlb_alert.sh: no message given" >&2
  exit 2
fi

mkdir -p "$MLB_HOME"
printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${message//$'\n'/ | }" >> "$ALERT_FILE"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  . "$ENV_FILE"
fi

status=0
if [[ -n "${MLB_DISCORD_WEBHOOK:-}" ]]; then
  payload="$(python3 -c 'import json,sys; print(json.dumps({"content": "mlb alert: " + sys.argv[1][:1800]}))' "$message")"
  curl -fsS --max-time 15 -H 'Content-Type: application/json' -d "$payload" \
    "$MLB_DISCORD_WEBHOOK" >/dev/null || { echo "mlb_alert.sh: Discord send failed" >&2; status=1; }
fi
if [[ -n "${MLB_NTFY_URL:-}" ]]; then
  curl -fsS --max-time 15 -H 'Title: mlb alert' -d "${message:0:1800}" \
    "$MLB_NTFY_URL" >/dev/null || { echo "mlb_alert.sh: ntfy send failed" >&2; status=1; }
fi
exit "$status"
