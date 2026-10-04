ClipForge v13

Fixes the PyAV/faster-whisper error:
open() got an unexpected keyword argument "metadata_errors"

The local transcription path converts the video to mono 16 kHz PCM WAV with FFmpeg,
then loads that WAV with Python's standard wave module into a float32 NumPy array.
That array is passed directly to faster-whisper, so faster-whisper does not call
PyAV's av.open() and does not use the incompatible metadata_errors argument.

Run run_clipforge.bat from this folder.
