ClipForge v19
- Smart crop: 9:16 / 1:1 follows the main face (OpenCV) with a steady virtual camera; centred crop if no face; blurred background for narrow sources. No more black bars.
- AI highlights: timestamped transcript, hook-first criteria, snapped to sentence boundaries, 15-60s, no overlaps, loudness bonus, on-screen Hook title. Without a Groq key it picks the loudest moments.
- Captions stay in sync: translation per short segment (v18 spread 60s chunks). Active word highlighted, layout correct for every ratio.
- Speed: clips render in parallel, Whisper model is cached (GPU: large-v3-turbo, CPU: base), loudness analysis runs during transcription, stage timings in the log.
- Fixes: /files route crashed (<n> vs name), XSS in UI, server now binds to 127.0.0.1, API errors no longer kill the job.
