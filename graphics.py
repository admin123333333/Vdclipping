"""Motion graphics for ClipForge clips (pure FFmpeg + libass, no extra dependencies).

What it adds, like a pro Shorts editor would:
  * punch-in zooms on the loud / key moments + a slow "push-in" over the whole clip
  * animated hook title (pop-in) with a red accent bar that wipes in
  * short white flash on the first frames
  * thin progress bar that fills while the clip plays
  * "FOLLOW" call-to-action card that slides in during the last seconds
  * synthesized sound effects: whoosh on the hook / CTA, bass impact on every punch-in

Everything can be switched off: CLIPFORGE_GRAPHICS=0 (all), CLIPFORGE_SFX=0 (sounds only).
CLIPFORGE_CHANNEL=@yourchannel adds your handle to the CTA card.
"""
import os
import subprocess
import threading

RED = '&H000A0AD2&'        # UFC-style red   (ASS colours are BGR)
GOLD = '&H0000E6FF&'
RED_HI = '&H003C3CFF&'     # brighter red for emphasised words in captions
WHITE = '&H00FFFFFF&'


def enabled():
    return os.environ.get('CLIPFORGE_GRAPHICS', '1') != '0'


def sfx_enabled():
    return enabled() and os.environ.get('CLIPFORGE_SFX', '1') != '0'


def ts(sec):
    sec = max(0.0, float(sec))
    h, m, s = int(sec // 3600), int(sec % 3600 // 60), sec % 60
    return f'{h}:{m:02d}:{int(s):02d}.{int((s - int(s)) * 100):02d}'


# ------------------------------------------------------------------ punch-in zooms
def punch_times(words, a, b, energy=None, boost_re=None, max_n=4, min_gap=4.0):
    """Moments (seconds, relative to the clip start) that deserve a punch-in zoom.
    Key words first (knockout, robbed ...), then the loudest audio peaks."""
    dur = b - a
    lo, hi = 1.5, dur - 3.0            # not on the hook, not on the CTA
    cands = []
    if boost_re is not None:
        for w in words:
            if a <= w['start'] <= b and boost_re.search(str(w['word'])):
                cands.append((float(w['start']) - a - 0.1, 2.0))
    if energy is not None:
        try:
            import numpy as np
            seg = np.asarray(energy[int(a):int(b) + 1], dtype=float)
            for i in range(len(seg)):
                nb = seg[max(0, i - 2):i + 3]
                if seg[i] >= 0.7 and seg[i] >= nb.max():
                    cands.append((i + int(a) - a - 0.1, float(seg[i])))
        except Exception:
            pass
    picked = []
    for t, sc in sorted(cands, key=lambda x: -x[1]):
        if lo <= t <= hi and all(abs(t - p) >= min_gap for p in picked):
            picked.append(t)
        if len(picked) >= max_n:
            break
    return sorted(picked)


def zoom_expr(dur, punches, amp=1.0):
    """Zoom factor as an ffmpeg expression in t: slow push-in + intro settle + punch-ins.
    amp < 1 gives a gentler zoom (used in full-frame mode so almost nothing is cut)."""
    terms = [f'{0.04 * amp:.4f}*t/{max(dur, 1):.2f}',                     # slow push-in over the clip
             f'if(lt(t,0.5),{0.08 * amp:.4f}*(1-t/0.5),0)']              # settle-in at the start
    for tp in punches:
        terms.append(f'if(between(t,{tp:.2f},{tp + 0.7:.2f}),'
                     f'{0.07 * amp:.4f}*if(lt(t-{tp:.2f},0.12),(t-{tp:.2f})/0.12,1-(t-{tp:.2f}-0.12)/0.58),0)')
    return '1+' + '+'.join(terms)


def zoom_filter(tw, th, dur, punches):
    """scale+crop chain with a time-varying zoom: intro settle + slow push-in + punches."""
    z = zoom_expr(dur, punches)
    return (f"scale=w='trunc({tw}*({z})/2)*2':h='trunc({th}*({z})/2)*2':eval=frame,"
            f'crop={tw}:{th},setsar=1')


# ------------------------------------------------------------------ ASS overlays
def _rect(w, h, centered=True):
    if centered:
        return f'm {-w // 2} {-h // 2} l {w // 2} {-h // 2} {w // 2} {h // 2} {-w // 2} {h // 2}'
    return f'm 0 0 l {w} 0 {w} {h} 0 {h}'


def hook_tags():
    """Pop-in for the hook title (overshoot then settle)."""
    return r'{\fad(100,250)\fscx55\fscy55\t(0,200,\fscx114\fscy114)\t(200,340,\fscx100\fscy100)}'


def overlay_events(px, py, hfs, hmv, fs, mv, dur, hook=None, hook_lines=1, cta_cy=None, frame=None):
    """Dialogue lines (drawings + CTA) to append to the [Events] section."""
    ev = []
    # 1) opening flash
    ev.append(f'Dialogue: 5,{ts(0)},{ts(0.18)},Default,,0,0,0,,'
              r'{\an7\pos(0,0)\p1\bord0\shad0\1c&HFFFFFF&\alpha&H70&\t(0,170,\alpha&HFF&)}'
              + _rect(px, py, centered=False))
    # 2) progress bar (top edge, fills over the whole clip)
    ev.append(f'Dialogue: 4,{ts(0)},{ts(dur)},Default,,0,0,0,,'
              r'{\an7\pos(0,0)\p1\bord0\shad0\1c' + RED + r'\fscx0.5' +
              rf'\t(0,{int(dur * 1000)},\fscx100)' + '}' + _rect(px, max(8, py // 190), centered=False))
    # 3) accent bar that wipes in under the hook (top-left anchored: libass ignores negative drawing coords)
    if hook:
        y = int(hmv + hfs * 1.15 * hook_lines + 22)
        he = min(3.2, max(1.0, dur))
        bw, bh = int(px * 0.46), max(8, py // 200)
        ev.append(f'Dialogue: 3,{ts(0.05)},{ts(he)},Default,,0,0,0,,'
                  rf'{{\an7\pos({(px - bw) // 2},{y})\p1\bord0\shad0\1c{RED}\fscx1\fad(0,250)'
                  rf'\t(0,320,\fscx100)}}' + _rect(bw, bh, centered=False))
    # 3b) full-frame mode: red accent lines wipe in along the top/bottom edge of the video
    if frame:
        lh = max(6, py // 260)
        for y in (frame[0] - lh, frame[1]):
            ev.append(f'Dialogue: 3,{ts(0.1)},{ts(dur)},Default,,0,0,0,,'
                      rf'{{\an7\pos(0,{y})\p1\bord0\shad0\1c{RED}\fscx1\t(0,450,\fscx100)}}'
                      + _rect(px, lh, centered=False))
    # 4) CTA card in the last 2.4 s
    if dur >= 8:
        cs = max(0.0, dur - 2.4)
        handle = os.environ.get('CLIPFORGE_CHANNEL', '').strip().replace('{', '').replace('}', '')
        line1 = 'FOLLOW FOR MORE'
        line2 = handle or 'UFC CLIPS DAILY'
        cfs = int(fs * 0.78)
        bw = int(max(len(line1), len(line2 * 1)) * cfs * 0.66 + 110)
        bh = int(cfs * 2.9)
        cy = cta_cy if cta_cy else py - mv - int(fs * 3.4)   # centre of the card
        bx, by = (px - bw) // 2, cy - bh // 2
        box_mv = rf'\move({bx},{by + 140},{bx},{by},0,320)'
        txt_mv = rf'\move({px // 2},{cy + 140},{px // 2},{cy},0,320)'
        ev.append(f'Dialogue: 3,{ts(cs)},{ts(dur)},Default,,0,0,0,,'
                  rf'{{\an7{box_mv}\p1\bord0\shad0\1c{RED}\fad(150,200)}}' + _rect(bw, bh, centered=False))
        ev.append(f'Dialogue: 4,{ts(cs)},{ts(dur)},Default,,0,0,0,,'
                  rf'{{\an5{txt_mv}\fs{cfs}\bord0\shad0\1c&HFFFFFF&\fad(150,200)}}'
                  rf'{line1}\N{{\fs{int(cfs * 0.9)}\1c{GOLD}}}{line2}')
    return ev


# ------------------------------------------------------------------ sound effects
_SFX_LOCK = threading.Lock()


def make_sfx(ffmpeg, work):
    """Generate whoosh.wav / impact.wav once (synthesized, no downloads, no copyright)."""
    paths = {k: os.path.join(work, f'sfx_{k}.wav') for k in ('whoosh', 'impact')}
    specs = {
        'whoosh': ['-f', 'lavfi', '-i', 'anoisesrc=d=0.5:c=pink:a=1.0',
                   '-af', 'highpass=f=500,lowpass=f=7000,afade=t=in:d=0.22,afade=t=out:st=0.22:d=0.28'],
        'impact': ['-f', 'lavfi', '-i',
                   "aevalsrc='0.9*sin(2*PI*52*t)*exp(-7*t)+0.35*(random(0)*2-1)*exp(-45*t)':d=0.6:s=48000",
                   '-af', 'volume=1.2'],
    }
    with _SFX_LOCK:
        for k, p in paths.items():
            if os.path.isfile(p) and os.path.getsize(p) > 1000:
                continue
            subprocess.run([ffmpeg, '-y', '-v', 'error', *specs[k], '-ac', '1', '-ar', '48000', p],
                           check=True, capture_output=True, timeout=60)
    return paths


def audio_graph(dur, punches, sfx):
    """(extra_input_args, filter_complex) mixing normalised dialogue with the SFX.
    Input 0 is the video; the SFX files are inputs 1..n. Output label: [aout]."""
    events = [('whoosh', 0.0, 1.0)]
    events += [('impact', t, 0.6) for t in punches]
    if dur >= 8:
        events.append(('whoosh', max(0.0, dur - 2.4), 0.8))
    inputs, parts, labels = [], [], ['[m]']
    base = ('[0:a:0]loudnorm=I=-14:TP=-1.5:LRA=11'
            f',afade=t=out:st={max(0.0, dur - 0.25):.2f}:d=0.25[m]')
    for n, (kind, t, vol) in enumerate(events, 1):
        inputs += ['-i', sfx[kind]]
        ms = int(max(0, t) * 1000)
        parts.append(f'[{n}:a]adelay={ms}:all=1,volume={vol}[s{n}]')
        labels.append(f'[s{n}]')
    mix = f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:dropout_transition=0:normalize=0[aout]"
    return inputs, ';'.join([base] + parts + [mix])
