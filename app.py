"""ClipForge server (v28 - public website ready).

Runs two ways:
  * locally on your PC (python app.py) - permissive defaults, like before
  * as a public website (CLIPFORGE_PUBLIC=1, see DEPLOY_AR.md) - queue, rate limits,
    upload/duration limits, URL allow-list, unguessable job links, auto-delete of files.

All limits are environment variables, see .env.example.
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
import uuid
import zipfile
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_file, send_from_directory

from clip_engine import (download_video, transcribe_groq, transcribe_local, find_highlights,
                         render_clip, translate_words_to_english, audio_energy, _ffmpeg_exe)
import smartcrop


def _b(name, default):
    v = os.environ.get(name)
    return default if v is None or v == '' else v.strip().lower() not in ('0', 'false', 'no', 'off')


def _i(name, default):
    try:
        return int(os.environ.get(name, '') or default)
    except ValueError:
        return default


def _f(name, default):
    try:
        return float(os.environ.get(name, '') or default)
    except ValueError:
        return default


PUBLIC = _b('CLIPFORGE_PUBLIC', False)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.environ.get('CLIPFORGE_DATA_DIR') or os.path.join(BASE_DIR, 'results'))
MAX_UPLOAD_MB = _i('CLIPFORGE_MAX_UPLOAD_MB', 500 if PUBLIC else 4096)
MAX_MINUTES = _i('CLIPFORGE_MAX_MINUTES', 45 if PUBLIC else 0)          # 0 = unlimited
MAX_CLIPS = _i('CLIPFORGE_MAX_CLIPS', 6 if PUBLIC else 10)
MAX_ACTIVE = max(1, _i('CLIPFORGE_MAX_JOBS', 1 if PUBLIC else 2))        # jobs processed at once
MAX_QUEUE = _i('CLIPFORGE_MAX_QUEUE', 8)
RATE_PER_HOUR = _i('CLIPFORGE_RATE_PER_HOUR', 3 if PUBLIC else 0)        # per IP, 0 = off
TTL_HOURS = _f('CLIPFORGE_TTL_HOURS', 6 if PUBLIC else 0)                # 0 = keep forever
MIN_FREE_GB = _f('CLIPFORGE_MIN_FREE_GB', 3 if PUBLIC else 0)
ALLOW_URL = _b('CLIPFORGE_ALLOW_URL', True)
ALLOW_LOCAL = _b('CLIPFORGE_ALLOW_LOCAL', not PUBLIC)                    # local Whisper on the server
SERVER_KEY = os.environ.get('GROQ_API_KEY', '').strip()
CONTACT = os.environ.get('CLIPFORGE_CONTACT', '').strip()
CORS_ORIGIN = os.environ.get('CLIPFORGE_CORS_ORIGIN', '').strip()
RATIOS = ('9:16', '1:1', '16:9')
VIDEO_EXT = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v'}
YT_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be'}
JID_RE = re.compile(r'[0-9a-f]{32}')
CLIP_RE = re.compile(r'clip_\d{1,2}\.mp4')

os.makedirs(DATA_DIR, exist_ok=True)
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = (MAX_UPLOAD_MB + 2) * 1024 * 1024
if _b('CLIPFORGE_TRUST_PROXY', False):       # behind Caddy/nginx: real client IP from X-Forwarded-For
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

JOBS = {}
JOBS_LOCK = threading.Lock()
HITS = defaultdict(deque)                     # ip -> submission timestamps
QCOND = threading.Condition()
QUEUE, ACTIVE = [], [0]


# ------------------------------------------------------------------ helpers
def _clean(msg):
    msg = str(msg)
    for p in (DATA_DIR, BASE_DIR):
        msg = msg.replace(p, '…').replace(p.replace('\\', '/'), '…')
    return msg[:400]


def log(job, msg):
    job['log'].append(_clean(msg))
    del job['log'][:-300]
    try:
        print(f"[{job['id'][:8]}] {_clean(msg)}", flush=True)
    except Exception:
        pass


def job_dir(jid):
    return os.path.join(DATA_DIR, jid)


def _save(job):
    try:
        with open(os.path.join(job_dir(job['id']), 'job.json'), 'w', encoding='utf-8') as f:
            json.dump({k: job.get(k) for k in ('id', 'status', 'log', 'results', 'created', 'finished', 'has_zip')},
                      f, ensure_ascii=False)
    except Exception:
        pass


def _load_jobs():
    """Re-attach finished jobs after a restart (running ones are marked interrupted)."""
    for jid in os.listdir(DATA_DIR):
        p = os.path.join(DATA_DIR, jid, 'job.json')
        if not JID_RE.fullmatch(jid) or not os.path.isfile(p):
            continue
        try:
            with open(p, encoding='utf-8') as fh:
                d = json.load(fh)
            if d.get('status') in ('queued', 'running'):
                d['status'] = 'error'
                d['finished'] = d.get('finished') or time.time()
                d['log'].append('❌ تم إيقاف الخادم أثناء المعالجة. أعد المحاولة.')
            d['dir'] = job_dir(jid)
            JOBS[jid] = d
        except Exception:
            continue


def client_ip():
    return request.remote_addr or '?'


def rate_limited():
    """Minutes to wait if this IP is over its hourly limit, else 0."""
    if RATE_PER_HOUR <= 0:
        return 0
    now, q = time.time(), HITS[client_ip()]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= RATE_PER_HOUR:
        return int(3600 - (now - q[0])) // 60 + 1
    return 0


def probe_duration(path):
    try:
        p = subprocess.run([_ffmpeg_exe(), '-hide_banner', '-i', path], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=60)
        m = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', p.stderr)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return None


def valid_youtube(url):
    try:
        u = urlparse(url)
        host = (u.hostname or '').lower()
    except Exception:
        return False
    return (len(url) <= 300 and u.scheme in ('http', 'https') and host in YT_HOSTS
            and not u.username and not u.password)


def err(msg, code=400):
    return jsonify(error=msg), code


def _acquire(jid):
    with QCOND:
        QUEUE.append(jid)
        while QUEUE[0] != jid or ACTIVE[0] >= MAX_ACTIVE:
            QCOND.wait(timeout=2)
        QUEUE.pop(0)
        ACTIVE[0] += 1
        QCOND.notify_all()


def _release():
    with QCOND:
        ACTIVE[0] -= 1
        QCOND.notify_all()


def _workers():
    env = os.environ.get('CLIPFORGE_RENDER_WORKERS')
    if env and env.isdigit() and int(env) > 0:
        return int(env)
    return max(1, min(3, (os.cpu_count() or 2) // 2))


def _purge_intermediates(work):
    """Public mode: keep only the finished clips (+zip + job.json); drop source video, audio, subtitles."""
    for n in os.listdir(work):
        if CLIP_RE.fullmatch(n) or n in ('job.json', 'clips.zip'):
            continue
        try:
            os.remove(os.path.join(work, n))
        except OSError:
            pass


# ------------------------------------------------------------------ pipeline
def run_job(jid, src, o):
    job, work = JOBS[jid], job_dir(jid)
    _acquire(jid)
    job['status'] = 'running'
    bg = ThreadPoolExecutor(max_workers=1)
    t0 = time.time()

    def tick(label):
        nonlocal t0
        log(job, f'⏱️ {label}: {time.time() - t0:.0f}s')
        t0 = time.time()

    try:
        key, ratio, mode = o['key'], o['ratio'], o['mode']
        if o.get('url'):
            log(job, '⬇️ جاري تحميل الفيديو من يوتيوب…')
            src = download_video(o['url'], work, progress=lambda m: log(job, m),
                                 max_seconds=MAX_MINUTES * 60)
            tick('التحميل')
        dur = probe_duration(src)
        if MAX_MINUTES and dur and dur > MAX_MINUTES * 60:
            raise RuntimeError(f'الفيديو أطول من الحد المسموح ({MAX_MINUTES} دقيقة).')

        energy_f = bg.submit(audio_energy, src)
        log(job, '🎙️ جاري التفريغ النصي (%s)…' % ('سحابي' if mode == 'api' else 'محلي'))
        if mode == 'api':
            words, source_language = transcribe_groq(src, work, key)
        else:
            words, source_language = transcribe_local(src, work, progress=lambda m: log(job, m))
        log(job, f'✅ تم استخراج {len(words)} كلمة')
        tick('التفريغ')

        log(job, '🌐 ترجمة الـ captions إلى الإنجليزية (متزامنة)…')
        words = translate_words_to_english(words, key, source_language)
        tick('الترجمة')

        log(job, '🔥 اختيار أقوى اللحظات بالذكاء الاصطناعي…')
        energy = energy_f.result()
        clips = find_highlights(words, key, o['count'], energy)
        tick('التحليل')

        how = 'إطار كامل بدون قص' if o['reframe'] == 'fit' else 'قص ذكي'
        log(job, f'✂️ تجهيز {len(clips)} مقاطع بالتوازي ({how})…')

        def one(i, c):
            return i, c, render_clip(src, words, c, ratio, work, f'clip_{i}', o['hook'], energy, o['fx'],
                                     o['reframe'], lambda m: log(job, m))

        failed = 0
        with ThreadPoolExecutor(max_workers=_workers()) as ex:
            futs = {ex.submit(one, i, c): i for i, c in enumerate(clips, 1)}
            for fut in as_completed(futs):
                try:
                    i, c, f = fut.result()
                except Exception as e:
                    failed += 1
                    log(job, f'⚠️ فشل المقطع {futs[fut]}: {str(e)[-300:]}')
                    continue
                job['results'].append({**c, 'rank': i, 'file': f'/files/{jid}/{f}'})
                log(job, f'✅ المقطع {i}/{len(clips)} جاهز')
        if failed == len(clips):
            raise RuntimeError('فشل تجهيز كل المقاطع')
        job['results'].sort(key=lambda r: r['rank'])
        tick('التصدير')

        try:   # one zip with all clips
            with zipfile.ZipFile(os.path.join(work, 'clips.zip'), 'w', zipfile.ZIP_STORED) as z:
                for r in job['results']:
                    z.write(os.path.join(work, os.path.basename(r['file'])), os.path.basename(r['file']))
            job['has_zip'] = True
        except Exception:
            job['has_zip'] = False
        job['finished'] = time.time()
        job['status'] = 'done'
        log(job, '🎉 اكتملت المعالجة')
    except Exception as e:
        traceback.print_exc()
        job['finished'] = time.time()
        job['status'] = 'error'
        log(job, f'❌ خطأ: {e}')
    finally:
        _release()
        bg.shutdown(wait=False)
        if PUBLIC:
            _purge_intermediates(work)
        _save(job)


# ------------------------------------------------------------------ housekeeping
def cleanup_once(now=None):
    now = now or time.time()
    if TTL_HOURS > 0:
        ttl = TTL_HOURS * 3600
        with JOBS_LOCK:
            old = [j for j, v in JOBS.items() if v.get('finished') and now - v['finished'] > ttl]
            for j in old:
                JOBS.pop(j, None)
        for j in old:
            shutil.rmtree(job_dir(j), ignore_errors=True)
        for n in os.listdir(DATA_DIR):          # orphan folders (older runs / crashes)
            p = os.path.join(DATA_DIR, n)
            if JID_RE.fullmatch(n) and n not in JOBS and os.path.isdir(p) and now - os.path.getmtime(p) > ttl + 3600:
                shutil.rmtree(p, ignore_errors=True)
    for ip in [k for k, q in list(HITS.items()) if not q or now - q[-1] > 3600]:
        HITS.pop(ip, None)


def _cleanup_loop():
    while True:
        time.sleep(600)
        try:
            cleanup_once()
        except Exception:
            traceback.print_exc()


# ------------------------------------------------------------------ HTTP
@app.after_request
def headers(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Referrer-Policy'] = 'no-referrer'
    resp.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if request.path.startswith('/api/'):
        resp.headers['Cache-Control'] = 'no-store'
    if CORS_ORIGIN:
        resp.headers['Access-Control-Allow-Origin'] = CORS_ORIGIN
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    return resp


@app.errorhandler(413)
def too_big(_):
    return err(f'الملف أكبر من الحد المسموح ({MAX_UPLOAD_MB} MB).', 413)


@app.get('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.get('/static/<path:name>')
def static_files(name):
    resp = send_from_directory(os.path.join(BASE_DIR, 'static'), name)
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


@app.get('/legal')
def legal():
    with open(os.path.join(BASE_DIR, 'legal.html'), encoding='utf-8') as fh:
        html = fh.read()
    html = (html.replace('{{TTL}}', (f'{TTL_HOURS:g} ساعات' if TTL_HOURS else 'مدة غير محددة'))
                .replace('{{CONTACT}}', CONTACT or 'عبر صفحة الموقع'))
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.get('/healthz')
def healthz():
    return jsonify(ok=True, active=ACTIVE[0], queued=len(QUEUE))


@app.get('/api/config')
def config():
    return jsonify(public=PUBLIC, max_upload_mb=MAX_UPLOAD_MB, max_minutes=MAX_MINUTES, max_clips=MAX_CLIPS,
                   allow_url=ALLOW_URL, allow_local=ALLOW_LOCAL, server_key=bool(SERVER_KEY),
                   ttl_hours=TTL_HOURS, rate_per_hour=RATE_PER_HOUR)


@app.route('/api/process', methods=['POST', 'OPTIONS'])
def process():
    if request.method == 'OPTIONS':
        return '', 204
    # cheap checks first, before the (possibly huge) upload body is read
    wait = rate_limited()
    if wait:
        return err(f'وصلت للحد المسموح ({RATE_PER_HOUR} فيديوهات في الساعة). حاول بعد {wait} دقيقة.', 429)
    if len(QUEUE) >= MAX_QUEUE:
        return err('الخادم مشغول حالياً. حاول بعد قليل.', 503)
    if MIN_FREE_GB and shutil.disk_usage(DATA_DIR).free < MIN_FREE_GB * 1024 ** 3:
        return err('الخادم ممتلئ مؤقتاً. حاول لاحقاً.', 503)

    f = request.files.get('video')
    url = (request.form.get('url') or '').strip()
    if not (f and f.filename) and not url:
        return err('أضف رابط يوتيوب أو ملف فيديو')
    if url:
        if not ALLOW_URL:
            return err('التحميل من الروابط غير مفعّل في هذا الموقع. ارفع ملف الفيديو.')
        if not valid_youtube(url):
            return err('الرابط غير صالح. المسموح فقط روابط يوتيوب (youtube.com / youtu.be).')

    mode = 'local' if request.form.get('mode') == 'local' else 'api'
    if mode == 'local' and not ALLOW_LOCAL:
        return err('الوضع المحلي غير متاح في هذا الموقع.')
    user_key = (request.form.get('groq_key') or '').strip()
    if user_key and not re.fullmatch(r'gsk_[A-Za-z0-9_\-]{20,200}', user_key):
        return err('مفتاح Groq غير صالح (يبدأ بـ gsk_).')
    key = user_key or SERVER_KEY or None
    if mode == 'api' and not key:
        return err('أدخل مفتاح Groq في الإعدادات.')

    ratio = request.form.get('ratio') if request.form.get('ratio') in RATIOS else '9:16'
    try:
        count = max(1, min(int(request.form.get('count', 5)), MAX_CLIPS))
    except ValueError:
        count = 5
    opts = {'key': key, 'ratio': ratio, 'mode': mode, 'count': count, 'url': url or None,
            'hook': request.form.get('hook', '1') != '0', 'fx': request.form.get('fx', '1') != '0',
            'reframe': 'fill' if request.form.get('reframe') == 'fill' else 'fit'}

    jid = uuid.uuid4().hex
    work = job_dir(jid)
    os.makedirs(work)
    src = None
    if not url:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in VIDEO_EXT:
            shutil.rmtree(work, ignore_errors=True)
            return err('صيغة الملف غير مدعومة. المسموح: mp4, mov, mkv, webm, avi.')
        src = os.path.join(work, 'source' + ext)
        f.save(src)
        dur = probe_duration(src)
        sw, _ = smartcrop.probe_size(_ffmpeg_exe(), src)
        if not sw or not dur:
            shutil.rmtree(work, ignore_errors=True)
            return err('الملف ليس فيديو صالحاً أو تالف.')
        if MAX_MINUTES and dur > MAX_MINUTES * 60:
            shutil.rmtree(work, ignore_errors=True)
            return err(f'الفيديو أطول من الحد المسموح ({MAX_MINUTES} دقيقة).')

    if RATE_PER_HOUR > 0:
        HITS[client_ip()].append(time.time())
    job = {'id': jid, 'status': 'queued', 'log': ['🚀 تم استلام الطلب'], 'results': [], 'dir': work,
           'created': time.time(), 'finished': None, 'has_zip': False}
    with JOBS_LOCK:
        JOBS[jid] = job
    _save(job)
    threading.Thread(target=run_job, args=(jid, src, opts), daemon=True).start()
    return jsonify(job=jid)


@app.get('/api/status/<jid>')
def status(jid):
    job = JOBS.get(jid) if JID_RE.fullmatch(jid) else None
    if not job:
        return jsonify(status='gone', log=['انتهت صلاحية هذه المهمة أو حُذفت.'], results=[]), 404
    with QCOND:
        pos = QUEUE.index(jid) + 1 if jid in QUEUE else 0
    exp = (job['finished'] + TTL_HOURS * 3600) if (TTL_HOURS and job.get('finished')) else None
    return jsonify(status=job['status'], log=job['log'], results=job['results'], queue_pos=pos,
                   has_zip=bool(job.get('has_zip')), expires_at=exp)


@app.get('/files/<jid>/<name>')
def files(jid, name):
    if not (JID_RE.fullmatch(jid) and CLIP_RE.fullmatch(name)) or jid not in JOBS:
        return err('not found', 404)
    return send_from_directory(job_dir(jid), name, mimetype='video/mp4', as_attachment=request.args.get('dl') == '1',
                               download_name=f'clipforge_{name}', conditional=True, max_age=0)


@app.get('/api/zip/<jid>')
def zip_all(jid):
    job = JOBS.get(jid) if JID_RE.fullmatch(jid) else None
    p = os.path.join(job_dir(jid), 'clips.zip') if job else ''
    if not job or not os.path.isfile(p):
        return err('not found', 404)
    return send_file(p, mimetype='application/zip', as_attachment=True, download_name='clipforge_clips.zip')


@app.delete('/api/job/<jid>')
def delete_job(jid):
    job = JOBS.get(jid) if JID_RE.fullmatch(jid) else None
    if not job:
        return err('not found', 404)
    if job['status'] in ('queued', 'running'):
        return err('المعالجة ما زالت جارية.', 409)
    with JOBS_LOCK:
        JOBS.pop(jid, None)
    shutil.rmtree(job_dir(jid), ignore_errors=True)
    return jsonify(ok=True)


def _boot():
    _load_jobs()
    threading.Thread(target=_cleanup_loop, daemon=True).start()


_boot()

if __name__ == '__main__':
    # 127.0.0.1 = this PC only. Set CLIPFORGE_HOST=0.0.0.0 to open it to your LAN.
    app.run(host=os.environ.get('CLIPFORGE_HOST', '127.0.0.1'), port=_i('PORT', 5000), debug=False, threaded=True)
