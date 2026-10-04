ClipForge v11

This build fixes the local transcription crash:
open() got an unexpected keyword argument 'metadata_errors'
by converting the downloaded video to a 16 kHz WAV with FFmpeg before
passing the audio file to faster-whisper.

Start: double-click run_clipforge.bat
Then open: http://127.0.0.1:5000
Results: the results folder next to app.py.
