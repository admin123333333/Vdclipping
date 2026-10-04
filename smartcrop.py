"""Smart reframing for ClipForge.

Instead of padding a 16:9 video with black bars, we crop to the target aspect
ratio and let a virtual camera follow the main face. If OpenCV is missing or no
face is found, we fall back to a centred crop (never black bars, except when the
source is *narrower* than the target, where a blurred background is used).
"""
import os
import re
import subprocess
from functools import lru_cache

# Default is full HD (best quality for Shorts). Set CLIPFORGE_RES=720 for ~2x faster renders.
if os.environ.get('CLIPFORGE_RES', '1080') == '1080':
    SIZES = {'9:16': (1080, 1920), '1:1': (1080, 1080), '16:9': (1920, 1080)}
else:
    SIZES = {'9:16': (720, 1280), '1:1': (720, 720), '16:9': (1280, 720)}


@lru_cache(maxsize=16)
def probe_size(ffmpeg, src):
    """Return (width, height) as displayed (rotation aware) or (None, None)."""
    try:
        p = subprocess.run([ffmpeg, '-hide_banner', '-i', src], capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=60)
    except Exception:
        return None, None
    m = re.search(r'Video:.*?,\s*(\d{2,5})x(\d{2,5})', p.stderr)
    if not m:
        return None, None
    w, h = int(m.group(1)), int(m.group(2))
    r = re.search(r'rotation of (-?\d+(?:\.\d+)?) degrees', p.stderr)
    if r and abs(float(r.group(1))) % 180 == 90:
        w, h = h, w
    return w, h


def face_samples(src, a, b, step=0.5, ffmpeg=None):
    """[(t_rel, face_center_x_in_source_pixels | None)] every `step` s.

    Frames come from ONE multi-threaded FFmpeg pass (downscaled, gray, 1/step fps)
    instead of decoding every frame in OpenCV, which was very slow on HD/4K."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    if not ffmpeg:
        return None
    cascade = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades,
                                                 'haarcascade_frontalface_default.xml'))
    if cascade.empty():
        return None
    sw, sh = probe_size(ffmpeg, src)
    if not sw:
        return None
    fw = min(640, sw)
    fh = max(2, int(fw * sh / sw) // 2 * 2)
    cmd = [ffmpeg, '-v', 'error', '-ss', str(a), '-t', str(b - a + step), '-i', src,
           '-an', '-sn', '-vf', f'fps={1.0 / step:g},scale={fw}:{fh}',
           '-pix_fmt', 'gray', '-f', 'rawvideo', '-']
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=600)
    except Exception:
        return None
    fsz = fw * fh
    n = min(len(p.stdout) // fsz, int((b - a) / step) + 1)
    if n < 1:
        return None
    k = fw / sw
    min_face = (max(24, int(fw * 0.05)),) * 2
    out = []
    for i in range(n):
        gray = np.frombuffer(p.stdout, np.uint8, fsz, i * fsz).reshape(fh, fw)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=min_face)
        cx = None
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            cx = (x + w / 2.0) / k
        out.append((i * step, cx))
    return out


def camera_path(samples, crop_w, src_w, dead=0.10, gain=0.4):
    """Smooth, steady virtual-camera x positions [(t, x_left)] or None."""
    if not samples:
        return None
    seen = [c for _, c in samples if c is not None]
    if len(seen) < max(2, 0.2 * len(samples)):
        return None
    # fill gaps: forward then backward
    cs, last = [], None
    for _, c in samples:
        last = c if c is not None else last
        cs.append(last)
    nxt = None
    for i in range(len(cs) - 1, -1, -1):
        if cs[i] is None:
            cs[i] = nxt
        nxt = cs[i]
    # median-of-5 removes single-frame detection glitches
    med = []
    for i in range(len(cs)):
        win = sorted(cs[max(0, i - 2):i + 3])
        med.append(win[len(win) // 2])
    cam = med[0]
    half, hi = crop_w / 2.0, src_w - crop_w
    pts = []
    for (t, _), c in zip(samples, med):
        if abs(c - cam) > dead * crop_w:       # dead zone = camera stays still
            cam += (c - cam) * gain
        pts.append((t, round(min(max(cam - half, 0), hi))))
    # drop interior points of constant runs (lossless for linear interpolation)
    slim = [pts[0]]
    for i in range(1, len(pts) - 1):
        if not (pts[i][1] == pts[i - 1][1] == pts[i + 1][1]):
            slim.append(pts[i])
    if len(pts) > 1:
        slim.append(pts[-1])
    return slim


def x_expression(pts):
    """Piecewise-linear ffmpeg expression in `t` through the keypoints."""
    if len(pts) == 1:
        return str(pts[0][1])
    e = str(pts[-1][1])
    for i in range(len(pts) - 2, -1, -1):
        t0, x0 = pts[i]
        t1, x1 = pts[i + 1]
        dt = max(t1 - t0, 0.01)
        e = f'if(lt(t,{t1:.2f}),{x0}+({x1 - x0})*(t-{t0:.2f})/{dt:.2f},{e})'
    return e


def _even(n):
    return max(2, int(round(n)) // 2 * 2)


def plan(ffmpeg, src, ratio, mode='fit'):
    """Decide how the source is placed on the target canvas.

    kind 'plain': aspect ratios already match -> straight scale (no loss)
    kind 'fit'  : WHOLE frame kept, centred over a blurred, darkened copy of itself (no cropping)
    kind 'crop' : old behaviour, face-tracking crop (fills the screen but cuts the sides)
    """
    tw, th = SIZES.get(ratio, SIZES['16:9'])
    sw, sh = probe_size(ffmpeg, src)
    g = {'tw': tw, 'th': th, 'sw': sw, 'sh': sh, 'kind': 'plain', 'fw': tw, 'fh': th}
    if not sw:
        g['kind'] = 'fit_unknown'
        return g
    if abs(sw / sh - tw / th) < 0.02:
        return g
    if mode == 'fill' and sw / sh > tw / th:
        g['kind'] = 'crop'
        return g
    k = min(tw / sw, th / sh)
    g.update(kind='fit', fw=_even(sw * k), fh=_even(sh * k), top=(th - _even(sh * k)) // 2)
    g['bottom'] = g['top'] + g['fh']
    g['upscale'] = k > 1.0
    return g


def fit_graph(g, zexpr=None):
    """filter_complex part: [0:v] -> [v0]. Whole frame, sharp, over a blurred copy as background."""
    tw, th, fw, fh = g['tw'], g['th'], g['fw'], g['fh']
    bw, bh = _even(tw / 4), _even(th / 4)
    flags = 'lanczos+accurate_rnd+full_chroma_int'
    sharp = ',unsharp=5:5:0.45:5:5:0.0' if g.get('upscale') else ''
    bg = (f'[bgsrc]scale={bw}:{bh}:force_original_aspect_ratio=increase:flags=bilinear,'
          f'crop={bw}:{bh},gblur=sigma=9:steps=2,eq=brightness=-0.10:saturation=1.25,'
          f'scale={tw}:{th}:flags=bicubic,setsar=1[bg]')
    if zexpr:   # motion-graphics zoom applied to the foreground only; it grows over the blur, never cuts top/bottom
        fg = (f"[fgsrc]scale=w='trunc({fw}*({zexpr})/2)*2':h='trunc({fh}*({zexpr})/2)*2'"
              f':eval=frame:flags={flags}{sharp},setsar=1[fg]')
    else:
        fg = f'[fgsrc]scale={fw}:{fh}:flags={flags}{sharp},setsar=1[fg]'
    return ('[0:v]split=2[bgsrc][fgsrc];' + bg + ';' + fg +
            ";[bg][fg]overlay=x='(W-w)/2':y='(H-h)/2':eval=frame:format=auto,setsar=1[v0]")


def video_filter(ffmpeg, src, ratio, a, b, track=True):
    tw, th = SIZES.get(ratio, SIZES['16:9'])
    sw, sh = probe_size(ffmpeg, src)
    if not sw:  # unknown source size: old safe behaviour
        return (f'scale={tw}:{th}:force_original_aspect_ratio=decrease,'
                f'pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1')
    tar, sar = tw / th, sw / sh
    if abs(sar - tar) < 0.02:
        return f'scale={tw}:{th}:flags=lanczos,setsar=1'
    if sar > tar:                                   # wider than target -> crop
        cw, ch = int(sh * tar) // 2 * 2, sh // 2 * 2
        expr = None
        if track and cw < sw:
            try:
                pts = camera_path(face_samples(src, a, b, ffmpeg=ffmpeg), cw, sw)
                expr = x_expression(pts) if pts else None
            except Exception:
                expr = None
        xe = f"'{expr}'" if expr else '(iw-ow)/2'
        # a 9:16 crop of a 1080p video is only ~608 px wide -> it is upscaled, so add a light sharpen
        sharp = ',unsharp=5:5:0.5:5:5:0.0' if cw < tw else ''
        return f'crop={cw}:{ch}:{xe}:0,scale={tw}:{th}:flags=lanczos{sharp},setsar=1'
    # narrower than target (e.g. vertical -> 16:9): blurred background + centred fg
    return (f'split[a][b];[a]scale={tw}:{th}:force_original_aspect_ratio=increase,'
            f'crop={tw}:{th},boxblur=25:5[bg];'
            f'[b]scale={tw}:{th}:force_original_aspect_ratio=decrease[fg];'
            f'[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1')
