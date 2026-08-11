@echo off
rem Double-click to play STEAMWARD. Starts the local server (the game cannot
rem run from file:// because it uses ES modules) and opens the browser once
rem the server answers. Close this window to stop the server.
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is required. Install it from https://nodejs.org and run this again.
  pause
  exit /b 1
)

rem Open the browser as soon as the port answers (works whether this window's
rem server wins the port or one is already running).
start "" powershell -NoProfile -Command "for($i=0;$i -lt 60;$i++){try{$c=New-Object Net.Sockets.TcpClient('localhost',8123);$c.Close();break}catch{Start-Sleep -Milliseconds 250}};Start-Process 'http://localhost:8123'"

echo Serving STEAMWARD on http://localhost:8123 — close this window to stop.
node tools\serve.mjs
pause
