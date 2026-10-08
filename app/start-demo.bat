@echo off
rem Starts CallVerse (NestJS) and opens the browser, without changing the system execution policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-demo.ps1"
pause
