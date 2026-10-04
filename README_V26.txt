ClipForge v26 - professional motion graphics

Added automatically to every clip (checkbox in the UI, on by default):
- Punch-in zoom on key moments: words like knockout / submission / robbed (CLIPFORGE_BOOST_REGEX) and the loudest audio peaks (crowd, shouting). Max 4 per clip, at least 4 s apart.
- Slow push-in over the whole clip + a quick "settle" zoom at the start.
- Hook title pops in (overshoot), with a red accent bar wiping in below it.
- White flash on the first frames, thin red progress bar on the top edge.
- Key words in the captions turn red; each caption phrase "pops" when it appears.
- Last 2.4 s: red "FOLLOW FOR MORE" card slides in. Set CLIPFORGE_CHANNEL=@yourchannel to show your handle.
- Sound effects, synthesized locally (no downloads, no copyright): whoosh on the hook and on the card, bass impact on each punch-in. Fade-out on picture and sound at the end.

Switches (in run_clipforge.bat):
  CLIPFORGE_GRAPHICS=0   everything off (or untick the box in the UI)
  CLIPFORGE_SFX=0        keep visuals, no sound effects
  CLIPFORGE_CHANNEL=@name  your handle on the follow card

Notes
- If your FFmpeg does not support a sound-effects filter, the clip is rendered again automatically without sound effects (visuals stay).
- Rendering is a bit slower because of the animated zoom. CLIPFORGE_RES=720 speeds it up.
