ClipForge v27 - full frame, no cropping, higher quality

PROBLEM (v26)
A 16:9 video was CROPPED to a 608 px wide strip and stretched to 1080 px -> 2/3 of the picture lost and soft/blurry.
The motion-graphics zoom then cropped it a second time.

FIX
- New default "Full frame" (CLIPFORGE_REFRAME=fit): the WHOLE original frame is kept at full width (1080 px for a
  1080p source = no upscaling, sharp), centred over a blurred + darkened copy of the same video. Nothing is cut.
  Old behaviour is still available: UI option "Fill screen - smart crop" or CLIPFORGE_REFRAME=fill.
- Motion graphics are applied to the video layer only, with a gentler zoom (max ~4% per side at a punch-in), so the
  sides are not lost. Hook title sits above the video, captions below it, red accent lines frame the video,
  progress bar on top, FOLLOW card at the bottom.
- Quality: x264 crf 16 / preset fast (was crf 18 / veryfast), NVENC cq 16, max 24 Mbps, lanczos scaling,
  BT.709 colour tags (no colour shift), light sharpen only if the source had to be upscaled.
- The job log now shows one line per clip, e.g. "full frame + motion graphics + sound effects | 4 zooms",
  and prints the real FFmpeg error if a render attempt fails, so you can see if graphics were applied.

TIPS
- Best sharpness: keep CLIPFORGE_MAX_HEIGHT=1080 (default) or 1440. Source below 1080p will be upscaled.
- Faster renders: CLIPFORGE_PRESET=veryfast or CLIPFORGE_RES=720.
