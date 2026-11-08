#!/usr/bin/env bash
# Prints unseen mlb alerts at shell login. Source or run it from ~/.zshrc:
#   [[ -o interactive ]] && ~/workspace/mlb/scripts/mlb_alert_banner.sh
# `mlb_alert_banner.sh --clear` marks everything seen. Prints nothing when there
# is nothing new, so it never adds noise.
set -euo pipefail

MLB_HOME="${MLB_HOME:-$HOME/.mlb}"
ALERT_FILE="$MLB_HOME/alerts.log"
SEEN_FILE="$MLB_HOME/alerts.seen"

[[ -f "$ALERT_FILE" ]] || exit 0
total="$(wc -l < "$ALERT_FILE")"
seen="$(cat "$SEEN_FILE" 2>/dev/null || echo 0)"

if [[ "${1:-}" == "--clear" ]]; then
  echo "$total" > "$SEEN_FILE"
  exit 0
fi

new=$(( total - seen ))
(( new > 0 )) || exit 0
printf '\033[1;31m== %d unseen mlb alert(s) ==\033[0m\n' "$new"
tail -n "$(( new > 5 ? 5 : new ))" "$ALERT_FILE" | cut -c1-200
(( new > 5 )) && echo "... and $(( new - 5 )) older. Full list: $ALERT_FILE"
echo "Mark seen: $0 --clear"
