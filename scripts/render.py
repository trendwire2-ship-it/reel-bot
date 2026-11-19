#!/usr/bin/env python3
"""Render a story JSON into a smooth 60fps 1080x1920 2D-animated reel.

Usage: python3 scripts/render.py queue/story.json out.mp4 [--preview SECONDS]
Voice: Microsoft Edge "Andrew" (edge-tts, free) with word-level timing; falls back to Kokoro (offline) if unreachable.
"""
import asyncio, json, math, multiprocessing as mp, os, re, subprocess, sys, tempfile
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import *  # noqa

FPS = int(os.environ.get("REEL_FPS", "60"))
SR = 24000
MAX_LEN = 88.5  # Facebook Reels API limit is 90s
VOICE = os.environ.get("REEL_VOICE", "en-US-AndrewNeural")
MODEL = os.environ.get("KOKORO_MODEL", os.path.join(ROOT, "models/kokoro.onnx"))
VOICES = os.environ.get("KOKORO_VOICES", os.path.join(ROOT, "models/voices.bin"))

# ------------------------------------------------------------------ text normalisation (for the offline fallback voice)
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()

def n2w(n):
    n = int(n)
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")
    if n < 1000:
        return ONES[n // 100] + " hundred" + (" " + n2w(n % 100) if n % 100 else "")
    if n < 1_000_000:
        return n2w(n // 1000) + " thousand" + (" " + n2w(n % 1000) if n % 1000 else "")
    return n2w(n // 1_000_000) + " million" + (" " + n2w(n % 1_000_000) if n % 1_000_000 else "")

def year2w(y):
    y = int(y)
    if 2000 <= y <= 2009:
        return "two thousand" + (" " + ONES[y - 2000] if y > 2000 else "")
    hi, lo = divmod(y, 100)
    if lo == 0:
        return n2w(hi) + " hundred"
    return n2w(hi) + " " + ("oh " + ONES[lo] if lo < 10 else n2w(lo))

ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}

def ordinal(n):
    w = n2w(n)
    head, _, last = w.rpartition("-") if "-" in w else w.rpartition(" ")
    sep = "-" if "-" in w else " "
    last = ORD.get(last, last[:-1] + "ieth" if last.endswith("y") else last + "th")
    return (head + sep if head else "") + last

# How abbreviations are spoken (captions keep the written form). Add more as needed.
SPOKEN = [("U.S.A.", "USA"), ("U.S.", "US"), ("U.K.", "UK"), ("D.B.", "DB"), ("J.F.K.", "JFK"), ("F.B.I.", "FBI")]

def spoken(t):
    for a, b in SPOKEN:
        t = t.replace(a, b)
    return t

def normalize(text):
    t = re.sub(r"\$(\d[\d,]*)", lambda m: n2w(m.group(1).replace(",", "")) + " dollars", text)
    t = re.sub(r"\b(\d{1,2}):(\d{2})\s*([AaPp])\.?[Mm]\b\.?", lambda m: n2w(m.group(1)) + " " + ("o'clock" if int(m.group(2)) == 0 else n2w(m.group(2)) if int(m.group(2)) >= 10 else "oh " + ONES[int(m.group(2))]) + " " + m.group(3).upper() + " M", t)
    t = re.sub(r"\b(\d+)(st|nd|rd|th)\b", lambda m: ordinal(int(m.group(1))), t)
    t = re.sub(r"\b(1[1-9]\d\d|20\d\d)s\b", lambda m: year2w(m.group(1)).rsplit(" ", 1)[0] + " " + (year2w(m.group(1)).rsplit(" ", 1)[1].replace("y", "ie") + "s"), t)
    t = re.sub(r"\b(1[1-9]\d\d|20\d\d)\b", lambda m: year2w(m.group(1)), t)
    t = re.sub(r"\b\d[\d,]*\b", lambda m: n2w(m.group(0).replace(",", "")), t)
    return spoken(t)

# ------------------------------------------------------------------ voice
async def _edge(text, rate):
    import edge_tts
    com = edge_tts.Communicate(text, VOICE, rate=rate, boundary="WordBoundary")
    audio, bounds = bytearray(), []
    async for ch in com.stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":
            bounds.append((ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"]))
    return bytes(audio), bounds

def decode(mp3, tmp):
    p = os.path.join(tmp, "x.mp3")
    open(p, "wb").write(mp3)
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", p, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()

REF = os.environ.get("VOICE_REF", os.path.join(ROOT, "assets/voice_ref.wav"))

def sentence_timed(tx, synth, speed):
    """Synthesize sentence by sentence; spread word timings by spoken length within each sentence."""
    pieces, words, t = [], [], 0.0
    for sent in [s for s in re.split(r"(?<=[.!?…])\s+", tx.strip()) if s]:
        a = synth(normalize(sent))
        nz = np.where(np.abs(a) > 0.01)[0]
        if len(nz):
            a = a[max(0, nz[0] - 500): nz[-1] + 1500]
        dur = len(a) / SR
        ws = sent.split()
        wts = [len(normalize(w)) + 2 + (4 if re.search(r"[,.;:!?…]$", w) else 0) for w in ws]
        acc = t
        for w, wt in zip(ws, wts):
            d = dur * wt / sum(wts)
            words.append((acc, acc + d * 0.92, w))
            acc += d
        pieces += [a, np.zeros(int(0.1 * SR), np.float32)]
        t += dur + 0.1
    return np.concatenate(pieces), words

_clone = {}
def clone_scenes(texts, speed):
    """User's own cloned voice (Chatterbox, MIT licence) from assets/voice_ref.wav."""
    import torch, torchaudio
    from chatterbox.tts import ChatterboxTTS
    if "m" not in _clone:
        torch.set_num_threads(os.cpu_count() or 2)
        _clone["m"] = ChatterboxTTS.from_pretrained(device="cpu")
    m = _clone["m"]
    def synth(text):
        wav = m.generate(text, audio_prompt_path=REF, exaggeration=float(os.environ.get("VOICE_EXAGGERATION", "0.55")),
                         cfg_weight=float(os.environ.get("VOICE_CFG", "0.45")))
        if m.sr != SR:
            wav = torchaudio.functional.resample(wav, m.sr, SR)
        a = wav.squeeze().cpu().numpy().astype(np.float32)
        if abs(speed - 1.0) > 0.01:  # tempo change without pitch shift
            a = atempo(a, speed)
        return a
    return [sentence_timed(tx, synth, speed) for tx in texts]

def atempo(a, speed):
    with tempfile.TemporaryDirectory() as d:
        i, o = os.path.join(d, "i.wav"), os.path.join(d, "o.wav")
        sf.write(i, a, SR)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", i, "-filter:a", f"atempo={speed:.3f}", o], check=True)
        return sf.read(o, dtype="float32")[0]

def tts_scenes(texts, tmp, speed=1.0):
    """Returns list of (audio, [(start,end,word)]) per scene, and engine name.
    Order: cloned voice (if assets/voice_ref.wav exists) -> Edge Andrew -> offline Kokoro."""
    mode = os.environ.get("VOICE_MODE", "auto")
    if mode in ("auto", "clone") and os.path.exists(REF):
        try:
            return clone_scenes(texts, speed), "clone"
        except Exception as e:
            print("Cloned voice failed, falling back to Andrew:", type(e).__name__, str(e)[:200])
    try:
        rate = f"{int(round((speed - 1) * 100)):+d}%"
        out = []
        for tx in texts:
            mp3, b = asyncio.run(_edge(spoken(tx), rate))
            a = decode(mp3, tmp)
            end = int((b[-1][1] + 0.12) * SR) if b else len(a)
            out.append((a[:end], b))
        return out, "edge"
    except Exception as e:  # network blocked etc.
        print("Edge voice unavailable, using offline Kokoro voice:", type(e).__name__, str(e)[:120])
    from kokoro_onnx import Kokoro
    k = Kokoro(MODEL, VOICES)
    def synth(text):
        a, sr = k.create(text, voice=os.environ.get("KOKORO_VOICE", "am_michael"), speed=speed, lang="en-us")
        return a.astype(np.float32)
    out = [sentence_timed(tx, synth, 1.0) for tx in texts]
    return out, "kokoro"

def build_audio(story, tmp):
    texts = [s["say"] for s in story["scenes"]]
    speed = float(story.get("speed", 1.0))
    lead, gap, tail = 0.15, 0.22, 1.0
    fixed = lead + gap * (len(texts) - 1) + tail
    res, eng = tts_scenes(texts, tmp, speed)
    for attempt in range(3):
        total = fixed + sum(len(a) / SR for a, _ in res)
        if total <= MAX_LEN:
            break
        factor = (total - fixed) / (MAX_LEN - 0.6 - fixed)
        print(f"Too long ({total:.1f}s); speeding voice up x{factor:.3f}")
        if eng == "edge":
            speed *= factor
            res, eng = tts_scenes(texts, tmp, speed)
        else:  # time-stretch the audio we already have (no pitch change), scale word timings
            res = [(atempo(a, factor), [(s_ / factor, e_ / factor, w) for s_, e_, w in b]) for a, b in res]
    t = lead
    chunks = [np.zeros(int(lead * SR), np.float32)]
    words, scenes = [], []
    for i, (a, b) in enumerate(res):
        st = t
        orig = texts[i].split()
        for j, (s, e, w) in enumerate(b):
            disp = w
            # keep original punctuation for caption grouping when tokens line up
            if j < len(orig) and re.sub(r"\W", "", orig[j]).lower() == re.sub(r"\W", "", w).lower():
                disp = orig[j]
            words.append({"w": disp, "s": t + s, "e": t + e, "scene": i})
        chunks.append(a)
        t += len(a) / SR
        if i < len(res) - 1:
            chunks.append(np.zeros(int(gap * SR), np.float32))
            t += gap
        scenes.append({"s": st, "e": t})
    chunks.append(np.zeros(int(tail * SR), np.float32))
    total = t + tail
    scenes[-1]["e"] = total
    path = os.path.join(tmp, "voice.wav")
    sf.write(path, np.concatenate(chunks), SR)
    print(f"voice: {eng}, {total:.1f}s, {len(words)} words")
    return path, words, scenes, total

def make_music(total, cuts, hits, tmp, seed=0):
    rng = np.random.default_rng(seed)
    n = int(total * SR)
    tt = np.arange(n) / SR
    root = rng.choice([49.0, 55.0, 58.27])
    drone = np.zeros(n)
    for mult, amp in [(1, 0.5), (1.5, 0.2), (2, 0.25), (3, 0.07), (4.757, 0.05)]:
        lfo = 0.6 + 0.4 * np.sin(2 * np.pi * (0.04 + 0.015 * mult) * tt + rng.random() * 6)
        drone += amp * lfo * np.sin(2 * np.pi * root * mult * tt + rng.random() * 6)
    # soft ticking clock pulse for tension
    pulse = np.zeros(n)
    kl = int(0.25 * SR); kt = np.arange(kl) / SR
    kick = np.sin(2 * np.pi * (58 * np.exp(-kt * 9)) * kt) * np.exp(-kt * 14)
    p = 0.0
    while p < total - 0.5:
        for off, a in ((0, 1.0), (0.22, 0.55)):
            i = int((p + off) * SR); j = min(n, i + kl)
            pulse[i:j] += a * kick[: j - i]
        p += 1.05
    bed = 0.5 * drone + 0.33 * pulse
    wl = int(0.7 * SR)
    noise = np.convolve(rng.standard_normal(wl), np.ones(40) / 40, mode="same")
    whoosh = noise * np.sin(np.linspace(0, np.pi, wl)) ** 2 * 1.6
    for s in cuts:
        i = int(max(0, s - 0.35) * SR); j = min(n, i + wl)
        bed[i:j] += whoosh[: j - i]
    bl = int(1.2 * SR); bt = np.arange(bl) / SR
    boom = np.sin(2 * np.pi * (45 * np.exp(-bt * 2)) * bt) * np.exp(-bt * 3.5) * 2.2
    for h in hits:
        i = int(h * SR); j = min(n, i + bl)
        bed[i:j] += boom[: j - i]
    f = int(0.6 * SR)
    bed[:f] *= np.linspace(0, 1, f); bed[-f:] *= np.linspace(1, 0, f)
    bed = bed / (np.max(np.abs(bed)) + 1e-9) * 0.9
    path = os.path.join(tmp, "music.wav")
    sf.write(path, bed.astype(np.float32), SR)
    return path

# ------------------------------------------------------------------ timeline evaluation
def val(v, p, default=0.0):
    """v may be a number or [start, end] (eased across the scene) or [a,b,c...] keyframes."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    if len(v) == 1:
        return float(v[0])
    p = ease_io(p)
    seg = p * (len(v) - 1)
    i = min(int(seg), len(v) - 2)
    return lerp(float(v[i]), float(v[i + 1]), ease_io(seg - i))

CAM_PRESETS = {
    "push_in": {"zoom": [1.04, 1.16], "pan": [0, 0]},
    "pull_out": {"zoom": [1.18, 1.04], "pan": [0, 0]},
    "pan_left": {"zoom": [1.12, 1.12], "pan": [60, -60]},
    "pan_right": {"zoom": [1.12, 1.12], "pan": [-60, 60]},
    "drift": {"zoom": [1.06, 1.1], "pan": [-20, 20]},
    "rise": {"zoom": [1.1, 1.1], "pany": [60, -60]},
}

class Stage:
    def __init__(self, story):
        self.story = story
        self.cast = {k: Character(dict(v, name=k)) for k, v in story.get("cast", {}).items()}

    def draw_scene(self, c, sc, lt, dur):
        self.first = sc is self.story["scenes"][0]
        p = clamp(lt / max(dur, 0.1))
        cam = sc.get("camera", "drift")
        if isinstance(cam, str):
            cam = CAM_PRESETS.get(cam, CAM_PRESETS["drift"])
        zoom = val(cam.get("zoom"), p, 1.08)
        panx = val(cam.get("pan"), p, 0.0)
        pany = val(cam.get("pany"), p, 0.0)
        zoom = max(zoom, 1.0 + (abs(panx) + abs(pany)) / (W / 2) + 0.02)
        c.save()
        c.translate(W / 2, H / 2); c.scale(zoom, zoom); c.translate(-W / 2 - panx, -H / 2 - pany)
        BACKGROUNDS.get(sc.get("bg", "black"), bg_black)(c, lt, panx * 3 + lt * 6, sc.get("bg_opts", {}))
        items = []
        for pr in sc.get("props", []):
            items.append((pr.get("z", 0), "prop", pr))
        for ca in sc.get("cast", []):
            items.append((ca.get("z", 1), "char", ca))
        for _, kind, it in sorted(items, key=lambda x: x[0]):
            (self.draw_prop if kind == "prop" else self.draw_char)(c, it, lt, p, dur)
        c.restore()
        if sc.get("text"):
            self.draw_overlay_text(c, sc["text"], lt)

    def appear(self, it, lt):
        a0 = float(it.get("appear", 0.0))
        if self.first and a0 <= 0:
            a0 = -1.0
        return ease_out((lt - a0) / 0.5), lt - a0

    def draw_char(self, c, ca, lt, p, dur):
        ch = self.cast.get(ca["id"])
        if not ch:
            return
        a, lt2 = self.appear(ca, lt)
        if a <= 0:
            return
        x = val(ca.get("x"), p, 0.5) * W
        y = val(ca.get("y"), p, 0.86) * H
        s = val(ca.get("scale"), p, 1.0)
        enter = ca.get("enter", "fade")
        if enter == "left":
            x -= (1 - a) * 700
        elif enter == "right":
            x += (1 - a) * 700
        elif enter == "drop":
            y -= (1 - a) * 900
        elif enter == "rise":
            y += (1 - a) * 500
        rot = val(ca.get("rot"), p, 0.0)
        if ca.get("sway"):
            rot += ca["sway"] * math.sin(lt * 1.3)
            x += 25 * math.sin(lt * 0.9)
        if ca.get("chute"):
            hs = ch.hscale
            c.save(); c.translate(x, y); c.rotate(rot); c.translate(0, -735 * 0.62 * s * hs)
            prop(c, "parachute", 0, -239 * s, 0.8 * s, lt, {"color": ca.get("chute_color", "#e8e2d4")})
            c.restore()
        alpha = int(255 * a) if enter == "fade" else 255
        if alpha < 255:
            c.saveLayerAlpha(None, alpha)
        hand = ch.draw(c, x, y, 0.62 * s, lt + h01(ca["id"]) * 10, ca.get("action", "stand"),
                       ca.get("face", 1), ca.get("expr", "neutral"), talk=ca.get("talk", False), rot=rot)
        if ca.get("hold"):
            # hand position in world coords: approximate with character transform
            hx, hy = hand["hand"]
            sc_ = 0.62 * s * ch.hscale
            wx = x + hx * sc_ * ca.get("face", 1)
            wy = y + hy * sc_
            prop(c, ca["hold"], wx, wy + 30 * sc_, 0.7 * s, lt, ca.get("hold_opts", {}))
        if alpha < 255:
            c.restore()

    def draw_prop(self, c, pr, lt, p, dur):
        a, lt2 = self.appear(pr, lt)
        if a <= 0:
            return
        x = val(pr.get("x"), p, 0.5) * W
        y = val(pr.get("y"), p, 0.6) * H
        s = val(pr.get("scale"), p, 1.0)
        m = pr.get("motion", "pop")
        rot = val(pr.get("rot"), p, 0.0)
        if m == "pop":
            s *= 0.6 + 0.4 * ease_back(clamp(lt2 / 0.45))
        elif m == "drop":
            y -= (1 - ease_out(clamp(lt2 / 0.6))) * 700
        elif m == "float":
            y += 14 * math.sin(lt * 1.4); rot += 3 * math.sin(lt * 0.9)
        elif m == "slam":
            s *= 1 + 1.2 * (1 - ease_out(clamp(lt2 / 0.25)))
        opts = dict(pr.get("opts", {}))
        if pr["kind"] == "poster" and opts.get("char") in self.cast:
            opts["char"] = self.cast[opts["char"]]
        if pr["kind"] == "plane_side" and "stairs" in opts:
            opts["stairs"] = val(opts["stairs"], p, 0)
        c.save()
        c.translate(x, y); c.rotate(rot)
        c.saveLayerAlpha(None, int(255 * a)) if a < 1 else None
        prop(c, pr["kind"], 0, 0, s, lt, opts)
        if a < 1:
            c.restore()
        c.restore()

    def draw_overlay_text(self, c, tx, lt):
        y = tx.get("y", 0.26) * H
        big = tx.get("big", "")
        if big:
            f = fit(big, FONT_BIG, W - 140, tx.get("size", 150))
            total = text_w(big, f)
            x = W / 2 - total / 2
            for i, ch in enumerate(big):
                a = ease_out((lt - 0.15 - i * 0.045) / 0.35)
                if a <= 0:
                    break
                yy = y + (1 - a) * 40
                c.drawString(ch, x, yy, f, stroke("#000000", 10, int(200 * a)))
                c.drawString(ch, x, yy, f, fill(tx.get("color", "#f5f2ec"), int(255 * a)))
                x += text_w(ch, f)
        if tx.get("sub"):
            a = ease_out((lt - 0.5) / 0.5)
            f = font(FONT_TYPE, 52)
            wsub = text_w(tx["sub"], f)
            c.drawRect(rect(W / 2 - wsub / 2 - 20, y + 30, (wsub + 40) * a, 70), fill("#c0392b", int(230 * a)))
            draw_text_c(c, tx["sub"], W / 2, y + 82, f, "#ffffff", int(255 * a))

# ------------------------------------------------------------------ overlays
def caption_groups(words, max_words=3, max_chars=15):
    groups, cur = [], []
    for w in words:
        if cur and cur[-1]["scene"] != w["scene"]:
            groups.append(cur); cur = []
        cur.append(w)
        txt = " ".join(x["w"] for x in cur)
        if len(cur) >= max_words or len(txt) >= max_chars or re.search(r"[.,!?;:…]$", w["w"]):
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)
    for i, g in enumerate(groups):
        g_end = groups[i + 1][0]["s"] if i + 1 < len(groups) else g[-1]["e"] + 0.4
        for w in g:
            w["g_end"] = min(g_end, g[-1]["e"] + 0.6)
    return groups

def draw_captions(c, groups, t):
    f0 = font(FONT_BIG, 100)
    for g in groups:
        s, e = g[0]["s"] - 0.03, g[0]["g_end"] - 0.03
        if not (s <= t < e):
            continue
        a_in = ease_out((t - s) / 0.14)
        a_out = 1 - ease_io((t - (e - 0.06)) / 0.06)
        a = clamp(min(a_in, a_out))
        toks = [re.sub(r"[\"“”]", "", x["w"]).upper() for x in g]
        sp = 26
        f = f0
        ws = [text_w(tk, f) for tk in toks]
        tot = sum(ws) + sp * (len(toks) - 1)
        if tot > W - 120:
            f = font(FONT_BIG, 100 * (W - 120) / tot)
            ws = [text_w(tk, f) for tk in toks]; tot = sum(ws) + sp * (len(toks) - 1)
        y = 1380 + (1 - a_in) * 30
        x = W / 2 - tot / 2
        for tk, wd, w in zip(toks, ws, g):
            k = clamp(min((t - w["s"] + 0.04) / 0.08, (w["e"] + 0.1 - t) / 0.12))
            k = ease_io(k)
            col = tuple(int(lerp(a_, b_, k)) for a_, b_ in zip((255, 255, 255), (255, 214, 10)))
            scl = 1 + 0.1 * k
            c.save(); c.translate(x + wd / 2, y); c.scale(scl, scl)
            c.drawString(tk, -wd / 2, 0, f, stroke("#000000", 14, int(255 * a)))
            c.drawString(tk, -wd / 2, 0, f, fill(col + (int(255 * a),)))
            c.restore()
            x += wd + sp

def draw_banner(c, text, t0, t, dur=2.4, y=330, color="#c0392b"):
    d = t - t0
    if not text or d < 0 or d > dur:
        return
    a = ease_out(d / 0.35) * (1 - ease_io((d - (dur - 0.35)) / 0.35))
    f = fit(text, FONT_BIG, W - 180, 88)
    w = text_w(text, f)
    x = W / 2 + (1 - ease_out(d / 0.35)) * -300 + ease_io((d - (dur - 0.35)) / 0.35) * 300
    c.save(); c.translate(x, y); c.rotate(-2)
    c.drawRoundRect(rect(-w / 2 - 34, -70, w + 68, 104), 14, 14, fill(color, int(240 * a)))
    draw_text_c(c, text, 0, 4, f, "#ffffff", int(255 * a))
    c.restore()

def draw_particles(c, t):
    for i in range(26):
        x = (h01(i) * W + 40 * math.sin(t * 0.3 + i)) % W
        y = (h01(i + 50) * H - t * (10 + 20 * h01(i + 9))) % H
        c.drawCircle(x, y, 2 + 2 * h01(i + 3), fill("#fff5dc", int(40 + 40 * math.sin(t + i))))

def vignette_paint():
    p = skia.Paint(AntiAlias=True)
    p.setShader(skia.GradientShader.MakeRadial(skia.Point(W / 2, H / 2), H * 0.72,
                                               [hexcol("#000000", 0), hexcol("#000000", 0), hexcol("#000000", 200)], [0, 0.55, 1.0]))
    return p

# ------------------------------------------------------------------ frame rendering
TRANS = 0.32  # half-length of a transition (s)

def render_frame(c, st, tl, t):
    story, scenes, groups, total = st.story, tl["scenes"], tl["groups"], tl["total"]
    c.clear(hexcol("#000000"))
    # which scene(s)
    idx = 0
    for i, s in enumerate(scenes):
        if t >= s["s"]:
            idx = i
    cur = scenes[idx]
    nxt_i = idx + 1 if idx + 1 < len(scenes) and t > scenes[idx + 1]["s"] - TRANS else None
    prv_i = idx - 1 if idx > 0 and t < cur["s"] + TRANS else None
    pair = None
    if nxt_i is not None:
        pair = (idx, nxt_i, scenes[nxt_i]["s"])
    elif prv_i is not None:
        pair = (prv_i, idx, cur["s"])
    if pair:
        a, b, B = pair
        q = ease_io((t - (B - TRANS)) / (2 * TRANS))
        kind = story["scenes"][b].get("transition", ["push_left", "zoom", "push_right", "zoom"][b % 4])
        sa, sb = scenes[a], scenes[b]
        if kind.startswith("push"):
            d = -1 if kind == "push_left" else 1
            c.save(); c.translate(d * W * q, 0)
            st.draw_scene(c, story["scenes"][a], t - sa["s"], sa["e"] - sa["s"]); c.restore()
            c.save(); c.translate(-d * W * (1 - q), 0)
            st.draw_scene(c, story["scenes"][b], t - sb["s"], sb["e"] - sb["s"]); c.restore()
        else:  # zoom through: A zooms in & fades, B settles from slightly larger
            c.save(); z = 1 + 0.35 * q; c.translate(W / 2, H / 2); c.scale(z, z); c.translate(-W / 2, -H / 2)
            st.draw_scene(c, story["scenes"][a], t - sa["s"], sa["e"] - sa["s"]); c.restore()
            c.saveLayerAlpha(None, int(255 * q))
            z = 1.25 - 0.25 * q; c.translate(W / 2, H / 2); c.scale(z, z); c.translate(-W / 2, -H / 2)
            st.draw_scene(c, story["scenes"][b], t - sb["s"], sb["e"] - sb["s"]); c.restore()
    else:
        st.draw_scene(c, story["scenes"][idx], t - cur["s"], cur["e"] - cur["s"])
    draw_particles(c, t)
    c.drawRect(rect(0, 0, W, H), tl["vig"])
    # opening hook + per-scene re-hooks
    draw_banner(c, story.get("hook"), 0.0, t, dur=3.2, y=330)
    for i, s in enumerate(scenes):
        if story["scenes"][i].get("hook"):
            draw_banner(c, story["scenes"][i]["hook"], s["s"], t, dur=2.6, y=330, color="#c0392b" if i % 2 else "#d4a017")
    draw_captions(c, groups, t)
    # fade in/out of whole video (first frame still has content, just slightly dimmed)
    if t > total - 0.6:
        c.drawRect(rect(0, 0, W, H), fill("#000000", int(255 * ease_io((t - (total - 0.6)) / 0.6))))

def worker(args):
    story, tl, f0, f1, out = args
    tl = dict(tl)
    tl["vig"] = vignette_paint()
    st = Stage(story)
    info = skia.ImageInfo.Make(W, H, skia.kBGRA_8888_ColorType, skia.kPremul_AlphaType)
    surf = skia.Surface.MakeRaster(info)
    c = surf.getCanvas()
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", os.environ.get("X264_PRESET", "veryfast"),
                           "-crf", "19", "-pix_fmt", "yuv420p", "-g", str(FPS * 2), out], stdin=subprocess.PIPE)
    buf = np.empty((H, W, 4), np.uint8)
    for fi in range(f0, f1):
        render_frame(c, st, tl, fi / FPS)
        surf.readPixels(info, buf, W * 4)
        ff.stdin.write(buf.tobytes())
    ff.stdin.close(); ff.wait()
    return out

def render(story_path, out_path, preview=None):
    story = json.load(open(story_path))
    tmp = tempfile.mkdtemp()
    voice, words, scenes, total = build_audio(story, tmp)
    hits = [0.05] + [s["s"] for i, s in enumerate(scenes) if story["scenes"][i].get("hook")]
    music = make_music(total, [s["s"] for s in scenes[1:]], hits, tmp, seed=sum(map(ord, story.get("id", "x"))))
    groups = caption_groups(words)
    tl = {"scenes": scenes, "groups": groups, "total": total}
    end_t = min(total, preview) if preview else total
    nframes = int(end_t * FPS)
    nw = max(1, min(mp.cpu_count(), 8))
    bounds = [round(i * nframes / nw) for i in range(nw + 1)]
    parts = [os.path.join(tmp, f"part{i}.mp4") for i in range(nw)]
    jobs = [(story, tl, bounds[i], bounds[i + 1], parts[i]) for i in range(nw)]
    with mp.Pool(nw) as pool:
        pool.map(worker, jobs)
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    silent = os.path.join(tmp, "video.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent], check=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", voice, "-i", music,
        "-filter_complex",
        "[2:a]volume=0.15[m];[1:a][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", "-t", f"{end_t:.3f}", out_path,
    ], check=True)
    print(f"rendered {out_path}: {end_t:.1f}s at {FPS}fps")
    return total

if __name__ == "__main__":
    pv = None
    if "--preview" in sys.argv:
        pv = float(sys.argv[sys.argv.index("--preview") + 1])
    render(sys.argv[1], sys.argv[2], pv)
