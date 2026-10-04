ClipForge v28 - public website edition

NEW
- Multi-user server: unguessable job links (128-bit), FIFO queue with "your position", per-IP hourly limit,
  upload size / video length / clip count limits, disk-space guard, YouTube-only URL allow-list
  (lookalike hosts and file:// rejected), real-video validation of uploads.
- Privacy: source video deleted right after processing, results auto-deleted after CLIPFORGE_TTL_HOURS,
  "delete my files now" button, no server paths in the API, user's Groq key never stored on the server.
- Results: ZIP of all clips, seekable video (Range), download buttons, resume after page refresh.
- UI: upload progress, rights/terms checkbox, /legal page, local compiled CSS (no CDN), limits shown to visitors.
- Deploy: Dockerfile, docker-compose.yml (+Caddy automatic HTTPS), .env.example, DEPLOY_AR.md.
- Still runs on your PC exactly like before (run_clipforge.bat): public limits are OFF unless CLIPFORGE_PUBLIC=1.

TESTED (sandbox, real FFmpeg rendering; Groq/YouTube calls stubbed - no network there)
validation + security checks, full job -> clips -> zip -> Range download -> delete, FIFO queue, rate limit (429),
oversize upload (413), restart persistence, TTL cleanup, UI JavaScript syntax.
NOT TESTED: Docker build, real YouTube download from a server, real Groq calls through the new server, browser UI clicks.
