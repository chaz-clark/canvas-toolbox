@echo off
REM Canvas — double-click this file. No command line needed.
REM
REM This only launches bin\canvas-menu.ps1, which in turn only calls
REM lib\tools\canvas_run.py. All the security guards live there. See
REM docs\canvas-access-boundary.md.
title Canvas
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0canvas-menu.ps1"
if errorlevel 1 (
  echo.
  echo   Something went wrong starting the menu.
  echo   Ask for help, and mention docs\canvas-access-boundary.md.
  echo.
  pause
)
