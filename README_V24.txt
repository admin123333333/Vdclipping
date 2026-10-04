ClipForge v24 — NVIDIA MX450 GPU fix

Your NVIDIA GeForce MX450 is CUDA-capable. This version installs the CUDA 12 cuBLAS/cuDNN runtime wheels and registers their Windows DLL folders before CTranslate2/Faster-Whisper loads.

Default Whisper model: base, compute_type=int8_float16 on GPU (lower VRAM use).
CPU fallback: tiny/int8.

If you still see cublas64_12.dll, close all old ClipForge CMD windows and run this v24 run_clipforge.bat once so the NVIDIA wheels install.
