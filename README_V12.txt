ClipForge v12

This version fixes Groq highlight analysis after llama-3.3-70b-versatile became unavailable for many accounts.
It tries openai/gpt-oss-120b, then qwen/qwen3.8-27b. If neither is available, it automatically uses the built-in fallback highlight selection instead of failing the whole job.

Start with run_clipforge.bat.
