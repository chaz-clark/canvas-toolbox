#!/usr/bin/env bash
# Canvas — double-click this file on a Mac. No Terminal knowledge needed.
#
# macOS runs a .command file in Terminal on double-click. This only launches
# bin/canvas-menu.sh, which only calls lib/tools/canvas_run.py. All the security
# guards live there. See docs/canvas-access-boundary.md.
#
# If double-clicking does nothing the first time, the file needs its execute bit:
#     chmod +x bin/Canvas.command bin/canvas-menu.sh
exec "$(cd "$(dirname "$0")" && pwd)/canvas-menu.sh"
