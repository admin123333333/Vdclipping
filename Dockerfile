FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 CLIPFORGE_PUBLIC=1 CLIPFORGE_DATA_DIR=/data PORT=8000

# fonts for burned-in captions (libass maps "Arial" to Liberation Sans), aria2 for fast downloads
RUN apt-get update && apt-get install -y --no-install-recommends \
        fontconfig fonts-liberation fonts-dejavu-core aria2 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Deno = JavaScript runtime yt-dlp needs for YouTube
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

WORKDIR /app
COPY requirements-server.txt .
RUN pip install -r requirements-server.txt

COPY *.py *.html ./
COPY static ./static

RUN useradd -m -u 1000 clip && mkdir -p /data && chown -R clip:clip /data /app
USER clip
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

# ONE worker on purpose: job state lives in this process. Concurrency comes from threads.
CMD ["gunicorn", "app:app", "-b", "0.0.0.0:8000", "-w", "1", "--threads", "16", \
     "--timeout", "120", "--graceful-timeout", "30", "--access-logfile", "-"]
