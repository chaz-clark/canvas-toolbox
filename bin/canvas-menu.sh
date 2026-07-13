#!/usr/bin/env bash
# Canvas access boundary — the faculty-facing menu (macOS / Linux).
#
# The security model is unchanged: a plain script talks to Canvas, the instructor
# runs it, and no AI tool holds the Canvas token. This file is presentation only.
# Every guard — allowlist, write confirmation, enrolled-course guard, token
# injection, audit log — lives in lib/tools/canvas_run.py. This script cannot do
# anything the CLI could not; it just types the flags for you after asking, in
# English, whether you meant it.
#
# The answer to "faculty find the CLI hard" is NOT to let an AI agent run the
# command — that hands the Canvas credential to an AI vendor. It is to make it
# trivial for the HUMAN to run it.
#
# See docs/canvas-access-boundary.md.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GRN=$'\033[32m'
YEL=$'\033[33m'; CYN=$'\033[36m'; OFF=$'\033[0m'

get_env() {  # get_env KEY  -> value from .env, without sourcing it
  [ -f .env ] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" .env \
    | head -1 | sed 's/^["'\'']//; s/["'\'']$//' | tr -d '\r'
}

# The course NAME is the guard that matters to a human. A stale .env pointing at
# the wrong course id is invisible (111111 vs 111112); a wrong name is not. (L12)
course_name() {
  [ -f .canvas/index.json ] || return 0
  python3 - <<'PY' 2>/dev/null || true
import json
try:
    print(json.load(open(".canvas/index.json")).get("course", {}).get("name") or "")
except Exception:
    pass
PY
}

COURSE_ID="$(get_env CANVAS_COURSE_ID)"
BASE_URL="$(get_env CANVAS_BASE_URL)"
NAME="$(course_name)"

if [ -z "${COURSE_ID:-}" ]; then
  printf "\n  %sNo CANVAS_COURSE_ID in .env — nothing to talk to.%s\n" "$RED" "$OFF"
  printf "  Ask whoever set this repo up, or see docs/canvas-access-boundary.md.\n\n"
  read -r -p "  Press Enter to close..." _
  exit 2
fi

gate() {
  printf "\n  %s> canvas_run.py %s%s\n\n" "$DIM" "$*" "$OFF"
  uv run python lib/tools/canvas_run.py "$@"
}

pause() { printf "\n  %sPress Enter to return to the menu...%s" "$DIM" "$OFF"; read -r _; }

while true; do
  clear
  printf "\n  ============================================================\n"
  printf "   %sCANVAS%s  —  this is the only thing that talks to Canvas.\n" "$CYN$BOLD" "$OFF"
  printf "  ============================================================\n\n"
  if [ -n "${NAME:-}" ]; then
    printf "   Course:  %s%s%s\n" "$YEL" "$NAME" "$OFF"
  else
    printf "   Course:  (not pulled yet)\n"
  fi
  printf "   ID:      %s          %s\n\n" "$COURSE_ID" "$BASE_URL"
  printf "   %sIs that the right course? If not, STOP and ask for help.%s\n\n" "$DIM" "$OFF"
  printf "  ------------------------------------------------------------\n\n"
  printf "    1.  Get the latest from Canvas          %s(safe — read only)%s\n" "$DIM" "$OFF"
  printf "    2.  See what would change in Canvas     %s(safe — read only)%s\n" "$DIM" "$OFF"
  printf "    3.  Check the course for problems       %s(safe — read only)%s\n\n" "$DIM" "$OFF"
  printf "    4.  %sSEND my changes to Canvas%s          %s(students see this immediately)%s\n\n" "$RED$BOLD" "$OFF" "$DIM" "$OFF"
  printf "    Q.  Quit\n\n"
  read -r -p "   Choose 1, 2, 3, 4 or Q: " choice
  choice="$(printf '%s' "$choice" | tr '[:lower:]' '[:upper:]' | tr -d '[:space:]')"

  case "$choice" in
    1)
      printf "\n  %sGetting the latest copy of the course from Canvas...%s\n" "$CYN" "$OFF"
      if gate pull; then
        printf "\n  %sDone. The course is now on this computer, in the 'course' folder.%s\n" "$GRN" "$OFF"
        printf "  Nothing in Canvas was changed.\n"
      else
        printf "\n  %sThat didn't finish. Nothing in Canvas was changed.%s\n" "$RED" "$OFF"
      fi
      pause ;;

    2)
      printf "\n  %sComparing your local copy against Canvas...%s\n" "$CYN" "$OFF"
      gate status
      printf "\n  %sNothing was sent to Canvas — this only looks.%s\n" "$GRN" "$OFF"
      pause ;;

    3)
      printf "\n  %sAuditing the course. This takes a minute...%s\n" "$CYN" "$OFF"
      gate audit
      printf "\n  Done. The report is in 'audit.md' — open it in any editor.\n"
      printf "  Nothing in Canvas was changed.\n"
      pause ;;

    4)
      printf "\n  %s============================================================%s\n" "$RED" "$OFF"
      printf "   %sTHIS WRITES TO THE LIVE COURSE%s\n" "$RED$BOLD" "$OFF"
      printf "  %s============================================================%s\n\n" "$RED" "$OFF"
      printf "   Canvas has no draft mode. Whatever you send goes live\n"
      printf "   immediately and enrolled students can see it at once.\n"
      printf "   There is no undo.\n\n"
      printf "   %sFirst, here is exactly what would be sent:%s\n" "$CYN" "$OFF"
      gate status
      printf "\n  ------------------------------------------------------------\n\n"
      if [ -n "${NAME:-}" ]; then
        printf "   Sending to:  %s%s (%s)%s\n\n" "$YEL" "$NAME" "$COURSE_ID" "$OFF"
      else
        printf "   Sending to:  %scourse %s%s\n\n" "$YEL" "$COURSE_ID" "$OFF"
      fi
      printf "   If the list above is not exactly what you meant to change,\n"
      printf "   type anything else to cancel.\n\n"
      read -r -p "   Type SEND to publish these changes to Canvas: " confirm
      if [ "$confirm" != "SEND" ]; then
        printf "\n  %sCancelled. Nothing was sent to Canvas.%s\n" "$GRN" "$OFF"
        pause; continue
      fi
      printf "\n  %sSending...%s\n" "$CYN" "$OFF"
      # Both flags the gate requires. The typed SEND above is the human
      # equivalent — the flags are not skipped, just not memorized.
      if gate push --confirm-course "$COURSE_ID" --allow-enrolled; then
        printf "\n  %sSent. Your changes are live in Canvas now.%s\n" "$GRN" "$OFF"
        printf "  Check the course in a browser to confirm it looks right.\n"
      else
        printf "\n  %sThat did not complete. Check the messages above.%s\n" "$RED" "$OFF"
        printf "  Some changes may have been sent before it stopped — check Canvas.\n"
      fi
      pause ;;

    Q) printf "\n  Bye.\n\n"; exit 0 ;;

    *) printf "\n  %sDidn't catch that — please type 1, 2, 3, 4 or Q.%s\n" "$YEL" "$OFF"; sleep 1 ;;
  esac
done
