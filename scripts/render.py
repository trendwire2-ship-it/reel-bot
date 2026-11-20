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
from rig import Character, UPPER, FORE, THIGH  # noqa: F811  (cinematic rig replaces the old one)
from worlds import WORLDS

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
def chunk_text(tx, limit=280):
    sents = [x for x in re.split(r"(?<=[.!?…])\s+", tx.strip()) if x]
    out, cur = [], ""
    for snt in sents:
        if cur and len(cur) + len(snt) + 1 > limit:
            out.append(cur); cur = snt
        else:
            cur = (cur + " " + snt).strip()
    if cur:
        out.append(cur)
    return out

def align_words(text, a):
    """Word timings for one continuous take: split at punctuation phrases, match phrase breaks to the
    longest pauses actually present in the audio, spread words by spoken length inside each phrase."""
    words = text.split()
    phrases, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[,.;:!?…]$", w):
            phrases.append(cur); cur = []
    if cur:
        phrases.append(cur)
    hop = int(0.01 * SR)
    env = np.array([np.sqrt(np.mean(a[i:i + hop] ** 2)) for i in range(0, max(1, len(a) - hop), hop)])
    thr = max(1e-4, np.percentile(env, 30) * 0.6)
    quiet = env < thr
    gaps, i = [], 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            if j - i >= 8 and i > 5 and j < len(quiet) - 5:
                gaps.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    nz = np.where(env > thr)[0]
    t0, t1 = (nz[0] * 0.01, nz[-1] * 0.01 + 0.01) if len(nz) else (0.0, len(a) / SR)
    need = len(phrases) - 1
    spans = []
    lens = [sum(len(normalize(w)) + 2 for w in ph) for ph in phrases]
    if need > 0 and len(gaps) >= need:
        best = sorted(sorted(gaps, key=lambda g: g[1] - g[0], reverse=True)[:need])
        starts = [t0] + [g[1] for g in best]
        ends = [g[0] for g in best] + [t1]
        spans = list(zip(starts, ends))
        speech = sum(e_ - s_ for s_, e_ in spans)
        for (s_, e_), ln in zip(spans, lens):  # sanity: a phrase can't be far shorter/longer than its text
            exp = speech * ln / sum(lens)
            if not (0.45 * exp <= e_ - s_ <= 2.2 * exp):
                spans = []
                break
    if not spans:
        tot = sum(sum(len(normalize(w)) + 2 for w in ph) for ph in phrases)
        acc = t0
        for ph in phrases:
            d = (t1 - t0) * sum(len(normalize(w)) + 2 for w in ph) / max(tot, 1)
            spans.append((acc, acc + d)); acc += d
    out = []
    for ph, (s_, e_) in zip(phrases, spans):
        wts = [len(normalize(w)) + 2 for w in ph]
        acc = s_
        for w, wt in zip(ph, wts):
            d = (e_ - s_) * wt / sum(wts)
            out.append((acc, acc + d * 0.95, w)); acc += d
    return out

def clone_scenes(texts, speed):
    """User's own cloned voice (Chatterbox, MIT licence) from assets/voice_ref.wav.
    Each scene is voiced as one continuous take (smooth, natural intonation), level-matched, with soft joins."""
    import torch, torchaudio
    from chatterbox.tts import ChatterboxTTS
    if "m" not in _clone:
        torch.set_num_threads(os.cpu_count() or 2)
        torch.manual_seed(7)
        _clone["m"] = ChatterboxTTS.from_pretrained(device="cpu")
    m = _clone["m"]
    def synth(text):
        wav = m.generate(text, audio_prompt_path=REF,
                         exaggeration=float(os.environ.get("VOICE_EXAGGERATION", "0.45")),
                         cfg_weight=float(os.environ.get("VOICE_CFG", "0.5")),
                         temperature=float(os.environ.get("VOICE_TEMP", "0.7")))
        if m.sr != SR:
            wav = torchaudio.functional.resample(wav, m.sr, SR)
        a = wav.squeeze().cpu().numpy().astype(np.float32)
        nz = np.where(np.abs(a) > 0.008)[0]
        if len(nz):
            a = a[max(0, nz[0] - 240): nz[-1] + 2400]
        f = min(len(a) // 4, int(0.015 * SR))
        if f > 0:
            a[:f] *= np.linspace(0, 1, f); a[-f:] *= np.linspace(1, 0, f)
        rms = np.sqrt(np.mean(a[np.abs(a) > 0.01] ** 2)) if np.any(np.abs(a) > 0.01) else 0.1
        return a * (0.1 / max(rms, 1e-4))
    out = []
    for tx in texts:
        pieces, words, t = [], [], 0.0
        for ch in chunk_text(tx):
            a = synth(normalize(ch))
            for s_, e_, w in align_words(ch, a):
                words.append((t + s_, t + e_, w))
            pieces += [a, np.zeros(int(0.16 * SR), np.float32)]
            t += len(a) / SR + 0.16
        audio = np.concatenate(pieces[:-1]) if pieces else np.zeros(1, np.float32)
        if abs(speed - 1.0) > 0.01:
            audio = atempo(audio, speed)
            words = [(s_ / speed, e_ / speed, w) for s_, e_, w in words]
        out.append((audio, words))
    return out

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
    "push_in": {"zoom": [1.04, 1.17], "pan": [0, 0]},
    "pull_out": {"zoom": [1.2, 1.04], "pan": [0, 0]},
    "pan_left": {"zoom": [1.1, 1.12], "pan": [80, -80]},
    "pan_right": {"zoom": [1.1, 1.12], "pan": [-80, 80]},
    "drift": {"zoom": [1.06, 1.11], "pan": [-30, 30]},
    "rise": {"zoom": [1.1, 1.12], "pany": [90, -90]},
    "track_left": {"zoom": [1.08, 1.08], "pan": [140, -140]},
    "track_right": {"zoom": [1.08, 1.08], "pan": [-140, 140]},
    "crane_down": {"zoom": [1.14, 1.06], "pany": [-120, 60]},
}
LEGACY_TRANS = {"zoom": "push", "push_left": "whip_left", "push_right": "whip_right"}
TRANS_CYCLE = ["whip_left", "push", "fog", "whip_right", "flash", "dissolve"]

def smooth_shake(t, seed=0.0):
    return (math.sin(t * 23.0 + seed) * 0.6 + math.sin(t * 37.0 + seed * 2) * 0.3 + math.sin(t * 11.0 + seed * 3) * 0.4,
            math.sin(t * 29.0 + seed * 5) * 0.6 + math.sin(t * 17.0 + seed) * 0.4)

class Stage:
    def __init__(self, story):
        self.story = story
        self.cast = {k: Character(dict(v, name=k)) for k, v in story.get("cast", {}).items()}
        self.worlds = {}
        self.first = False

    def world(self, idx, sc):
        if idx not in self.worlds:
            self.worlds[idx] = WORLDS.get(sc.get("bg", "black"), WORLDS["black"])(sc.get("bg_opts", {}))
        return self.worlds[idx]

    def cam_apply(self, c, zoom, panx, pany, depth):
        z = 1 + (zoom - 1) * depth
        c.translate(W / 2, H / 2); c.scale(z, z); c.translate(-W / 2 - panx * depth, -H / 2 - pany * depth)

    def draw_scene(self, c, idx, lt, dur):
        sc = self.story["scenes"][idx]
        self.first = idx == 0
        wd = self.world(idx, sc)
        p = clamp(lt / max(dur, 0.1))
        cam = sc.get("camera", "drift")
        if isinstance(cam, str):
            cam = CAM_PRESETS.get(cam, CAM_PRESETS["drift"])
        zoom = max(1.0, val(cam.get("zoom"), p, 1.08))
        panx = val(cam.get("pan"), p, 0.0)
        pany = val(cam.get("pany"), p, 0.0)
        # gentle handheld float + scripted shakes
        fx, fy = math.sin(lt * 0.31 + idx) * 6, math.sin(lt * 0.23 + idx * 2) * 5
        for t0, d, amp in sc.get("shake", []):
            e = clamp((lt - t0) / max(d, 0.05))
            if 0 < e < 1:
                env = math.sin(e * math.pi) ** 0.7 * (1 - e) ** 0.5
                sx, sy = smooth_shake(lt, idx)
                fx += sx * amp * env; fy += sy * amp * env
        c.save(); c.translate(fx, fy)
        for depth, fn, fg in wd["layers"]:
            if fg:
                continue
            c.save(); self.cam_apply(c, zoom, panx, pany, depth); fn(c, lt, sc.get("bg_opts", {})); c.restore()
        c.save(); self.cam_apply(c, zoom, panx, pany, 1.0)
        items = [(pr.get("z", 0), "prop", pr) for pr in sc.get("props", [])] + [(ca.get("z", 1), "char", ca) for ca in sc.get("cast", [])]
        for _, kind, it in sorted(items, key=lambda x: x[0]):
            (self.draw_prop if kind == "prop" else self.draw_char)(c, it, lt, p, dur, wd)
        c.restore()
        for depth, fn, fg in wd["layers"]:
            if fg:
                c.save(); self.cam_apply(c, zoom, panx, pany, depth); fn(c, lt, sc.get("bg_opts", {})); c.restore()
        c.restore()
        if sc.get("text"):
            draw_title(c, sc["text"], lt)
        if sc.get("label"):
            draw_label(c, sc["label"], lt)
        return wd

    def appear(self, it, lt):
        a0 = float(it.get("appear", 0.0))
        if self.first and a0 <= 0:
            a0 = -1.0
        return ease_out((lt - a0) / 0.55), lt - a0

    def draw_char(self, c, ca, lt, p, dur, wd):
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
            rot += ca["sway"] * math.sin(lt * 1.1 + 0.4)
            x += 22 * math.sin(lt * 0.8)
        face = val(ca.get("face"), p, 1.0)
        sc_ = 0.62 * s * ch.hscale
        alpha = int(255 * a) if enter == "fade" else 255
        if alpha < 255:
            c.saveLayerAlpha(None, alpha)
        if ca.get("chute"):
            c.save(); c.translate(x, y); c.rotate(rot)
            cs = 0.82 * s
            hands = (80 * ch.bw + math.sin(math.radians(163)) * (UPPER + FORE)) * sc_ / cs
            prop(c, "parachute", 0, -(1118 * sc_ + 260 * 1.18 * cs), cs, lt, {"color": ca.get("chute_color", "#e8e2d4"), "hands": hands})
            c.restore()
        phase = None
        act = ca.get("action", "stand")
        if act in ("walk", "run") and isinstance(ca.get("x"), list):
            # drive the step cycle from distance actually travelled so feet plant instead of sliding
            amp = 1.0 if act == "walk" else 1.55
            stride = 4 * THIGH * math.sin(math.radians(27 * amp)) * sc_  # px per full cycle (two steps)
            x0 = val(ca.get("x"), 0.0, 0.5) * W
            travelled = abs(x - x0)
            phase = travelled / max(stride, 1) * 2 * math.pi + h01(ca["id"]) * 6
            dp = 0.02
            vx = (val(ca.get("x"), min(1.0, p + dp), 0.5) - val(ca.get("x"), max(0.0, p - dp), 0.5)) * W / (2 * dp * max(dur, 0.1))
            if abs(vx) > 5 and "face" not in ca:
                face = 1.0 if vx > 0 else -1.0
            elif abs(vx) > 5 and (vx > 0) != (face > 0):
                face = -face  # never walk backwards
            if abs(vx) < 25:
                act = "stand"
        res = ch.draw(c, x, y, 0.62 * s, lt + h01(ca["id"]) * 10, act, face, ca.get("expr", "neutral"),
                      talk=ca.get("talk", False), rot=rot, light=wd["light"], at=lt2, phase=phase)
        if ca.get("hold"):
            hx, hy = res["hand"]
            fs = 1 if face >= 0 else -1
            r = math.radians(rot)
            wx_, wy_ = hx * res["sc"] * fs, hy * res["sc"]
            wx = x + wx_ * math.cos(r) - wy_ * math.sin(r)
            wy = y + wx_ * math.sin(r) + wy_ * math.cos(r)
            prop(c, ca["hold"], wx, wy + 36 * res["sc"], 0.62 * s, lt, ca.get("hold_opts", {}))
        if alpha < 255:
            c.restore()

    def draw_prop(self, c, pr, lt, p, dur, wd):
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
        c.save(); c.translate(x, y); c.rotate(rot)
        if a < 1:
            c.saveLayerAlpha(None, int(255 * a))
        if pr["kind"] not in ("stamp", "bills"):
            sh = skia.Paint(AntiAlias=True); sh.setImageFilter(skia.ImageFilters.DropShadow(14, 22, 18, 18, hexcol("#000000", 110), None))
            ext = 520 * s if pr["kind"] != "plane_side" else 560 * s
            c.saveLayer(rect(-ext, -ext, 2 * ext, 2 * ext), sh); prop(c, pr["kind"], 0, 0, s, lt, opts); c.restore()
        else:
            prop(c, pr["kind"], 0, 0, s, lt, opts)
        if a < 1:
            c.restore()
        c.restore()

# ------------------------------------------------------------------ documentary typography
def count_up(txt, k):
    m = re.match(r"^(\$)?([\d,]+)(.*)$", txt)
    if not m:
        return txt
    n = int(m.group(2).replace(",", ""))
    v = int(round(n * k))
    return (m.group(1) or "") + (f"{v:,}" if "," in m.group(2) else str(v)) + m.group(3)

def draw_title(c, tx, lt):
    y = tx.get("y", 0.26) * H
    big = tx.get("big", "")
    if big:
        k = ease_out(clamp((lt - 0.1) / 0.9))
        shown = count_up(big, k) if re.match(r"^\$?[\d,]+", big) else big
        f = fit(big, FONT_BIG, W - 160, tx.get("size", 150))
        spacing = lerp(18, 4, ease_out(clamp(lt / 0.8)))
        widths = [text_w(ch, f) for ch in shown]
        total = sum(widths) + spacing * (len(shown) - 1)
        x = W / 2 - total / 2
        c.save()
        c.clipRect(rect(0, y - f.getSize() * 1.1, W, f.getSize() * 1.25))
        for i, ch in enumerate(shown):
            a = ease_out((lt - 0.08 - i * 0.035) / 0.4)
            if a <= 0:
                break
            yy = y + (1 - a) * f.getSize()
            sh = skia.Paint(AntiAlias=True, Color=hexcol("#000000", int(150 * a)))
            sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 10))
            c.drawString(ch, x + 4, yy + 8, f, sh)
            c.drawString(ch, x, yy, f, fill(tx.get("color", "#f3efe6"), int(255 * a)))
            x += widths[i] + spacing
        c.restore()
    if tx.get("sub"):
        f = font(FONT_TYPE, 46)
        full = tx["sub"]
        n = int(clamp((lt - 0.55) / 0.9) * len(full) + 0.999)
        wsub = text_w(full, f)
        ux = ease_io((lt - 0.45) / 0.5)
        c.drawRect(rect(W / 2 - wsub / 2 - 16, y + 34, (wsub + 32) * ux, 6), fill("#c0302a"))
        if n > 0:
            c.drawString(full[:n], W / 2 - wsub / 2, y + 96, f, fill("#000000", 160))
            c.drawString(full[:n], W / 2 - wsub / 2 - 2, y + 93, f, fill("#efe8da"))

def draw_label(c, lb, lt):
    """Lower-third style name label (kept clear of the caption zone)."""
    y = lb.get("y", 0.62) * H
    a = ease_out((lt - lb.get("at", 0.4)) / 0.5)
    if a <= 0:
        return
    fN, fR = font(FONT_BIG, 64), font(FONT_TYPE, 34)
    w = max(text_w(lb["name"], fN), text_w(lb.get("role", ""), fR)) + 60
    x = 70
    c.save(); c.clipRect(rect(x, y - 80, w * a + 20, 160))
    c.drawRect(rect(x, y - 70, w, 130), fill("#0b0b0d", 200))
    c.drawRect(rect(x, y - 70, 8, 130), fill("#c0302a"))
    c.drawString(lb["name"], x + 30, y + 2, fN, fill("#f3efe6"))
    c.drawString(lb.get("role", ""), x + 30, y + 44, fR, fill("#c9c2b2"))
    c.restore()

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
    f0 = font(FONT_BIG, 98)
    for g in groups:
        s, e = g[0]["s"] - 0.03, g[0]["g_end"] - 0.03
        if not (s <= t < e):
            continue
        a_in = ease_out((t - s) / 0.14)
        a_out = 1 - ease_io((t - (e - 0.06)) / 0.06)
        a = clamp(min(a_in, a_out))
        toks = [re.sub(r"[\"“”]", "", x["w"]).upper() for x in g]
        sp = 24
        f = f0
        ws = [text_w(tk, f) for tk in toks]
        tot = sum(ws) + sp * (len(toks) - 1)
        if tot > W - 140:
            f = font(FONT_BIG, 98 * (W - 140) / tot)
            ws = [text_w(tk, f) for tk in toks]; tot = sum(ws) + sp * (len(toks) - 1)
        y = 1470 + (1 - a_in) * 26
        x = W / 2 - tot / 2
        for tk, wd, w in zip(toks, ws, g):
            k = ease_io(clamp(min((t - w["s"] + 0.04) / 0.08, (w["e"] + 0.1 - t) / 0.12)))
            col = tuple(int(lerp(a_, b_, k)) for a_, b_ in zip((246, 242, 234), (255, 206, 46)))
            scl = 1 + 0.08 * k
            c.save(); c.translate(x + wd / 2, y); c.scale(scl, scl)
            sh = skia.Paint(AntiAlias=True, Color=hexcol("#000000", int(170 * a)))
            sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 9))
            c.drawString(tk, -wd / 2 + 3, 7, f, sh)
            c.drawString(tk, -wd / 2, 0, f, stroke("#0a0a0a", 11, int(255 * a)))
            c.drawString(tk, -wd / 2, 0, f, fill(col + (int(255 * a),)))
            c.restore()
            x += wd + sp

def draw_banner(c, text, t0, t, dur=2.4, y=330, color="#c0302a"):
    d = t - t0
    if not text or d < 0 or d > dur:
        return
    a_in = ease_out(d / 0.4)
    a_out = ease_io((d - (dur - 0.35)) / 0.35)
    f = fit(text, FONT_BIG, W - 220, 84)
    w = text_w(text, f) + 80
    x0 = W / 2 - w / 2
    c.save()
    c.clipRect(rect(x0 + w * a_out, y - 80, w * (a_in - a_out) + 1, 130))
    c.drawRect(rect(x0, y - 70, w, 108), fill("#0b0b0d", 225))
    c.drawRect(rect(x0, y - 70, 10, 108), fill(color))
    c.drawRect(rect(x0, y + 34, w * a_in, 4), fill(color))
    c.drawString(text, x0 + 42, y + 10, f, fill("#f3efe6"))
    c.restore()

def draw_follow_card(c, text, t, total):
    """End-of-reel call to action: a pill with a pulsing FOLLOW button, above the caption zone."""
    t0 = total - 3.4
    d = t - t0
    if d < 0:
        return
    a = ease_out(d / 0.45) * (1 - ease_io((t - (total - 0.7)) / 0.5))
    if a <= 0:
        return
    f = fit(text, FONT_BIG, W - 300, 54)
    fb = font(FONT_BIG, 50)
    tw = text_w(text, f); bw = text_w("+ FOLLOW", fb) + 60
    w = tw + bw + 90
    y = 1180 + (1 - ease_out(d / 0.45)) * 60
    x0 = W / 2 - w / 2
    c.saveLayerAlpha(None, int(255 * a))
    c.drawRoundRect(rect(x0, y - 62, w, 104), 52, 52, fill("#0b0b0d", 225))
    c.drawRoundRect(rect(x0, y - 62, w, 104), 52, 52, stroke("#f3efe6", 2, 60))
    c.drawString(text, x0 + 40, y + 10, f, fill("#f3efe6"))
    pulse = 1 + 0.06 * math.sin(max(0.0, d - 0.5) * 6.0) * (1 if d > 0.5 else 0)
    bx = x0 + 40 + tw + 25
    c.save(); c.translate(bx + bw / 2, y - 10); c.scale(pulse, pulse)
    c.drawRoundRect(rect(-bw / 2, -40, bw, 80), 40, 40, fill("#c0302a"))
    c.drawString("+ FOLLOW", -bw / 2 + 30, 18, fb, fill("#ffffff"))
    c.restore()
    c.restore()

def vignette_paint():
    p = skia.Paint(AntiAlias=True)
    p.setShader(skia.GradientShader.MakeRadial(skia.Point(W / 2, H / 2), H * 0.7,
                                               [hexcol("#000000", 0), hexcol("#000000", 0), hexcol("#000000", 185)], [0, 0.52, 1.0]))
    return p

# ------------------------------------------------------------------ post-processing (bloom, grade, grain)
class Post:
    def __init__(self):
        self.small = skia.Surface(W // 4, H // 4)
        th = 0.58
        k = 1 / (1 - th)
        self.thresh = skia.ColorFilters.Matrix([k, 0, 0, 0, -th * k,
                                                0, k, 0, 0, -th * k,
                                                0, 0, k, 0, -th * k,
                                                0, 0, 0, 1, 0])
        self.vig = vignette_paint()

    def apply(self, surf, c, fi, bloom, grade):
        samp = skia.SamplingOptions(skia.FilterMode.kLinear)
        if bloom > 0:
            img = surf.makeImageSnapshot()
            sc = self.small.getCanvas(); sc.clear(skia.ColorBLACK)
            p = skia.Paint(); p.setColorFilter(self.thresh)
            sc.drawImageRect(img, skia.Rect.MakeWH(W // 4, H // 4), samp, p)
            bl = self.small.makeImageSnapshot()
            sc.clear(skia.ColorBLACK)
            pb = skia.Paint(); pb.setImageFilter(skia.ImageFilters.Blur(9, 9))
            sc.drawImage(bl, 0, 0, samp, pb)
            glow = self.small.makeImageSnapshot()
            pg = skia.Paint(); pg.setBlendMode(skia.BlendMode.kScreen); pg.setAlphaf(min(1.0, bloom * 1.6))
            c.drawImageRect(glow, skia.Rect.MakeWH(W, H), samp, pg)
        if grade and grade[1] > 0:
            pg = skia.Paint(Color=hexcol(grade[0])); pg.setBlendMode(skia.BlendMode.kSoftLight); pg.setAlphaf(min(1.0, grade[1] * 2.2))
            c.drawRect(rect(0, 0, W, H), pg)
        # gentle S-curve contrast via overlay of mid-grey is neutral; lift blacks slightly for a filmic look
        c.drawRect(rect(0, 0, W, H), fill("#14161c", 18))
        # vignette + film grain are applied by ffmpeg at encode time (much faster)

# ------------------------------------------------------------------ frame rendering
TRANS = 0.36  # half-length of a transition (s)

def scene_at(st, tl, c, idx, t):
    s = tl["scenes"][idx]
    return st.draw_scene(c, idx, t - s["s"], s["e"] - s["s"])

def render_frame(c, st, tl, t, surf=None, fi=0, post=None):
    story, scenes, groups, total = st.story, tl["scenes"], tl["groups"], tl["total"]
    c.clear(hexcol("#000000"))
    idx = 0
    for i, s in enumerate(scenes):
        if t >= s["s"]:
            idx = i
    cur = scenes[idx]
    pair = None
    if idx + 1 < len(scenes) and t > scenes[idx + 1]["s"] - TRANS:
        pair = (idx, idx + 1, scenes[idx + 1]["s"])
    elif idx > 0 and t < cur["s"] + TRANS:
        pair = (idx - 1, idx, cur["s"])
    wd = None
    if pair:
        a, b, B = pair
        q = ease_io((t - (B - TRANS)) / (2 * TRANS))
        speed = math.sin(math.pi * clamp((t - (B - TRANS)) / (2 * TRANS)))
        kind = story["scenes"][b].get("transition", TRANS_CYCLE[(b - 1) % len(TRANS_CYCLE)])
        kind = LEGACY_TRANS.get(kind, kind)
        if kind.startswith("whip"):
            d = -1 if kind == "whip_left" else 1
            bp = skia.Paint(); bp.setImageFilter(skia.ImageFilters.Blur(90 * speed + 0.01, 2 * speed + 0.01))
            c.saveLayer(None, bp)
            c.save(); c.translate(d * W * q, 0); c.clipRect(rect(0, 0, W, H)); scene_at(st, tl, c, a, t); c.restore()
            c.save(); c.translate(-d * W * (1 - q), 0); c.clipRect(rect(0, 0, W, H)); wd = scene_at(st, tl, c, b, t); c.restore()
            c.restore()
        elif kind == "push":
            bp = skia.Paint(); bp.setImageFilter(skia.ImageFilters.Blur(14 * speed + 0.01, 14 * speed + 0.01))
            c.saveLayer(None, bp)
            c.save(); z = 1 + 0.6 * q; c.translate(W / 2, H / 2); c.scale(z, z); c.translate(-W / 2, -H / 2)
            scene_at(st, tl, c, a, t); c.restore()
            c.saveLayerAlpha(None, int(255 * clamp(q * 1.6 - 0.3)))
            z = 0.88 + 0.12 * q; c.translate(W / 2, H / 2); c.scale(z, z); c.translate(-W / 2, -H / 2)
            wd = scene_at(st, tl, c, b, t); c.restore()
            c.restore()
        elif kind in ("fog", "flash", "dissolve"):
            mixk = clamp((q - 0.35) / 0.3) if kind != "dissolve" else q
            scene_at(st, tl, c, a, t)
            c.saveLayerAlpha(None, int(255 * mixk)); wd = scene_at(st, tl, c, b, t); c.restore()
            if kind == "fog":
                from worlds import draw_fog
                for k in range(3):
                    draw_fog(c, t, -200 + k * 700, 1100, "#c9cfdc", int(235 * speed), 900 * (k + 1), 5.0, k + 10)
                c.drawRect(rect(0, 0, W, H), fill("#b8c0d0", int(150 * speed ** 2)))
            elif kind == "flash":
                c.drawRect(rect(0, 0, W, H), fill("#fff3dc", int(235 * speed ** 3)))
        else:
            scene_at(st, tl, c, a if q < 0.5 else b, t)
    else:
        wd = scene_at(st, tl, c, idx, t)
    wd = wd or st.world(idx, story["scenes"][idx])
    if post is not None and surf is not None:
        post.apply(surf, c, fi, wd.get("bloom", 0.3), wd.get("grade"))
    # UI overlays (crisp, above grain)
    draw_banner(c, story.get("hook"), 0.0, t, dur=3.2, y=330)
    for i, s in enumerate(scenes):
        if story["scenes"][i].get("hook"):
            draw_banner(c, story["scenes"][i]["hook"], s["s"], t, dur=2.6, y=330, color="#c0302a" if i % 2 else "#d4a017")
    draw_captions(c, groups, t)
    if story.get("cta", "MORE TRUE STORIES DAILY"):
        draw_follow_card(c, story.get("cta", "MORE TRUE STORIES DAILY"), t, total)
    if t > total - 0.6:
        c.drawRect(rect(0, 0, W, H), fill("#000000", int(255 * ease_io((t - (total - 0.6)) / 0.6))))

def worker(args):
    story, tl, f0, f1, out = args
    st = Stage(story)
    post = Post()
    info = skia.ImageInfo.Make(W, H, skia.kBGRA_8888_ColorType, skia.kPremul_AlphaType)
    surf = skia.Surface.MakeRaster(info)
    c = surf.getCanvas()
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", os.environ.get("X264_PRESET", "veryfast"),
                           "-crf", "18", "-pix_fmt", "yuv420p", "-g", str(FPS * 2),
                           "-vf", "vignette=angle=0.5:mode=forward,noise=c0s=6:c0f=t+u", out], stdin=subprocess.PIPE)
    buf = np.empty((H, W, 4), np.uint8)
    for fi in range(f0, f1):
        render_frame(c, st, tl, fi / FPS, surf, fi, post)
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
        "[1:a]highpass=f=70,acompressor=threshold=-21dB:ratio=2.5:attack=12:release=220:makeup=2,equalizer=f=6500:t=q:w=1.2:g=-3[v];[2:a]volume=0.15[m];[v][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[a]",
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
