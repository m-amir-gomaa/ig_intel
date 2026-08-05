@echo off
rem instaScript launcher — Windows. Runs the project venv python.
setlocal
set "ROOT=%~dp0.."
set "PYTHONPATH=%ROOT%"
"%ROOT%\.venv\Scripts\python.exe" -m instascript %*
