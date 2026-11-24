#!/usr/bin/env bash
# sync_context.sh — multi-course orchestration wrapper for canvas_sync.py
#
# Runs canvas_sync.py inside a per-context working directory (master/, s1/, etc.)
# with the matching course ID from .env. Each context gets its own course/,
# course_src/, and .canvas/ — fully isolated from other contexts.
#
# Usage:
#   lib/tools/sync_context.sh <context> [canvas_sync.py args...]
#
# Examples:
#   lib/tools/sync_context.sh master --pull
#   lib/tools/sync_context.sh blueprint --pull
#   lib/tools/sync_context.sh s1 --status
#   lib/tools/sync_context.sh s2 --update "sprint-1"
#   lib/tools/sync_context.sh master --build
#
# Context → .env variable mapping:
#   master    → MASTER_COURSE_ID
#   blueprint → BLUEPRINT_COURSE_ID
#   s1, s2... → S1_COURSE_ID, S2_COURSE_ID, ...
#
# The script:
#   1. Loads .env from the repo root
#   2. Resolves the course ID for the requested context
#   3. Creates the context folder if missing (master/, s1/, etc.)
#   4. cd's into the context folder so all CWD-relative paths in
#      canvas_sync.py (course/, course_src/, .canvas/) resolve there
#   5. Invokes canvas_sync.py with CANVAS_COURSE_ID set to the chosen course
#
# canvas_sync.py is unchanged — it just runs in whatever directory we cd to.

set -euo pipefail

# Resolve repo root (grandparent of this script: lib/tools/ → lib/ → root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"
SYNC_SCRIPT="$REPO_ROOT/lib/tools/canvas_sync.py"

# --- Validate environment ---

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: .env not found at $ENV_FILE" >&2
    echo "Copy .env.example to .env and fill in your course IDs." >&2
    exit 1
fi

if [ ! -f "$SYNC_SCRIPT" ]; then
    echo "ERROR: canvas_sync.py not found at $SYNC_SCRIPT" >&2
    exit 1
fi

if [ -z "${1:-}" ]; then
    cat >&2 <<EOF
Usage: $(basename "$0") <context> [canvas_sync.py args...]

Contexts:
  master       Master template course
  blueprint    Canvas Blueprint course (for online programs)
  s1, s2, ...  Per-section live courses for the current semester

Examples:
  $(basename "$0") master --pull
  $(basename "$0") s1 --status
  $(basename "$0") s2 --update "sprint-1"

See AGENTS.md "Multi-course architecture" for details.
EOF
    exit 1
fi

# --- Load .env into environment so we can read the right course ID ---

set -a  # export every variable assigned from now on
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# --- Resolve context → course ID ---

CONTEXT="$1"
shift  # remaining args go to canvas_sync.py

case "$CONTEXT" in
    master)
        VAR_NAME="MASTER_COURSE_ID"
        ;;
    blueprint)
        VAR_NAME="BLUEPRINT_COURSE_ID"
        ;;
    s[1-9]|s[1-9][0-9])
        VAR_NAME="$(echo "$CONTEXT" | tr '[:lower:]' '[:upper:]')_COURSE_ID"
        ;;
    *)
        echo "ERROR: Unknown context '$CONTEXT'" >&2
        echo "Valid contexts: master, blueprint, s1, s2, s3, ..." >&2
        exit 1
        ;;
esac

COURSE_ID="${!VAR_NAME:-}"

if [ -z "$COURSE_ID" ]; then
    echo "ERROR: $VAR_NAME is not set in $ENV_FILE" >&2
    echo "Add it to .env to use the '$CONTEXT' context." >&2
    exit 1
fi

# --- Set up context folder and dispatch ---

CONTEXT_DIR="$REPO_ROOT/$CONTEXT"
mkdir -p "$CONTEXT_DIR"

echo "→ canvas_sync.py [$CONTEXT] (course $COURSE_ID)"
echo "  Working dir: $CONTEXT_DIR"
echo

cd "$CONTEXT_DIR"
CANVAS_COURSE_ID="$COURSE_ID" exec uv run python "$SYNC_SCRIPT" "$@"
