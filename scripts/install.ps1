# canvas-toolbox installer for Windows (PowerShell) — Sprint top-stars-sweep v0.57.0
#
# One-line install:
#
#   irm https://raw.githubusercontent.com/chaz-clark/canvas-toolbox/main/scripts/install.ps1 | iex
#
# Mirrors scripts/install.sh for the macOS/Linux side. What this does:
#   1. Ensures Git is on PATH (required; not auto-installed — install Git
#      for Windows manually from https://git-scm.com/download/win first)
#   2. Installs uv via Astral's official PowerShell installer if missing
#   3. Clones canvas-toolbox into .\canvas-toolbox under the current dir
#      (override via $env:CLONE_DIR)
#   4. Runs `cb-init --yes` from inside the clone — auto-accepts all
#      prompts (curl-pipe / irm-pipe invocations have no TTY anyway)
#   5. Reports whether to fill in .env (cb-init halt-at-step-3 case)
#      or that the install is fully complete (all 8 steps ran)
#
# Idempotent: refuses to clobber a pre-existing canvas-toolbox\ dir;
# prints a recovery hint pointing at `cd canvas-toolbox; uv run python
# lib/tools/cb_init.py` (the resume path).
#
# Test mode (no clone, no uv install, no cb-init — for dry-run validation):
#
#   $env:CANVAS_TOOLBOX_INSTALL_DRY_RUN = "1"; .\scripts\install.ps1

$ErrorActionPreference = "Stop"

# Config
$Repo = "chaz-clark/canvas-toolbox"
$RepoUrl = "https://github.com/$Repo.git"
$CloneDir = if ($env:CLONE_DIR) { $env:CLONE_DIR } else { "canvas-toolbox" }
$DryRun = $env:CANVAS_TOOLBOX_INSTALL_DRY_RUN -eq "1"

function Info($msg)  { Write-Host $msg -ForegroundColor Green }
function Warn($msg)  { Write-Host $msg -ForegroundColor Yellow }
function Die($msg)   { Write-Host $msg -ForegroundColor Red; exit 1 }


# --- Dependency checks ---

function Ensure-Git {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        $version = (git --version) -replace 'git version ', ''
        Info "✓ git $version already installed."
        return
    }
    Die "git is required but not on PATH. Install Git for Windows: https://git-scm.com/download/win"
}

function Ensure-Uv {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        $version = (uv --version)
        Info "✓ $version already installed."
        return
    }
    if ($DryRun) {
        Info "[dry-run] would install uv via Astral's official installer"
        return
    }
    Info "Installing uv via Astral's official installer..."
    irm https://astral.sh/uv/install.ps1 | iex

    # Astral's installer updates PATH via the registry, but this session
    # doesn't pick it up automatically. Add the standard install location
    # to PATH for this process.
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uv) {
        Die "uv installer ran, but uv is still not on PATH. Open a new PowerShell session and re-run."
    }
    Info "✓ uv installed."
}


# --- Clone ---

function Clone-Repo {
    if (Test-Path $CloneDir) {
        Warn "Directory '$CloneDir' already exists."
        Warn ""
        Warn "If this is an existing canvas-toolbox clone, resume setup with:"
        Warn "  cd $CloneDir; uv run python lib/tools/cb_init.py"
        Warn ""
        Warn "Or remove + reinstall:"
        Warn "  Remove-Item -Recurse -Force $CloneDir"
        Warn "  irm https://raw.githubusercontent.com/$Repo/main/scripts/install.ps1 | iex"
        exit 1
    }
    if ($DryRun) {
        Info "[dry-run] would clone $RepoUrl into .\$CloneDir"
        return
    }
    Info "Cloning canvas-toolbox into .\$CloneDir..."
    git clone --depth=1 $RepoUrl $CloneDir
    Info "✓ Cloned."
}


# --- Run cb-init ---

function Run-CbInit {
    if ($DryRun) {
        Info "[dry-run] would cd $CloneDir; uv run python lib/tools/cb_init.py --yes"
        return $true
    }
    Push-Location $CloneDir
    try {
        Info ""
        Info "Running cb-init (auto-accepting prompts via --yes)..."
        Info ""
        # cb-init exit codes:
        #   0  setup complete (every needed step ran successfully)
        #   1  setup stopped (wrote .env stub at step 3; operator fills in)
        # Both are valid outcomes; main() branches on the exit code.
        uv run python lib/tools/cb_init.py --yes
        return ($LASTEXITCODE -eq 0)
    } finally {
        # Note: we DON'T Pop-Location on success because the user wants
        # to end up inside the cloned dir for the "edit .env" follow-up.
        if ($DryRun) { Pop-Location }
    }
}


# --- Main ---

Info "==========================================="
Info "canvas-toolbox installer (os: windows)"
Info "==========================================="
if ($DryRun) { Info "[dry-run mode - no real installs or clones]" }
Info ""

Ensure-Git
Ensure-Uv
Clone-Repo
$cbInitSuccess = Run-CbInit

Info ""
Info "==========================================="
if ($cbInitSuccess) {
    Info "✓ canvas-toolbox installed and fully configured."
    Info ""
    Info "Try:"
    Info "  cd $CloneDir"
    Info "  uv run python lib/tools/course_audit.py --help"
} else {
    Info "✓ canvas-toolbox installed at $(Get-Location)"
    Info ""
    Info "Next:"
    Info "  1. Edit .env - fill in CANVAS_API_TOKEN + CANVAS_BASE_URL"
    Info "     (Canvas -> Account -> Settings -> New Access Token)"
    Info "  2. Continue setup:"
    Info "       uv run python lib/tools/cb_init.py"
}
Info "==========================================="
