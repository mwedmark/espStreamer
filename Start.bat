@echo off
setlocal enabledelayedexpansion

echo [.] Cleaning up old processes...
taskkill /f /im vlc.exe >nul 2>&1
taskkill /f /im python.exe >nul 2>&1

:: --- VLC Discovery Block ---
echo [.] Locating VLC Media Player...
set "VLC=vlc.exe"
where vlc.exe >nul 2>&1
if !errorlevel! neq 0 (
    if exist "C:\Program Files\VideoLAN\VLC\vlc.exe" (
        set "VLC=C:\Program Files\VideoLAN\VLC\vlc.exe"
    ) else if exist "C:\Program Files (x86)\VideoLAN\VLC\vlc.exe" (
        set "VLC=C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"
    ) else (
        echo [!] ERROR: VLC could not be found. 
        echo Please ensure VLC is installed or add its folder to your System PATH.
        pause
        exit /b 1
    )
)
echo [+] Found VLC: "!VLC!"

:: --- Resolution Detection ---
echo [.] Detecting Physical Screen Resolution...
for /f %%a in ('powershell -command "(Get-CimInstance Win32_VideoController | Where-Object { $_.CurrentHorizontalResolution -gt 0 } | Select-Object -First 1).CurrentHorizontalResolution"') do set SCREEN_W=%%a
for /f %%a in ('powershell -command "(Get-CimInstance Win32_VideoController | Where-Object { $_.CurrentVerticalResolution -gt 0 } | Select-Object -First 1).CurrentVerticalResolution"') do set SCREEN_H=%%a
echo [+] Hardware Resolution: %SCREEN_W% x %SCREEN_H%

:: --- Start VLC Capture ---
echo [.] Starting VLC Capture (Indestructible Mode)...
:: Standardize flags: :screen-top/left=0 to target primary display and fix black screen issues.
start /b "" "!VLC!" screen:// :screen-fps=20 :screen-caching=0 :live-caching=0 :screen-top=0 :screen-left=0 :sout=#transcode{vcodec=mjpg,vb=2000,width=320,height=200,fps=20}:standard{access=http,mux=mpjpeg,dst=:90/pc.mjpg} :sout-keep

:: --- Validation ---
timeout /t 2 /nobreak > nul
tasklist /fi "IMAGENAME eq vlc.exe" | find /i "vlc.exe" > nul
if !errorlevel! neq 0 (
    echo [!] WARNING: VLC failed to start. Port 90 might be blocked or display capture is restricted.
) else (
    echo [+] VLC capture process detected.
)

:: --- Start Proxy ---
echo [.] Starting Local CORS Proxy via Python...
start /b cmd /c "python tools\cors_proxy.py"

:: Give the proxy time to bind
echo [.] Waiting for server to initialize...
timeout /t 3 /nobreak > nul

echo [.] Launching User Interface at http://localhost:8080 ...
start http://localhost:8080/index.html

echo.
echo [+] ESPStreamer is now running!
echo [!] Keep this window open to maintain the stream and proxy.
echo [!] If screen is still black, check if VLC needs Administrator permissions.
echo.
pause
