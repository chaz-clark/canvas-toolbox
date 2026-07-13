# Canvas access boundary - the faculty-facing menu. A plain script. No AI involved.
#
# WHY THIS EXISTS
#   The security model is unchanged: a plain script talks to Canvas, the
#   instructor runs it, and no AI tool holds the Canvas token. But the CLI asks
#   an instructor to remember `--confirm-course <id> --allow-enrolled`, and
#   faculty who don't live in a terminal reasonably bounce off that.
#
#   The answer is NOT to let an AI agent run the command - that would hand the
#   Canvas credential to an AI vendor and undermine the very assurance the boundary exists to give. The answer
#   is to make it trivial for the HUMAN to run it. That's this file.
#
#   Everything here is presentation. Every guard still lives in
#   lib/tools/canvas_run.py: the allowlist, the write confirmation, the enrolled-
#   course guard, the token injection, the audit log. This script cannot do
#   anything the CLI could not; it just types the flags for you after asking, in
#   English, whether you meant it.
#
# ASCII ONLY, DELIBERATELY.
#   Windows PowerShell 5.1 reads a BOM-less file as Windows-1252, so a UTF-8 em
#   dash decodes into a trailing smart quote - which PowerShell accepts as a
#   string delimiter, terminating the string early and breaking the whole script.
#   Faculty machines vary; do not reintroduce non-ASCII characters here.
#
# See docs/canvas-access-boundary.md.
#Requires -Version 5.1

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

function Read-DotEnv {
    param([string]$Path)
    $map = @{}
    if (Test-Path $Path) {
        foreach ($line in (Get-Content $Path -Encoding UTF8)) {
            $t = $line.Trim()
            if ($t -eq "" -or $t.StartsWith("#") -or -not $t.Contains("=")) { continue }
            $k, $v = $t.Split("=", 2)
            $map[$k.Trim()] = $v.Trim().Trim('"').Trim("'")
        }
    }
    return $map
}

# The course NAME is the guard that matters to a human. A stale .env pointing at
# the wrong course id is invisible (111111 vs 111112); a wrong course NAME is not.
# (canvas_api_lessons_learned L12.)
function Get-CourseName {
    param([string]$Repo)
    $idx = Join-Path $Repo ".canvas\index.json"
    if (-not (Test-Path $idx)) { return $null }
    try {
        $j = Get-Content $idx -Raw -Encoding UTF8 | ConvertFrom-Json
        return $j.course.name
    } catch { return $null }
}

# Runs the gate and returns its exit code.
#
# `| Out-Host` is load-bearing, not decoration. Without it, PowerShell captures
# the function's entire output stream into the caller's `$code = Invoke-Gate ...`
# — so the TOOL'S OWN OUTPUT gets swallowed into the variable instead of shown.
# The symptom is brutal for faculty: option 2 ("see what would change") printed
# nothing at all, because the only thing that reached the screen was the guard's
# stderr warning. Out-Host writes straight to the console, leaving only the exit
# code as the function's return value.
function Invoke-Gate {
    param([string[]]$GateArgs)
    Push-Location $repo
    try {
        Write-Host ""
        Write-Host ("  > canvas_run.py " + ($GateArgs -join " ")) -ForegroundColor DarkGray
        Write-Host ""
        & uv run python lib/tools/canvas_run.py @GateArgs | Out-Host
        return $LASTEXITCODE
    } finally { Pop-Location }
}

function Pause-ForUser {
    Write-Host ""
    Write-Host "  Press Enter to return to the menu..." -ForegroundColor DarkGray
    [void](Read-Host)
}

$envMap   = Read-DotEnv (Join-Path $repo ".env")
$courseId = $envMap["CANVAS_COURSE_ID"]
$baseUrl  = $envMap["CANVAS_BASE_URL"]
$name     = Get-CourseName $repo

if (-not $courseId) {
    Write-Host ""
    Write-Host "  No CANVAS_COURSE_ID found in .env - nothing to talk to." -ForegroundColor Red
    Write-Host "  Ask whoever set this repo up, or see docs/canvas-access-boundary.md."
    Pause-ForUser
    exit 2
}

while ($true) {
    Clear-Host
    Write-Host ""
    Write-Host "  ============================================================"
    Write-Host "   CANVAS" -ForegroundColor Cyan -NoNewline
    Write-Host "  -  this is the only thing that talks to Canvas."
    Write-Host "  ============================================================"
    Write-Host ""
    if ($name) {
        Write-Host "   Course:  " -NoNewline
        Write-Host $name -ForegroundColor Yellow
    } else {
        Write-Host "   Course:  (not downloaded yet - choose 1 first)"
    }
    Write-Host "   ID:      $courseId          $baseUrl"
    Write-Host ""
    Write-Host "   Is that the right course? If not, STOP and ask for help." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  ------------------------------------------------------------"
    Write-Host ""
    Write-Host "    1.  Get the latest from Canvas       " -NoNewline
    Write-Host "(safe - read only)" -ForegroundColor DarkGray
    Write-Host "    2.  See what would change in Canvas  " -NoNewline
    Write-Host "(safe - read only)" -ForegroundColor DarkGray
    Write-Host "    3.  Check the course for problems    " -NoNewline
    Write-Host "(safe - read only)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "    4.  SEND my changes to Canvas        " -NoNewline -ForegroundColor Red
    Write-Host "(students see this immediately)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "    Q.  Quit"
    Write-Host ""
    $choice = (Read-Host "   Choose 1, 2, 3, 4 or Q").Trim().ToUpper()

    switch ($choice) {

        "1" {
            Write-Host ""
            Write-Host "  Getting the latest copy of the course from Canvas..." -ForegroundColor Cyan
            $code = Invoke-Gate @("pull")
            Write-Host ""
            if ($code -eq 0) {
                Write-Host "  Done. The course is now on this computer, in the 'course' folder." -ForegroundColor Green
                Write-Host "  Nothing in Canvas was changed."
            } else {
                Write-Host "  That did not finish. Nothing in Canvas was changed." -ForegroundColor Red
            }
            Pause-ForUser
        }

        "2" {
            Write-Host ""
            Write-Host "  Comparing your copy against Canvas..." -ForegroundColor Cyan
            $code = Invoke-Gate @("status")
            Write-Host ""
            Write-Host "  Nothing was sent to Canvas - this only looks." -ForegroundColor Green
            Pause-ForUser
        }

        "3" {
            Write-Host ""
            Write-Host "  Checking the course. This takes a minute..." -ForegroundColor Cyan
            $code = Invoke-Gate @("audit")
            Write-Host ""
            if ($code -le 1) {
                Write-Host "  Done. The report is in 'audit.md' - open it in any editor." -ForegroundColor Green
            }
            Write-Host "  Nothing in Canvas was changed."
            Pause-ForUser
        }

        "4" {
            Write-Host ""
            Write-Host "  ============================================================" -ForegroundColor Red
            Write-Host "   THIS WRITES TO THE LIVE COURSE" -ForegroundColor Red
            Write-Host "  ============================================================" -ForegroundColor Red
            Write-Host ""
            Write-Host "   Canvas has no draft mode. Whatever you send goes live"
            Write-Host "   immediately, and enrolled students can see it at once."
            Write-Host "   There is no undo."
            Write-Host ""
            Write-Host "   First, here is exactly what would be sent:" -ForegroundColor Cyan

            $code = Invoke-Gate @("status")

            Write-Host ""
            Write-Host "  ------------------------------------------------------------"
            Write-Host ""
            if ($name) {
                Write-Host "   Sending to:  " -NoNewline
                Write-Host "$name ($courseId)" -ForegroundColor Yellow
            } else {
                Write-Host "   Sending to:  course $courseId" -ForegroundColor Yellow
            }
            Write-Host ""
            Write-Host "   If the list above is not exactly what you meant to change,"
            Write-Host "   type anything else to cancel."
            Write-Host ""
            $confirm = (Read-Host "   Type SEND to publish these changes to Canvas").Trim()

            if ($confirm -cne "SEND") {
                Write-Host ""
                Write-Host "  Cancelled. Nothing was sent to Canvas." -ForegroundColor Green
                Pause-ForUser
                continue
            }

            Write-Host ""
            Write-Host "  Sending..." -ForegroundColor Cyan
            # Both flags the gate requires. The typed SEND above is the human
            # equivalent - the flags are not skipped, just not memorized.
            $code = Invoke-Gate @("push", "--confirm-course", $courseId, "--allow-enrolled")
            Write-Host ""
            if ($code -eq 0) {
                Write-Host "  Sent. Your changes are live in Canvas now." -ForegroundColor Green
                Write-Host "  Open the course in a browser to confirm it looks right."
            } else {
                Write-Host "  That did not complete. Read the messages above." -ForegroundColor Red
                Write-Host "  Some changes may have been sent before it stopped - check Canvas."
            }
            Pause-ForUser
        }

        "Q" { Write-Host ""; Write-Host "  Bye."; Write-Host ""; exit 0 }

        default {
            Write-Host ""
            Write-Host "  Did not catch that - please type 1, 2, 3, 4 or Q." -ForegroundColor Yellow
            Start-Sleep -Seconds 1
        }
    }
}
