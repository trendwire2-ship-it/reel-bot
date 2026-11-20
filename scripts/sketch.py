"""Pencil-sketch documentary style: graphite drawing look, a new shot every ~1.5-3 s with a hand-lettered title,
camera cuts between wide/medium/close framings, slow push-in on every shot, quick blurred slide between shots."""
import math, os, re
import numpy as np
import skia
from PIL import Image, ImageFilter
from engine import W, H, hexcol, fill, stroke, clamp, ease_io, ease_out, rect, text_w, ROOT

FONT_HAND = os.path.join(ROOT, "assets/fonts/GochiHand-Regular.ttf")
SW, SH = 720, 1280          # working resolution for drawing + filter (upscaled to 1080x1920)
SLIDE = 0.26                # seconds for the slide between shots
STOP = set("a an the and or but of to in on at for with from by was were is are be been it its that this as into than then so".split())

_tf = {}
def hand(size):
    if "t" not in _tf:
        _tf["t"] = skia.Typeface.MakeFromFile(FONT_HAND)
    return skia.Font(_tf["t"], size)

# ------------------------------------------------------------------ pencil filter
class Pencil:
    def __init__(self, w=SW, h=SH):
        self.w, self.h = w, h
        rng = np.random.default_rng(1)
        yy, xx = np.mgrid[0:h, 0:w]
        def hatch(angle, spacing, width):
            a = np.radians(angle); d = xx * np.cos(a) + yy * np.sin(a)
            wob = 1.3 * np.sin(yy / 37.0 + xx / 53.0)
            return (np.abs(((d + wob) % spacing) - spacing / 2) < width).astype(np.float32)
        self.HA = hatch(45, 8, 1.0)
        self.HB = np.maximum(self.HA, hatch(-45, 8, 1.0))
        self.paper = np.asarray(Image.fromarray((rng.random((h // 4, w // 4)) * 255).astype(np.uint8))
                                .resize((w, h), Image.BICUBIC)).astype(np.float32) / 255
        self.fine = [rng.random((h, w)).astype(np.float32) for _ in range(3)]
        self.vig = (1 - 0.30 * np.clip(((xx - w / 2) / (w / 2)) ** 2 * 0.7 + ((yy - h / 2) / (h / 2)) ** 2 * 0.9 - 0.25, 0, 1)).astype(np.float32)
        self.cdf = None

    def __call__(self, bgra, fi=0):
        a = (0.114 * bgra[..., 0] + 0.587 * bgra[..., 1] + 0.299 * bgra[..., 2]).astype(np.float32) / 255
        hist, bins = np.histogram(a, 128, (0, 1))
        cdf = np.cumsum(hist).astype(np.float32); cdf /= cdf[-1]
        # smooth the equalisation curve over time so brightness never flickers between frames
        self.cdf = cdf if self.cdf is None else self.cdf * 0.85 + cdf * 0.15
        g = 0.15 + 0.85 * np.interp(a, bins[:-1], self.cdf)
        g8 = Image.fromarray((g * 255).astype(np.uint8))
        gs = np.asarray(g8.filter(ImageFilter.GaussianBlur(0.9))).astype(np.float32) / 255
        loc = np.asarray(g8.resize((self.w // 8, self.h // 8), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2))
                         .resize((self.w, self.h), Image.BILINEAR)).astype(np.float32) / 255
        ex = np.abs(np.diff(gs, axis=1, append=gs[:, -1:])); ey = np.abs(np.diff(gs, axis=0, append=gs[-1:, :]))
        e = np.clip((ex + ey) * 7.5 - 0.06, 0, 1) ** 0.7
        tone = 0.30 + 0.70 * np.clip(0.5 + (gs - 0.5) * 1.1 + (gs - loc) * 0.8, 0, 1)
        dark = 1 - tone
        h = np.where(dark > 0.55, self.HB, np.where(dark > 0.38, self.HA, 0)) * np.clip((dark - 0.3) * 1.8, 0, 1)
        out = tone * (1 - 0.22 * h) * (1 - 0.8 * e) * self.vig
        out = out * (0.95 + 0.05 * self.paper) * (0.975 + 0.025 * self.fine[(fi // 2) % 3])
        out = np.clip(out * 1.03, 0, 1)
        rgba = np.empty((self.h, self.w, 4), np.uint8)
        rgba[..., 0] = np.clip((out * 0.985 + 0.010) * 255, 0, 255)
        rgba[..., 1] = np.clip((out * 0.975 + 0.012) * 255, 0, 255)
        rgba[..., 2] = np.clip((out * 0.950 + 0.020) * 255, 0, 255)
        rgba[..., 3] = 255
        return rgba

# ------------------------------------------------------------------ shot planning
def auto_title(words):
    keep = [re.sub(r"[^\w'$%,.-]", "", w).strip(",.") for w in words]
    keep = [w for w in keep if w and w.lower() not in STOP]
    return " ".join(keep[:4]).upper() or " ".join(words[:3]).upper()

FRAMINGS = ["wide", "medium", "close", "medium", "wide", "close"]

def plan_shots(story, scenes, words):
    """Shots = (scene index, start, end, title, framing, focus). Uses scene 'beats' when given:
    [{"word": <index of the word where the shot starts>, "title": "...", "frame": "wide|medium|close", "focus": "<cast id>"}]."""
    shots = []
    for si, sc in enumerate(story["scenes"]):
        ws = [w for w in words if w["scene"] == si]
        s0, s1 = scenes[si]["s"], scenes[si]["e"]
        beats = sc.get("beats")
        if not beats:  # automatic: one shot per phrase, merging very short ones
            beats, cur, start = [], [], 0
            for i, w in enumerate(ws):
                cur.append(w["w"])
                if re.search(r"[,.;:!?…]$", w["w"]) and (w["e"] - ws[start]["s"] > 1.4 or i == len(ws) - 1):
                    beats.append({"word": start, "title": auto_title(cur)}); cur = []; start = i + 1
            if cur:
                beats.append({"word": start, "title": auto_title(cur)})
            if sc.get("hook") and beats:
                beats[0]["title"] = sc["hook"]
            if sc.get("text", {}).get("big") and beats:
                beats[0]["title"] = sc["text"]["big"]
        cast_ids = [c["id"] for c in sc.get("cast", [])]
        for bi, b in enumerate(beats):
            wi = min(max(0, int(b.get("word", 0))), max(0, len(ws) - 1))
            st = s0 if bi == 0 or not ws else ws[wi]["s"] - 0.05
            shots.append({"scene": si, "s": st, "title": b.get("title", ""),
                          "frame": b.get("frame", FRAMINGS[(si + bi) % len(FRAMINGS)] if cast_ids else ["wide", "medium"][bi % 2]),
                          "focus": b.get("focus", cast_ids[bi % len(cast_ids)] if cast_ids else None)})
    for i, sh in enumerate(shots):
        sh["e"] = shots[i + 1]["s"] if i + 1 < len(shots) else scenes[-1]["e"]
    return shots

def framing_camera(stage, sc, shot, lt, dur, sd):
    """Zoom/pan that frames the focus character (or the middle of the scene), with a slow push-in."""
    z = {"wide": 1.04, "medium": 1.38, "close": 1.95}.get(shot["frame"], 1.1)
    tx, ty = W / 2, H * 0.55
    ca = next((c for c in sc.get("cast", []) if c.get("id") == shot.get("focus")), None)
    from render import val  # local import to avoid a cycle
    p = clamp(lt / max(dur, 0.1))
    if ca is not None and shot["frame"] != "wide":
        ch = stage.cast.get(ca["id"])
        s = val(ca.get("scale"), p, 1.0)
        hs = ch.hscale if ch else 1.0
        x = val(ca.get("x"), p, 0.5) * W
        y = val(ca.get("y"), p, 0.86) * H
        tall = 0.62 * s * hs * 960
        tx = x
        ty = y - tall * (0.82 if shot["frame"] == "close" else 0.5)
    elif sc.get("props") and shot["frame"] != "wide":
        pr = sc["props"][0]
        tx, ty = val(pr.get("x"), p, 0.5) * W, val(pr.get("y"), p, 0.6) * H
    k = clamp((lt - sd) / max(0.3, shot["e"] - shot["s"]))
    z *= 1.0 + 0.06 * ease_io(k)  # slow push-in for the whole shot
    panx = tx - W / 2
    pany = ty - H / 2 - 0.06 * H / z
    lim_x = (W / 2) * (1 - 1 / z) + 40
    lim_y = (H / 2) * (1 - 1 / z) + 60
    return {"zoom": z, "pan": max(-lim_x, min(lim_x, panx)), "pany": max(-lim_y, min(lim_y, pany))}

# ------------------------------------------------------------------ titles
def wrap_title(t, f, maxw):
    words, lines, cur = t.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and f.measureText(trial) > maxw:
            lines.append(cur); cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines

def draw_title(c, title, x_off=0.0, alpha=255):
    if not title:
        return
    size = 132
    while size > 70:
        f = hand(size)
        lines = wrap_title(title.upper(), f, W - 120)
        if len(lines) <= 2:
            break
        size -= 8
    y = 210 if len(lines) == 1 else 175
    for i, ln in enumerate(lines[:3]):
        wdt = f.measureText(ln)
        x = W / 2 - wdt / 2 + x_off
        yy = y + i * size * 0.92
        c.drawString(ln, x + 1.5, yy + 1.5, f, fill("#000000", int(alpha * 0.18)))
        c.drawString(ln, x, yy, f, stroke("#141414", 3.2, alpha))
        c.drawString(ln, x, yy, f, fill("#141414", alpha))

def top_wash(c):
    p = skia.Paint(AntiAlias=True)
    p.setShader(skia.GradientShader.MakeLinear([skia.Point(0, 0), skia.Point(0, 400)],
                                               [hexcol("#f2efe8", 215), hexcol("#f2efe8", 120), hexcol("#f2efe8", 0)], [0, 0.6, 1]))
    c.drawRect(rect(0, 0, W, 400), p)

def watermark(c):
    f = hand(34)
    c.drawString("Facts on Facts", W - 40 - f.measureText("Facts on Facts"), H - 70, f, fill("#141414", 120))

# ------------------------------------------------------------------ frame
class SketchRenderer:
    def __init__(self, stage, tl):
        self.st, self.tl = stage, tl
        self.small = skia.Surface.MakeRaster(skia.ImageInfo.Make(SW, SH, skia.kBGRA_8888_ColorType, skia.kPremul_AlphaType))
        self.buf = np.empty((SH, SW, 4), np.uint8)
        self.pencil = Pencil()
        self.samp = skia.SamplingOptions(skia.FilterMode.kLinear)

    def draw_shot(self, c, k, t):
        sh = self.tl["shots"][k]
        sc_i = sh["scene"]; sc = self.st.story["scenes"][sc_i]
        s = self.tl["scenes"][sc_i]
        lt, dur = t - s["s"], s["e"] - s["s"]
        cam = framing_camera(self.st, sc, sh, lt, dur, sh["s"] - s["s"])
        self.st.draw_scene(c, sc_i, lt, dur, cam_override=cam, overlays=False)

    def frame(self, c_full, t, fi):
        shots = self.tl["shots"]
        k = 0
        for i, sh in enumerate(shots):
            if t >= sh["s"]:
                k = i
        # 1) draw the raw scene(s) small, with the slide between shots
        sc = self.small.getCanvas()
        sc.clear(hexcol("#000000"))
        sc.save(); sc.scale(SW / W, SH / H)
        nxt = k + 1 if k + 1 < len(shots) and t > shots[k + 1]["s"] - SLIDE / 2 else None
        prv = k - 1 if k > 0 and t < shots[k]["s"] + SLIDE / 2 else None
        pair = (k, nxt, shots[nxt]["s"]) if nxt is not None else ((prv, k, shots[k]["s"]) if prv is not None else None)
        q = 0.0
        if pair:
            a, b, B = pair
            q = ease_io((t - (B - SLIDE / 2)) / SLIDE)
            speed = math.sin(math.pi * clamp((t - (B - SLIDE / 2)) / SLIDE))
            bp = skia.Paint(); bp.setImageFilter(skia.ImageFilters.Blur(60 * speed + 0.01, 1.5 * speed + 0.01))
            sc.saveLayer(None, bp)
            sc.save(); sc.translate(-W * q, 0); sc.clipRect(rect(0, 0, W, H)); self.draw_shot(sc, a, t); sc.restore()
            sc.save(); sc.translate(W * (1 - q), 0); sc.clipRect(rect(0, 0, W, H)); self.draw_shot(sc, b, t); sc.restore()
            sc.restore()
        else:
            self.draw_shot(sc, k, t)
        sc.restore()
        # 2) pencil filter
        self.small.readPixels(self.small.imageInfo(), self.buf, SW * 4)
        rgba = self.pencil(self.buf, fi)
        img = skia.Image.fromarray(rgba, colorType=skia.kRGBA_8888_ColorType)
        c_full.clear(hexcol("#f2efe8"))
        c_full.drawImageRect(img, skia.Rect.MakeWH(W, H), skia.SamplingOptions(skia.CubicResampler.Mitchell()))
        # 3) hand-lettered titles (slide with their shots), light wash behind them, watermark
        top_wash(c_full)
        if pair:
            a, b, _ = pair
            draw_title(c_full, shots[a]["title"], -W * q)
            draw_title(c_full, shots[b]["title"], W * (1 - q))
        else:
            draw_title(c_full, shots[k]["title"])
        watermark(c_full)
        total = self.tl["total"]
        cta = self.st.story.get("cta", "FOLLOW FOR MORE TRUE STORIES")
        if cta and t > total - 3.2:
            a_ = ease_out((t - (total - 3.2)) / 0.5)
            f = hand(64)
            c_full.drawString(cta, W / 2 - f.measureText(cta) / 2, H - 230 + (1 - a_) * 30, f, fill("#141414", int(235 * a_)))
            c_full.drawLine(W / 2 - f.measureText(cta) / 2, H - 210, W / 2 - f.measureText(cta) / 2 + f.measureText(cta) * a_, H - 205,
                            stroke("#141414", 4, int(200 * a_)))
        if t > total - 0.8:
            c_full.drawRect(rect(0, 0, W, H), fill("#000000", int(255 * ease_io((t - (total - 0.8)) / 0.8))))
