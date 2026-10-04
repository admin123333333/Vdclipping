ClipForge v20 - speed release
- Download capped at 1080p and prefers H.264 (YouTube's 4K VP9/AV1 is extremely slow to decode/crop). CLIPFORGE_MAX_HEIGHT=720 for even faster.
- Output defaults to 720p (9:16 = 720x1280). Set CLIPFORGE_RES=1080 for full HD.
- x264 ultrafast + crf 23; NVENC (GPU) used automatically when available. CLIPFORGE_GPU_ENCODE=0 to disable.
- Face tracking uses one multi-threaded FFmpeg pass instead of decoding every frame in OpenCV.

- Local transcription now logs model/device and progress with ETA (every 10%).
- Shorter API/translation timeouts so a slow connection cannot stall a stage.
- Download: live progress/speed in the log, per-attempt messages, chunked + parallel fragment download to avoid YouTube throttling.
- Download now runs yt-dlp as a killable subprocess: live output in the log, auto-kill after 120s without output (CLIPFORGE_STALL_SECONDS), next fallback is tried. Job log is also printed in the CMD window.
- Anti-throttling download: aria2c (16 connections, auto-installed via winget), IPv4, speed watchdog that kills slow attempts (<400 KB/s) and switches strategy/player client.
- Whisper: if CUDA is detected but its DLLs (cublas64_12.dll) are missing, automatically falls back to CPU (CLIPFORGE_DEVICE=cpu forces CPU).
