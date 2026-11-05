@echo off
rem Starts the agents, the emotion model and the web app for a local demo, without changing the system execution policy.
rem   start-all.bat           start everything     start-all.bat -Reset      restart the clock of the complaint cases
rem   start-all.bat -Clean    start from the clean demo state (rehearsal data is moved to a backup folder, not deleted)
rem   start-all.bat -Stop     stop everything
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-all.ps1" %*
pause
