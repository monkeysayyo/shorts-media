#!/usr/bin/env python3
"""Free vertical short-video renderer (1080x1920, 30fps) using PIL + ffmpeg.

Usage: python3 render_short.py spec.json out.mp4

spec.json:
{
  "theme": "dark" | "light" | "pop",       # colour palette
  "hook": "最初の1〜2秒で見せる一文",
  "scenes": [ {"title": "見出し", "body": "本文（短く）", "emoji_label": "No.1"} , ... ],
  "cta": "フォローで毎日1本",
  "scene_seconds": 3.2,                    # optional, seconds per scene
  "bgm": true                              # optional, synthesized soft beat
}
"""
import json, math, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"
FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
JP = 0  # index of the JP face inside the .ttc

PALETTES = {
    "dark":  {"bg1": (14, 16, 28), "bg2": (40, 22, 70), "fg": (255, 255, 255), "accent": (255, 210, 64), "sub": (200, 200, 220)},
    "light": {"bg1": (250, 247, 240), "bg2": (232, 238, 255), "fg": (20, 20, 30), "accent": (230, 60, 90), "sub": (80, 80, 100)},
    "pop":   {"bg1": (255, 92, 120), "bg2": (255, 170, 60), "fg": (255, 255, 255), "accent": (30, 30, 50), "sub": (255, 240, 230)},
}


def font(size, bold=True):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size, index=JP)


def wrap(text, fnt, max_w, draw):
    """Character-level wrap (works for Japanese without spaces)."""
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=fnt) <= max_w:
                cur += ch
            else:
                # avoid starting a line with closing punctuation
                if ch in "、。！？」』）)ー" and cur:
                    cur += ch
                    lines.append(cur)
                    cur = ""
                    continue
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return [l for l in lines if l != ""] or [""]


def gradient(p, t):
    """Vertical gradient that slowly shifts over time."""
    a = np.array(p["bg1"], dtype=np.float32)
    b = np.array(p["bg2"], dtype=np.float32)
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    shift = 0.15 * math.sin(t * 0.6)
    k = np.clip(y + shift, 0, 1)
    col = a * (1 - k) + b * k
    img = np.repeat(col[:, None, :], W, axis=1).reshape(H, W, 3)
    return Image.fromarray(img.astype(np.uint8))


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def draw_block(img, lines, fnt, color, center_y, alpha, dy, line_gap=1.25):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lh = int(fnt.size * line_gap)
    total = lh * len(lines)
    y = int(center_y - total / 2 + dy)
    for ln in lines:
        w = d.textlength(ln, font=fnt)
        x = (W - w) / 2
        # shadow
        d.text((x + 4, y + 5), ln, font=fnt, fill=(0, 0, 0, int(110 * alpha)))
        d.text((x, y), ln, font=fnt, fill=color + (int(255 * alpha),))
        y += lh
    img.alpha_composite(layer)


def render_frame(p, segs, total, t):
    img = gradient(p, t).convert("RGBA")
    d = ImageDraw.Draw(img)
    # find current segment
    for seg in segs:
        if seg["start"] <= t < seg["end"] or seg is segs[-1]:
            cur = seg
            if seg["start"] <= t < seg["end"]:
                break
    local = t - cur["start"]
    dur = cur["end"] - cur["start"]
    a_in = ease(local / 0.35)
    a_out = 1 - ease((local - (dur - 0.25)) / 0.25) if cur is not segs[-1] else 1
    alpha = min(a_in, a_out)
    dy = (1 - a_in) * 60

    if cur["kind"] == "hook":
        f = font(96)
        lines = wrap(cur["text"], f, W - 140, d)
        draw_block(img, lines, f, p["fg"], H * 0.45, alpha, dy)
        # pulsing accent bar
        bw = int(300 + 40 * math.sin(t * 6))
        d.rounded_rectangle([(W - bw) / 2, H * 0.62, (W + bw) / 2, H * 0.62 + 16], 8, fill=p["accent"])
    elif cur["kind"] == "scene":
        if cur.get("label"):
            lf = font(64)
            lw = d.textlength(cur["label"], font=lf)
            pad = 36
            x0 = (W - lw) / 2 - pad
            y0 = H * 0.24 + dy
            d.rounded_rectangle([x0, y0, x0 + lw + pad * 2, y0 + 104], 52, fill=p["accent"])
            d.text(((W - lw) / 2, y0 + 12), cur["label"], font=lf,
                   fill=(p["bg1"] if p is not PALETTES["pop"] else (255, 255, 255)))
        tf = font(88)
        tl = wrap(cur["title"], tf, W - 140, d)
        draw_block(img, tl, tf, p["fg"], H * 0.42, alpha, dy)
        if cur.get("body"):
            bf = font(54, bold=False)
            bl = wrap(cur["body"], bf, W - 180, d)
            draw_block(img, bl, bf, p["sub"], H * 0.62, alpha, dy * 1.4, line_gap=1.4)
    else:  # cta
        f = font(84)
        lines = wrap(cur["text"], f, W - 160, d)
        draw_block(img, lines, f, p["fg"], H * 0.46, alpha, dy)
        s = 1 + 0.05 * math.sin(t * 5)
        bw, bh = 520 * s, 120 * s
        d.rounded_rectangle([(W - bw) / 2, H * 0.6, (W + bw) / 2, H * 0.6 + bh], 60, fill=p["accent"])
        ff = font(56)
        txt = "フォロー"
        tw = d.textlength(txt, font=ff)
        d.text(((W - tw) / 2, H * 0.6 + (bh - 80) / 2), txt, font=ff,
               fill=(p["bg1"] if p is not PALETTES["pop"] else (255, 255, 255)))

    # progress bar (keeps viewers watching to the end)
    prog = min(1.0, t / total)
    d.rectangle([0, H - 14, W * prog, H], fill=p["accent"])
    return img.convert("RGB")


def make_bgm(path, seconds, bpm=100):
    sr = 44100
    n = int(seconds * sr)
    t = np.arange(n) / sr
    beat = 60 / bpm
    chords = [[220.0, 277.18, 329.63], [196.0, 246.94, 293.66], [174.61, 220.0, 261.63], [196.0, 246.94, 329.63]]
    out = np.zeros(n, dtype=np.float32)
    bar = beat * 4
    for i, c in enumerate(chords * int(math.ceil(seconds / (bar * 4)) + 1)):
        s0 = int(i * bar * sr)
        if s0 >= n:
            break
        s1 = min(n, int((i + 1) * bar * sr))
        tt = t[s0:s1] - t[s0]
        env = np.minimum(1, tt / 0.3) * np.exp(-tt * 0.4)
        for f in c:
            out[s0:s1] += 0.06 * np.sin(2 * np.pi * f * tt) * env
    # soft kick on each beat
    k = 0.0
    while k < seconds:
        s0 = int(k * sr)
        L = min(int(0.18 * sr), n - s0)
        tt = np.arange(L) / sr
        out[s0:s0 + L] += 0.35 * np.sin(2 * np.pi * (55 + 90 * np.exp(-tt * 25)) * tt) * np.exp(-tt * 18)
        k += beat
    # hi-hat on off-beats
    rng = np.random.default_rng(1)
    k = beat / 2
    while k < seconds:
        s0 = int(k * sr)
        L = min(int(0.04 * sr), n - s0)
        out[s0:s0 + L] += 0.05 * rng.standard_normal(L) * np.exp(-np.arange(L) / sr * 120)
        k += beat
    fade = int(1.0 * sr)
    out[-fade:] *= np.linspace(1, 0, fade)
    out = np.clip(out, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((out * 32767).astype(np.int16).tobytes())


def main(spec_path, out_path):
    spec = json.load(open(spec_path, encoding="utf-8"))
    p = PALETTES.get(spec.get("theme", "dark"), PALETTES["dark"])
    sec = float(spec.get("scene_seconds", 3.2))
    segs, t = [], 0.0
    segs.append({"kind": "hook", "text": spec["hook"], "start": t, "end": t + 2.2}); t += 2.2
    for sc in spec["scenes"]:
        segs.append({"kind": "scene", "title": sc["title"], "body": sc.get("body", ""),
                     "label": sc.get("emoji_label", ""), "start": t, "end": t + sec}); t += sec
    segs.append({"kind": "cta", "text": spec.get("cta", "フォローで毎日1本"), "start": t, "end": t + 2.5}); t += 2.5
    total = t

    silent = out_path + ".silent.mp4"
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                             "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", silent],
                            stdin=subprocess.PIPE)
    for i in range(int(total * FPS)):
        proc.stdin.write(render_frame(p, segs, total, i / FPS).tobytes())
    proc.stdin.close(); proc.wait()

    if spec.get("bgm", True):
        wav = out_path + ".bgm.wav"
        make_bgm(wav, total)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", wav, "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", out_path], check=True)
    else:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-c", "copy",
                        "-movflags", "+faststart", out_path], check=True)
    print(f"done: {out_path} ({total:.1f}s)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
