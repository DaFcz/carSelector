@echo off
rem Prints a file/line-count summary of this repository's own Python
rem source, broken down by top-level directory. Thin wrapper around
rem statistics.py (in this same directory) - the actual scan logic and
rem its exclusion rules (venv/.git/caches) live there, see that script's
rem own module docstring.
rem
rem Requires the same Python environment the rest of this project uses
rem (the repo-root venv) - though statistics.py itself only needs the
rem standard library, so any Python 3.11+ on PATH works too.
rem Run from anywhere; paths resolve relative to this script's own
rem location, not the current directory. Any arguments are forwarded
rem as-is to statistics.py, e.g.:
rem   scripts\statistics.bat --path backend

python "%~dp0statistics.py" %*
exit /b %ERRORLEVEL%
