ClipForge v17

Speed improvements:
- Local Faster-Whisper defaults to the base model on CPU (override with CLIPFORGE_WHISPER_MODEL=small for higher accuracy).
- Whisper uses beam_size=1, best_of=1 and VAD to reduce CPU time.
- English translation uses 100-word batches and up to 4 concurrent requests instead of sequential 35-word requests.
- English captions use tighter 4-7 word phrases with improved mobile styling and timing.

The captions remain English-only. Results are saved under results/<job-id>/.
