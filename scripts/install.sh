#!/usr/bin/env bash
# canvas-toolbox installer — Sprint 2B (issue B2 / built atop Sprint 2's cb-init)
#
# One-line install for macOS / Linux:
#
#   curl -fsSL https://raw.githubusercontent.com/chaz-clark/canvas-toolbox/main/scripts/install.sh | bash
#
# What this does:
#   1. Detects OS (macOS or Linux; bails on Windows with a pointer to the
#      manual 3-line flow in the README)
#   2. Ensures `git` is on PATH (required; not auto-installed — Xcode CLT
#      / system package manager handles git)
#   3. Installs `uv` via Astral's official installer if not present
#   4. Clones canvas-toolbox into ./canvas-toolbox under the current dir
#      (or wherever CLONE_DIR points)
#   5. Runs `cb-init --yes` from inside the clone — auto-accepts all
#      prompts (a curl-pipe invocation has no TTY for interactive
#      prompts anyway; non-interactive is the point of this script)
#   6. Reports whether to fill in `.env` (cb-init halt-at-step-3 case)
#      or that the install is fully complete (all 8 steps ran)
#
# Idempotent: re-running against an existing canvas-toolbox/ dir bails
# with a clear message pointing at `cd canvas-toolbox && uv run python
# lib/tools/cb_init.py` (the resume path).
#
# Windows users: skip this script. Use the 3-line manual flow in the
# README (Option B → Fast path) which works in PowerShell.
#
# Local test (without curl):
#
#   ./scripts/install.sh
#
# Test mode (no clone, no uv install, no cb-init — for CI / unit tests):
#
#   CANVAS_TOOLBOX_INSTALL_DRY_RUN=1 ./scripts/install.sh

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────
REPO="chaz-clark/canvas-toolbox"
REPO_URL="https://github.com/${REPO}.git"
CLONE_DIR="${CLONE_DIR:-canvas-toolbox}"
DRY_RUN="${CANVAS_TOOLBOX_INSTALL_DRY_RUN:-0}"

# Colors — only emit when stdout is a TTY (skips junk in piped logs / CI)
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[1;33m'
    NC='\033[0m'
else
    GREEN=''
    RED=''
    YELLOW=''
    NC=''
fi

info()  { printf "%b%s%b\n" "$GREEN" "$*" "$NC"; }
warn()  { printf "%b%s%b\n" "$YELLOW" "$*" "$NC"; }
err()   { printf "%b%s%b\n" "$RED" "$*" "$NC" >&2; }
die()   { err "$*"; exit 1; }


# ──────────────────────────────────────────────────────────────────────
# OS detection
# ──────────────────────────────────────────────────────────────────────
detect_os() {
    case "$(uname -s)" in
        Darwin) echo "macos" ;;
        Linux)  echo "linux" ;;
        MINGW*|MSYS*|CYGWIN*)
            die "Windows is not supported by install.sh. Use the 3-line manual flow in the README (Option B → Fast path)."
            ;;
        *)
            die "Unsupported OS: $(uname -s). install.sh supports macOS + Linux only."
            ;;
    esac
}


# ──────────────────────────────────────────────────────────────────────
# Dependency checks
# ──────────────────────────────────────────────────────────────────────
ensure_git() {
    if command -v git >/dev/null 2>&1; then
        info "✓ git $(git --version 2>&1 | awk '{print $3}') already installed."
        return
    fi
    die "git is required but not on PATH. Install it first: https://git-scm.com/downloads"
}

ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        info "✓ uv $(uv --version 2>&1) already installed."
        return
    fi
    if [ "$DRY_RUN" = "1" ]; then
        info "[dry-run] would install uv via Astral's official installer"
        return
    fi
    info "Installing uv via Astral's official installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Astral's installer adds uv to PATH via shell-rc; this script's shell
    # won't pick it up automatically. Add the standard install location
    # for THIS process.
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    if ! command -v uv >/dev/null 2>&1; then
        die "uv installer ran, but uv is still not on PATH. Open a new terminal and re-run, OR \`source ~/.zshrc\` / \`source ~/.bashrc\` first."
    fi
    info "✓ uv installed."
}


# ──────────────────────────────────────────────────────────────────────
# Clone
# ──────────────────────────────────────────────────────────────────────
clone_repo() {
    if [ -e "$CLONE_DIR" ]; then
        warn "Directory '$CLONE_DIR' already exists."
        warn ""
        warn "If this is an existing canvas-toolbox clone, resume setup with:"
        warn "  cd $CLONE_DIR && uv run python lib/tools/cb_init.py"
        warn ""
        warn "Or remove + reinstall:"
        warn "  rm -rf $CLONE_DIR && bash install.sh"
        exit 1
    fi
    if [ "$DRY_RUN" = "1" ]; then
        info "[dry-run] would clone $REPO_URL into ./$CLONE_DIR"
        return
    fi
    info "Cloning canvas-toolbox into ./$CLONE_DIR..."
    git clone --depth=1 "$REPO_URL" "$CLONE_DIR"
    info "✓ Cloned."
}


# ──────────────────────────────────────────────────────────────────────
# Run cb-init
# ──────────────────────────────────────────────────────────────────────
run_cb_init() {
    if [ "$DRY_RUN" = "1" ]; then
        info "[dry-run] would cd $CLONE_DIR && uv run python lib/tools/cb_init.py --yes"
        return 0
    fi
    cd "$CLONE_DIR"
    info ""
    info "Running cb-init (auto-accepting prompts via --yes)..."
    info ""
    # cb-init exit codes:
    #   0  setup complete (every needed step ran successfully)
    #   1  setup stopped (e.g. wrote .env stub at step 3; operator fills in)
    # Both are valid outcomes here; the message at the end of install.sh
    # branches on the exit code.
    if uv run python lib/tools/cb_init.py --yes; then
        return 0
    fi
    return 1
}


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
main() {
    local os
    os=$(detect_os)
    info "==========================================="
    info "canvas-toolbox installer (os: $os)"
    info "==========================================="
    if [ "$DRY_RUN" = "1" ]; then
        info "[dry-run mode — no real installs or clones]"
    fi
    info ""

    ensure_git
    ensure_uv
    clone_repo

    local cb_init_status=0
    run_cb_init || cb_init_status=$?

    info ""
    info "==========================================="
    if [ "$cb_init_status" = "0" ]; then
        info "✓ canvas-toolbox installed and fully configured."
        info ""
        info "Try:"
        info "  cd $CLONE_DIR"
        info "  uv run python lib/tools/course_audit.py --help"
    else
        info "✓ canvas-toolbox installed at $(pwd)"
        info ""
        info "Next:"
        info "  1. Edit .env — fill in CANVAS_API_TOKEN + CANVAS_BASE_URL"
        info "     (Canvas → Account → Settings → New Access Token)"
        info "  2. Continue setup:"
        info "       uv run python lib/tools/cb_init.py"
    fi
    info "==========================================="
}

main "$@"
