ClipForge v25 - captions, clip quality, better clip picking

CAPTIONS
- Translation is done on short fragments (max 9 words, split on pauses/commas) and the English words are timed by word length, not evenly -> far less drift.
- Phrases are short (4 words in 9:16), one phrase on screen at a time, a word is never highlighted for less than 0.11 s.
- Whisper: GPU default is now "small" (auto-falls back to "base" if VRAM is not enough), beam search 3, VAD padding so first words are not clipped. CPU default is "base".
- If captions still look early/late: set CLIPFORGE_CAPTION_OFFSET=-0.1 (earlier) or 0.1 (later) in run_clipforge.bat.
- For fighter names: set CLIPFORGE_PROMPT=UFC, MMA, <names...> (helps Whisper spell names; best when the video is English).

VIDEO QUALITY
- Output is 1080x1920 by default (was 720x1280). CLIPFORGE_RES=720 for faster renders.
- x264 crf 18 (was 23, ultrafast) / NVENC high-quality preset with cq 18. Max 16 Mbps, audio 192k @ 48 kHz.
- Light sharpen after upscaling the 9:16 crop; face detection at higher resolution; steadier virtual camera.
- Loudness normalised to -14 LUFS (CLIPFORGE_LOUDNORM=0 disables).
- A 9:16 crop of a 1080p video is only ~608 px wide. For sharper results set CLIPFORGE_MAX_HEIGHT=1440 (bigger download, slower decode).

CLIP PICKING
- AI is asked for ~2.5x more candidates, then re-ranked locally: audio score (average loudness + loudest 3 s burst = crowd roar / shouting) up to +-1.25, plus keyword bonus (knockout, submission, robbed, callout...). Override with CLIPFORGE_BOOST_REGEX.
- Prompt focuses on UFC/MMA (CLIPFORGE_NICHE to change), starts 1-2 sentences before the key moment and ends right after the payoff. Clips 20-50 s.
- Less overlap allowed between clips; padding 0.3 s before / 0.5 s after.
- Without a Groq key the loudest-burst windows are used.
