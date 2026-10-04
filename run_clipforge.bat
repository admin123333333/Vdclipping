@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "CLIPFORGE_DEVICE=auto"
cd /d "%~dp0"
title ClipForge Server

where py >nul 2>&1
if %errorlevel%==0 (set "PY=py -3") else (
  where python >nul 2>&1
  if %errorlevel%==0 (set "PY=python") else (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
  )
)

echo ========================================
echo          ClipForge - Starting v28 GPU
echo ========================================
echo.

echo Checking Deno...
where deno >nul 2>&1
if %errorlevel% neq 0 (
  if exist "%USERPROFILE%\.deno\bin\deno.exe" (
    set "PATH=%USERPROFILE%\.deno\bin;!PATH!"
  ) else (
    echo Deno was not found. Installing with winget...
    where winget >nul 2>&1
    if %errorlevel% neq 0 (
      echo [ERROR] winget is not available. Install Deno manually from https://deno.com/
      pause
      exit /b 1
    )
    winget install --id DenoLand.Deno -e --accept-source-agreements --accept-package-agreements
    if exist "%USERPROFILE%\.deno\bin\deno.exe" set "PATH=%USERPROFILE%\.deno\bin;!PATH!"
  )
)

where deno >nul 2>&1
if %errorlevel% neq 0 (
  echo [ERROR] Deno is still not visible.
  echo Try closing this window and opening a new CMD, then run this file again.
  pause
  exit /b 1
)
for /f "delims=" %%D in ('where deno') do set "DENO_PATH=%%D"
echo Deno: !DENO_PATH!
"!DENO_PATH!" --version
if errorlevel 1 (
  echo [ERROR] Deno exists but cannot be executed.
  pause
  exit /b 1
)

echo.
echo Checking aria2c (fast multi-connection download, avoids YouTube throttling)...
where aria2c >nul 2>&1
if errorlevel 1 (
  if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\aria2c.exe" (
    set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;!PATH!"
  ) else (
    where winget >nul 2>&1
    if not errorlevel 1 (
      echo Installing aria2 with winget...
      winget install --id aria2.aria2 -e --accept-source-agreements --accept-package-agreements
      if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\aria2c.exe" set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;!PATH!"
    ) else (
      echo [WARN] winget not available - install aria2 manually for faster downloads.
    )
  )
)

echo.
echo Installing/updating Python packages...
%PY% -m pip install "yt-dlp[default]" requests Flask imageio-ffmpeg faster-whisper numpy opencv-python-headless
if errorlevel 1 goto INSTALL_ERROR

echo Installing NVIDIA CUDA runtime libraries for faster-whisper GPU...
%PY% -m pip install "nvidia-cublas-cu12" "nvidia-cudnn-cu12>=9,<10" "nvidia-cuda-nvrtc-cu12"

if errorlevel 1 goto INSTALL_ERROR

%PY% -c "import yt_dlp, yt_dlp_ejs; print('yt-dlp:', yt_dlp.version.__version__); print('yt-dlp-ejs: OK')"
if errorlevel 1 goto INSTALL_ERROR

echo.
echo Starting server on http://127.0.0.1:5000 ...
echo Keep this window OPEN while using ClipForge.
echo.
start "" http://127.0.0.1:5000
rem Whisper model: small/int8_float16 on NVIDIA GPU (auto-falls back to base), base/int8 on CPU.
rem Captions: CLIPFORGE_CAPTION_OFFSET=-0.1 (earlier) / 0.1 (later)   Quality: CLIPFORGE_CRF=18  CLIPFORGE_RES=720|1080  CLIPFORGE_MAX_HEIGHT=1440
rem Reframe: CLIPFORGE_REFRAME=fit (whole frame, default) or fill (face-tracking crop)
rem Graphics: CLIPFORGE_GRAPHICS=0 (off)  CLIPFORGE_SFX=0 (no sound effects)  CLIPFORGE_CHANNEL=@yourchannel (shown on the follow card)
rem Picking: CLIPFORGE_NICHE="your content description"  CLIPFORGE_PROMPT="UFC, MMA, fighter names..." (helps Whisper spell names)
rem Download: CLIPFORGE_MIN_KBPS=400 (switch strategy below this speed)  CLIPFORGE_ARIA2=0 (disable aria2c)  CLIPFORGE_IPV6=1
rem Speed: CLIPFORGE_RES=1080 (full HD, slower)  CLIPFORGE_MAX_HEIGHT=720  CLIPFORGE_GPU_ENCODE=0
rem Optional overrides: CLIPFORGE_WHISPER_MODEL=small  CLIPFORGE_PRESET=ultrafast  CLIPFORGE_RENDER_WORKERS=2
%PY% app.py

pause
exit /b 0

:INSTALL_ERROR
echo.
echo [ERROR] Package installation failed.
pause
exit /b 1
