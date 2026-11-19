"""2D vector animation engine (skia): characters, backgrounds, props, text. Everything is a pure
function of time t (seconds), drawn with float coordinates and anti-aliasing so motion is smooth."""
import math, os, hashlib
import skia

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1080, 1920
FONT_BIG = os.path.join(ROOT, "assets/fonts/Anton-Regular.ttf")
FONT_TYPE = os.path.join(ROOT, "assets/fonts/AnonymousPro-Bold.ttf")
_tf = {}

def typeface(path):
    if path not in _tf:
        _tf[path] = skia.Typeface.MakeFromFile(path)
    return _tf[path]

def font(path, size):
    return skia.Font(typeface(path), size)

# ------------------------------------------------------------------ utils
def hexcol(c, a=255):
    if isinstance(c, int):
        return c
    if isinstance(c, (tuple, list)):
        r, g, b = c[:3]
        a = c[3] if len(c) > 3 else a
        return skia.ColorSetARGB(int(a), int(r), int(g), int(b))
    c = c.lstrip("#")
    return skia.ColorSetARGB(int(a), int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))

def rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))

def shade(c, f):
    r, g, b = rgb(c) if isinstance(c, str) else c[:3]
    if f < 1:
        return (r * f, g * f, b * f)
    return (r + (255 - r) * (f - 1), g + (255 - g) * (f - 1), b + (255 - b) * (f - 1))

def fill(c, a=255, aa=True):
    return skia.Paint(Color=hexcol(c, a), AntiAlias=aa, Style=skia.Paint.kFill_Style)

def stroke(c, w, a=255):
    return skia.Paint(Color=hexcol(c, a), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=w,
                      StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=skia.Paint.kRound_Join)

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))

def ease_io(t):
    t = clamp(t)
    return 0.5 - 0.5 * math.cos(math.pi * t)

def ease_out(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3

def ease_back(t):
    t = clamp(t)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2

def lerp(a, b, t):
    return a + (b - a) * t

def h01(s):
    return int(hashlib.md5(str(s).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF

def text_w(txt, f):
    return f.measureText(txt)

def draw_text_c(c, txt, x, y, f, color, a=255, outline=0, ocolor="#000000"):
    w = text_w(txt, f)
    if outline:
        c.drawString(txt, x - w / 2, y, f, stroke(ocolor, outline, a))
    c.drawString(txt, x - w / 2, y, f, fill(color, a))

def fit(txt, path, maxw, size):
    while size > 20 and text_w(txt, font(path, size)) > maxw:
        size -= 3
    return font(path, size)

def rect(x, y, w, h):
    return skia.Rect.MakeXYWH(x, y, w, h)

def poly(pts):
    p = skia.Path()
    p.moveTo(*pts[0])
    for q in pts[1:]:
        p.lineTo(*q)
    p.close()
    return p

OUT = "#1a1512"  # outline colour

# ------------------------------------------------------------------ character rig
HAIR = {"black": "#1b1714", "brown": "#5a3a22", "blonde": "#d9b866", "red": "#a8492a", "grey": "#9a978f",
        "white": "#e8e4dc", "dark_brown": "#3a2618", "auburn": "#7d3420"}

def hair_col(v):
    return HAIR.get(v, v if isinstance(v, str) and v.startswith("#") else "#2a1d14")

class Character:
    """spec keys: skin, hair, hair_style, eyes, glasses(none|glasses|sunglasses), facial_hair(none|mustache|beard|stubble|goatee),
    outfit(suit|raincoat|uniform|stewardess|tshirt|dress|kid|robe|prison|coat|lab|armor), outfit_color, shirt_color, tie_color,
    pants_color, hat(none|fedora|cap|military|pillbox|helmet|crown|tophat|beret), hat_color, build(slim|average|heavy),
    height(0.8-1.1), age, gender(m|f), badge (text)."""

    def __init__(self, spec):
        self.s = dict(spec)
        s = self.s
        self.skin = s.get("skin", "#c99a76")
        self.hair = hair_col(s.get("hair", "black"))
        self.style = s.get("hair_style", "short")
        self.outfit = s.get("outfit", "suit")
        self.oc = s.get("outfit_color", "#2b2b30")
        self.shirt = s.get("shirt_color", "#f2efe8")
        self.tie = s.get("tie_color", "#111111")
        self.pants = s.get("pants_color", self.oc if self.outfit in ("suit", "uniform", "raincoat", "coat") else "#2d3a55")
        self.build = {"slim": 0.9, "average": 1.0, "heavy": 1.22}.get(s.get("build", "average"), 1.0)
        self.hscale = float(s.get("height", 1.0))
        self.female = s.get("gender", "m") == "f"
        self.seed = h01(s.get("name", "x"))

    # ---- parts
    def limb(self, c, x, y, a1, l1, a2, l2, w, col, end_col=None, end_r=0):
        """two-segment limb from (x,y); angles in degrees from straight down, positive = forward (+x)."""
        r1 = math.radians(a1)
        ex, ey = x + math.sin(r1) * l1, y + math.cos(r1) * l1
        r2 = math.radians(a1 + a2)
        hx, hy = ex + math.sin(r2) * l2, ey + math.cos(r2) * l2
        p = skia.Path()
        p.moveTo(x, y); p.lineTo(ex, ey); p.lineTo(hx, hy)
        c.drawPath(p, stroke(OUT, w + 7))
        c.drawPath(p, stroke(col, w))
        if end_r:
            c.drawCircle(hx, hy, end_r + 3.5, fill(OUT))
            c.drawCircle(hx, hy, end_r, fill(end_col or col))
        return hx, hy

    def draw(self, c, x, y, scale, t, action="stand", face=1, expr="neutral", props=None, talk=False, rot=0.0):
        """Feet at (x,y). Returns dict with hand positions in world coords."""
        s = self.s
        sc = scale * self.hscale
        c.save()
        c.translate(x, y)
        if rot:
            c.rotate(rot)
        c.scale(sc * face, sc)
        ph = t * 2 * math.pi
        breathe = math.sin(ph * 0.35 + self.seed * 6)
        bw = self.build
        # pose parameters
        legL = legR = 0.0; kneeL = kneeR = 0.0
        armL, elbL, armR, elbR = -8 + breathe * 1.5, 6, 8 - breathe * 1.5, -6
        lift = 0.0; lean = 0.0; seated = False
        if action == "walk":
            w = math.sin(ph * 1.6)
            legL, legR = 26 * w, -26 * w
            kneeL, kneeR = max(0, -30 * w), max(0, 30 * w)
            armL, armR = -22 * w, 22 * w
            elbL = elbR = 18
            lift = abs(math.cos(ph * 1.6)) * 10
        elif action == "run":
            w = math.sin(ph * 2.6)
            legL, legR = 40 * w, -40 * w
            kneeL, kneeR = max(0, -55 * w) + 10, max(0, 55 * w) + 10
            armL, armR = -40 * w, 40 * w
            elbL = elbR = 70
            lift = abs(math.cos(ph * 2.6)) * 22; lean = 8
        elif action == "sit":
            seated = True
            legL = legR = 85; kneeL = kneeR = -85
        elif action == "talk":
            armR, elbR = 35 + 12 * math.sin(ph * 0.9), 55 + 15 * math.sin(ph * 1.3)
        elif action == "point":
            armR, elbR = 95 + 4 * math.sin(ph * 0.5), 5
        elif action == "hold":  # holding something in front
            armR, elbR = 40, 60
            armL, elbL = 30, 70
        elif action == "give":  # hand forward (note)
            armR, elbR = 70 + 6 * math.sin(ph * 0.6), 10
        elif action == "carry":
            armR, elbR = 4, 0
        elif action == "shock":
            armL, elbL = -60, -70
            armR, elbR = 60 + 5 * math.sin(ph * 3), 70
            expr = "shock"
        elif action == "lean":
            lean = 12
            armR, elbR = 50, 40
        elif action == "fall":
            armL, elbL = -150 + 10 * math.sin(ph * 0.8), -20
            armR, elbR = 150 - 10 * math.sin(ph * 0.8), 20
            legL, legR = -18 + 6 * math.sin(ph), 18 - 6 * math.sin(ph)
            kneeL, kneeR = 15, -15
        elif action == "hang":  # under parachute
            armL, elbL = -165, 0
            armR, elbR = 165, 0
            legL, legR = -8 + 5 * math.sin(ph * 0.7), 8 + 5 * math.sin(ph * 0.7)
        elif action == "dig":
            d = math.sin(ph * 1.2)
            armR, elbR = 50 + 30 * d, 40
            armL, elbL = 40 + 30 * d, 50
            lean = 18 + 8 * d
        elif action == "salute":
            armR, elbR = 150, 100
        elif action == "fight":
            d = math.sin(ph * 2.2)
            armR, elbR = 80 + 25 * d, 30
            armL, elbL = 60 - 20 * d, 80
            legL, legR = -15, 20
        elif action == "kneel":
            legL, kneeL = 85, -85
            legR, kneeR = -5, 90
            lift = -90

        hip_y = -260 * (1 if not seated else 0.68) - lift + (90 if action == "kneel" else 0) * 0
        if action == "kneel":
            hip_y = -170
        sh_y = hip_y - 250 + breathe * 2
        torso_w = 150 * bw
        c.save()
        c.translate(0, hip_y)
        c.rotate(lean)
        c.translate(0, -hip_y)

        # ---- back hair (long styles)
        head_y = sh_y - 115
        if self.style in ("long", "bob", "afro", "ponytail"):
            self.back_hair(c, head_y, t)

        # ---- legs
        leg_len1, leg_len2 = 135, 130
        pant = self.pants
        skin_leg = self.outfit in ("stewardess", "dress", "kid")
        for lx, la, ka, back in ((-34 * bw, legL, kneeL, True), (34 * bw, legR, kneeR, False)):
            col = pant
            if skin_leg:
                col = self.skin
            self.limb(c, lx, hip_y, la, leg_len1, ka, leg_len2, 46 * bw, col)
            # shoe
            r1 = math.radians(la); r2 = math.radians(la + ka)
            fx = lx + math.sin(r1) * leg_len1 + math.sin(r2) * leg_len2
            fy = hip_y + math.cos(r1) * leg_len1 + math.cos(r2) * leg_len2
            shoe = skia.Rect.MakeXYWH(fx - 22, fy - 16, 62, 30)
            c.drawRoundRect(shoe, 14, 14, fill(OUT))
            c.drawRoundRect(skia.Rect.MakeXYWH(fx - 19, fy - 13, 56, 24), 11, 11, fill(s.get("shoe_color", "#14110f")))
        if self.outfit == "kid":  # shorts
            c.drawRoundRect(rect(-torso_w / 2 + 8, hip_y - 20, torso_w - 16, 90), 18, 18, fill(OUT))
            c.drawRoundRect(rect(-torso_w / 2 + 11, hip_y - 17, torso_w - 22, 84), 16, 16, fill(self.pants))

        # ---- back arm
        arm_w = 34 * bw
        sleeve = self.oc if self.outfit not in ("tshirt", "kid") else self.skin
        self.limb(c, -torso_w / 2 + 14, sh_y + 22, armL, 120, elbL, 112, arm_w, sleeve, self.skin, 19)

        # ---- torso
        self.torso(c, torso_w, sh_y, hip_y, t)

        # ---- neck + head
        c.drawRoundRect(rect(-21, sh_y - 42, 42, 54), 14, 14, fill(OUT))
        c.drawRoundRect(rect(-18, sh_y - 40, 36, 52), 12, 12, fill(shade(self.skin, 0.88)))
        if self.outfit in ("suit", "raincoat", "coat"):
            self.collar(c, sh_y)
        tilt = 2.5 * math.sin(ph * 0.23 + self.seed * 4)
        c.save()
        c.translate(0, head_y)
        c.rotate(tilt)
        self.head(c, t, expr, talk)
        c.restore()

        # ---- front arm (+ held prop)
        hand = self.limb(c, torso_w / 2 - 14, sh_y + 22, armR, 120, elbR, 112, arm_w, sleeve, self.skin, 19)
        c.restore()
        c.restore()
        return {"hand": hand}

    def collar(self, c, sh_y):
        c.drawPath(poly([(-30, sh_y - 8), (0, sh_y + 30), (30, sh_y - 8), (22, sh_y - 22), (0, sh_y + 6), (-22, sh_y - 22)]), fill(self.shirt))

    def torso(self, c, tw, sh_y, hip_y, t):
        o = self.outfit
        bottom = hip_y + 20
        if o in ("raincoat", "coat", "robe", "dress", "lab"):
            bottom = hip_y + (230 if o in ("raincoat", "lab", "coat") else 300 if o == "robe" else 150)
        if o == "stewardess":
            bottom = hip_y + 110
        wb = tw * (1.18 if o in ("raincoat", "robe", "dress", "coat", "lab") else 1.0)
        p = skia.Path()
        p.moveTo(-tw / 2, sh_y + 10)
        p.quadTo(-tw / 2 - 4, sh_y - 14, -tw / 2 + 24, sh_y - 18)
        p.lineTo(tw / 2 - 24, sh_y - 18)
        p.quadTo(tw / 2 + 4, sh_y - 14, tw / 2, sh_y + 10)
        p.lineTo(wb / 2, bottom)
        p.lineTo(-wb / 2, bottom)
        p.close()
        c.drawPath(p, stroke(OUT, 7))
        body = self.oc
        if o in ("tshirt", "kid"):
            body = self.shirt
        c.drawPath(p, fill(body))
        # shading
        c.save(); c.clipPath(p, doAntiAlias=True)
        c.drawRect(rect(tw * 0.18, sh_y - 30, tw, bottom - sh_y + 40), fill("#000000", 40))
        c.restore()
        if o in ("suit", "raincoat", "coat"):
            # shirt V + tie + lapels
            c.drawPath(poly([(-28, sh_y - 16), (28, sh_y - 16), (0, sh_y + 120)]), fill(self.shirt))
            if self.s.get("tie_color", "#111111") != "none":
                c.drawPath(poly([(-9, sh_y - 8), (9, sh_y - 8), (6, sh_y + 6), (14, sh_y + 110), (0, sh_y + 128), (-14, sh_y + 110), (-6, sh_y + 6)]), fill(self.tie))
            lap = shade(body, 0.8)
            c.drawPath(poly([(-30, sh_y - 18), (-6, sh_y + 128), (-44, sh_y + 60)]), fill(lap))
            c.drawPath(poly([(30, sh_y - 18), (6, sh_y + 128), (44, sh_y + 60)]), fill(lap))
            for by in (sh_y + 150, sh_y + 200):
                c.drawCircle(4, by, 5, fill("#0d0b0a"))
            if o == "raincoat":
                c.drawRect(rect(-wb / 2 + 6, hip_y - 20, wb - 12, 18), fill(shade(body, 0.75)))
        elif o == "uniform":
            c.drawLine(0, sh_y - 16, 0, bottom, stroke(shade(body, 0.7), 4))
            for by in range(int(sh_y + 20), int(bottom - 20), 45):
                c.drawCircle(0, by, 6, fill("#d4af37"))
            c.drawRect(rect(-tw / 2 + 4, hip_y - 26, tw - 8, 22), fill("#3b2a1a"))
            c.drawRect(rect(-14, hip_y - 28, 28, 26), fill("#d4af37"))
            for px in (-tw / 4, tw / 4):
                c.drawRect(rect(px - 22, sh_y + 30, 44, 36), stroke(shade(body, 0.7), 3))
            if self.s.get("medals"):
                for i in range(3):
                    c.drawRect(rect(-tw / 4 - 22 + i * 15, sh_y + 8, 12, 18), fill(["#c0392b", "#2e86c1", "#d4af37"][i]))
        elif o == "stewardess":
            c.drawPath(poly([(-22, sh_y - 16), (22, sh_y - 16), (0, sh_y + 60)]), fill(self.shirt))
            c.drawPath(poly([(-16, sh_y + 4), (16, sh_y + 4), (30, sh_y + 40), (0, sh_y + 30), (-30, sh_y + 40)]), fill(self.s.get("scarf_color", "#c0392b")))
            for by in (sh_y + 110, sh_y + 160):
                c.drawCircle(0, by, 5, fill("#d4af37"))
        elif o == "tshirt" or o == "kid":
            c.drawPath(poly([(-24, sh_y - 18), (24, sh_y - 18), (0, sh_y + 6)]), fill(shade(body, 0.7)))
            if self.s.get("stripe"):
                c.drawRect(rect(-tw / 2 + 4, sh_y + 70, tw - 8, 22), fill(self.s["stripe"]))
        elif o == "prison":
            c.drawPath(poly([(-24, sh_y - 18), (24, sh_y - 18), (0, sh_y + 30)]), fill(shade(body, 0.7)))
        elif o == "armor":
            for i in range(4):
                c.drawLine(-tw / 2 + 10, sh_y + 40 + i * 50, tw / 2 - 10, sh_y + 40 + i * 50, stroke(shade(body, 0.7), 4))
        elif o == "robe":
            c.drawLine(-10, sh_y - 16, 30, bottom, stroke(shade(body, 0.7), 5))
            c.drawRect(rect(-wb / 2 + 10, hip_y - 30, wb - 20, 20), fill(self.s.get("sash_color", "#d4af37")))
        if self.s.get("badge"):
            c.drawCircle(-tw / 4, sh_y + 60, 14, fill("#d4af37"))

    def back_hair(self, c, head_y, t):
        hc = self.hair
        sway = 3 * math.sin(t * 1.3 + self.seed * 5)
        if self.style == "long":
            p = skia.Path()
            p.moveTo(-68, head_y - 30); p.quadTo(-86 + sway, head_y + 90, -70 + sway, head_y + 175)
            p.lineTo(70 + sway, head_y + 175); p.quadTo(86 + sway, head_y + 90, 68, head_y - 30); p.close()
            c.drawPath(p, stroke(OUT, 7)); c.drawPath(p, fill(hc))
        elif self.style == "bob":
            c.drawRoundRect(rect(-80, head_y - 60, 160, 145), 60, 60, fill(OUT))
            c.drawRoundRect(rect(-77, head_y - 57, 154, 139), 58, 58, fill(hc))
        elif self.style == "afro":
            c.drawCircle(0, head_y - 30, 112, fill(OUT)); c.drawCircle(0, head_y - 30, 108, fill(hc))
        elif self.style == "ponytail":
            p = skia.Path(); p.moveTo(-40, head_y - 40)
            p.quadTo(-110 + sway, head_y + 40, -70 + sway, head_y + 140)
            p.quadTo(-50, head_y + 40, -20, head_y - 30); p.close()
            c.drawPath(p, stroke(OUT, 6)); c.drawPath(p, fill(hc))

    def head(self, c, t, expr, talk):
        s = self.s
        sk = self.skin
        fx = 10  # 3/4 view: features shift forward
        # ears
        for ex in (-64, 64):
            c.drawOval(rect(ex - 13, -10, 26, 36), fill(OUT)); c.drawOval(rect(ex - 10, -7, 20, 30), fill(shade(sk, 0.9)))
        # head shape
        jaw = 1.0 if not self.female else 0.94
        hp = skia.Path()
        hp.addOval(rect(-66, -88, 132, 168 * jaw))
        c.drawPath(hp, stroke(OUT, 7))
        c.drawPath(hp, fill(sk))
        c.save(); c.clipPath(hp, doAntiAlias=True)
        c.drawOval(rect(-110, -40, 90, 160), fill("#000000", 28))  # cheek shadow on back side
        c.restore()
        age = s.get("age", 35)
        # facial hair (under features)
        fh = s.get("facial_hair", "none")
        hc = self.hair if s.get("beard_color") is None else hair_col(s.get("beard_color"))
        if fh in ("beard", "full_beard"):
            p = skia.Path(); p.moveTo(-62, 0); p.quadTo(-60, 95, fx, 92); p.quadTo(62, 95, 62, 0)
            p.lineTo(46, 20); p.quadTo(fx, 40, -46, 20); p.close()
            c.drawPath(p, fill(hc))
        elif fh == "stubble":
            p = skia.Path(); p.moveTo(-58, 15); p.quadTo(-50, 88, fx, 84); p.quadTo(56, 88, 58, 15)
            p.quadTo(fx, 50, -58, 15); p.close()
            c.drawPath(p, fill(hc, 70))
        elif fh == "goatee":
            c.drawOval(rect(fx - 20, 52, 40, 32), fill(hc))
        # eyes
        blink_p = 3.7 + self.seed * 1.5
        bt = (t + self.seed * 3) % blink_p
        open_ = 1.0 - (math.sin(clamp((bt - (blink_p - 0.22)) / 0.22) * math.pi))
        if expr == "shock":
            open_ = max(open_, 0.0) * 1.3
        look = 3 * math.sin(t * 0.4 + self.seed * 7)
        for ex in (-24 + fx, 24 + fx):
            eh = 15 * clamp(open_, 0.08, 1.4)
            c.drawOval(rect(ex - 12, -14 - eh / 2 + 2, 24, eh + 2), fill("#fbf8f2"))
            if open_ > 0.25:
                c.drawCircle(ex + 3 + look, -12, 6.5, fill(s.get("eyes", "#3b2414")))
                c.drawCircle(ex + 1 + look, -14, 2, fill("#ffffff"))
        # brows
        bc = shade(self.hair, 0.8) if s.get("hair") not in ("grey", "white") else (130, 125, 118)
        brow_tilt = {"angry": 9, "sad": -7, "shock": -4}.get(expr, 0)
        bl = -40 if expr != "shock" else -46
        c.drawLine(-36 + fx, bl + brow_tilt * -0.5, -12 + fx, bl + brow_tilt * 0.6, stroke(bc, 6))
        c.drawLine(12 + fx, bl + brow_tilt * 0.6, 36 + fx, bl + brow_tilt * -0.5, stroke(bc, 6))
        # glasses
        g = s.get("glasses", "none")
        if g in ("sunglasses", "glasses"):
            gp = fill("#111111") if g == "sunglasses" else stroke("#222222", 4)
            for ex in (-24 + fx, 24 + fx):
                c.drawRoundRect(rect(ex - 19, -27, 38, 28), 9, 9, gp)
            c.drawLine(-5 + fx, -16, 5 + fx, -16, stroke("#111111", 4))
            c.drawLine(-43 + fx, -18, -62, -14, stroke("#111111", 4))
            if g == "sunglasses":
                for ex in (-24 + fx, 24 + fx):
                    c.drawLine(ex - 10, -22, ex - 2, -24, stroke("#ffffff", 3, 90))
        # nose
        np_ = skia.Path(); np_.moveTo(fx + 4, -6); np_.quadTo(fx + 16, 22, fx + 2, 26)
        c.drawPath(np_, stroke(shade(sk, 0.7), 4))
        # mustache
        if fh in ("mustache", "beard", "full_beard"):
            mp = skia.Path(); mp.moveTo(fx - 30, 44); mp.quadTo(fx, 26, fx + 30, 44); mp.quadTo(fx, 38, fx - 30, 44)
            c.drawPath(mp, stroke(hc, 9))
        # mouth
        if talk:
            o = 4 + 9 * abs(math.sin(t * 9.0)) * abs(math.sin(t * 3.1))
            c.drawOval(rect(fx - 13, 50 - o / 2, 26, o + 4), fill("#5a2020"))
        elif expr in ("smile", "happy"):
            mp = skia.Path(); mp.moveTo(fx - 20, 48); mp.quadTo(fx, 66, fx + 20, 48)
            c.drawPath(mp, stroke("#6a2a24", 5))
        elif expr in ("sad", "angry", "serious"):
            mp = skia.Path(); mp.moveTo(fx - 18, 58); mp.quadTo(fx, 48, fx + 18, 58)
            c.drawPath(mp, stroke("#6a2a24", 5))
        elif expr == "shock":
            c.drawOval(rect(fx - 10, 44, 20, 24), fill("#5a2020"))
        else:
            c.drawLine(fx - 16, 54, fx + 16, 52, stroke("#6a2a24", 5))
        if age >= 50:
            for i in range(2):
                c.drawLine(-26 + fx, -58 + i * 9, 26 + fx, -58 + i * 9, stroke(shade(sk, 0.78), 2.5))
            c.drawLine(fx + 34, 30, fx + 40, 50, stroke(shade(sk, 0.78), 2.5))
        # front hair + hat
        self.front_hair(c, t)
        self.hat(c)

    def front_hair(self, c, t):
        st = self.style
        hc = self.hair
        if st in ("bald", "none"):
            return
        p = skia.Path()
        if st == "side_part":
            p.moveTo(-68, 4); p.quadTo(-78, -92, -6, -100); p.quadTo(70, -102, 70, 0)
            p.quadTo(62, -46, 30, -60); p.quadTo(-10, -66, -26, -54); p.quadTo(-52, -40, -58, 6); p.close()
        elif st == "receding":
            p.moveTo(-68, 10); p.quadTo(-72, -60, -40, -78); p.lineTo(-30, -58); p.quadTo(-56, -30, -58, 10); p.close()
            q = skia.Path(); q.moveTo(68, 10); q.quadTo(72, -60, 40, -78); q.lineTo(30, -58); q.quadTo(56, -30, 58, 10); q.close()
            c.drawPath(q, stroke(OUT, 5)); c.drawPath(q, fill(hc))
        elif st in ("short", "buzz"):
            p.moveTo(-68, -4); p.quadTo(-72, -100, 0, -98); p.quadTo(72, -100, 68, -4)
            p.quadTo(58, -56, 0, -60); p.quadTo(-58, -56, -68, -4); p.close()
        elif st == "pompadour":
            p.moveTo(-68, -4); p.quadTo(-80, -120, 10, -126); p.quadTo(84, -118, 68, -4)
            p.quadTo(60, -58, 0, -64); p.quadTo(-58, -56, -68, -4); p.close()
        elif st in ("long", "bob", "ponytail"):
            p.moveTo(-70, 20); p.quadTo(-80, -100, 4, -100); p.quadTo(78, -98, 70, 20)
            p.quadTo(60, -50, 20, -62); p.quadTo(-20, -40, -56, -40); p.quadTo(-64, -10, -70, 20); p.close()
        elif st == "bun":
            c.drawCircle(-10, -106, 30, fill(OUT)); c.drawCircle(-10, -106, 27, fill(hc))
            p.moveTo(-68, -4); p.quadTo(-72, -100, 0, -98); p.quadTo(72, -100, 68, -4)
            p.quadTo(58, -60, 0, -66); p.quadTo(-58, -60, -68, -4); p.close()
        elif st == "curly":
            for i in range(9):
                a = math.pi + i * math.pi / 8
                c.drawCircle(math.cos(a) * 62, -18 + math.sin(a) * 76, 22, fill(hc))
            return
        elif st == "afro":
            return
        elif st == "kid_messy":
            p.moveTo(-68, -4)
            for i in range(7):
                xx = -68 + i * 22
                p.lineTo(xx + 11, -112 + (i % 2) * 18 + 3 * math.sin(t * 2 + i))
                p.lineTo(xx + 22, -88)
            p.lineTo(68, -4); p.quadTo(58, -60, 0, -64); p.quadTo(-58, -60, -68, -4); p.close()
        else:
            p.moveTo(-68, -4); p.quadTo(-72, -100, 0, -98); p.quadTo(72, -100, 68, -4)
            p.quadTo(58, -56, 0, -60); p.quadTo(-58, -56, -68, -4); p.close()
        c.drawPath(p, stroke(OUT, 6))
        c.drawPath(p, fill(hc))
        c.drawPath(p, stroke(shade(hc, 1.35), 2, 120))

    def hat(self, c):
        hat = self.s.get("hat", "none")
        hc = self.s.get("hat_color", "#2a2622")
        if hat == "fedora":
            c.drawRoundRect(rect(-100, -82, 200, 22), 11, 11, fill(OUT)); c.drawRoundRect(rect(-96, -79, 192, 16), 8, 8, fill(hc))
            p = skia.Path(); p.moveTo(-60, -72); p.quadTo(-64, -150, 0, -146); p.quadTo(64, -150, 60, -72); p.close()
            c.drawPath(p, stroke(OUT, 6)); c.drawPath(p, fill(hc))
            c.drawRect(rect(-60, -92, 120, 14), fill("#111111"))
        elif hat == "cap":
            p = skia.Path(); p.moveTo(-68, -40); p.quadTo(-66, -120, 0, -118); p.quadTo(66, -120, 68, -40); p.close()
            c.drawPath(p, stroke(OUT, 6)); c.drawPath(p, fill(hc))
            c.drawRoundRect(rect(20, -50, 90, 18), 9, 9, fill(shade(hc, 0.8)))
        elif hat == "military":
            c.drawRoundRect(rect(-74, -100, 148, 50), 16, 16, fill(OUT)); c.drawRoundRect(rect(-70, -97, 140, 44), 14, 14, fill(hc))
            c.drawRoundRect(rect(-40, -58, 130, 16), 8, 8, fill("#111111"))
            c.drawCircle(0, -78, 10, fill("#d4af37"))
        elif hat == "helmet":
            p = skia.Path(); p.moveTo(-84, -30); p.quadTo(-84, -130, 0, -128); p.quadTo(84, -130, 84, -30); p.close()
            c.drawPath(p, stroke(OUT, 6)); c.drawPath(p, fill(hc))
        elif hat == "pillbox":
            c.drawRoundRect(rect(-36, -118, 72, 34), 10, 10, fill(OUT)); c.drawRoundRect(rect(-33, -115, 66, 28), 8, 8, fill(hc))
        elif hat == "crown":
            c.drawPath(poly([(-56, -78), (-56, -138), (-30, -104), (0, -146), (30, -104), (56, -138), (56, -78)]), fill("#e3b42a"))
            for xx in (-28, 0, 28):
                c.drawCircle(xx, -90, 6, fill("#c0392b"))
        elif hat == "tophat":
            c.drawRoundRect(rect(-92, -84, 184, 18), 9, 9, fill("#111111"))
            c.drawRect(rect(-56, -190, 112, 110), fill("#111111"))
        elif hat == "beret":
            c.drawOval(rect(-80, -122, 150, 60), fill(hc))

# ------------------------------------------------------------------ props
def prop(c, kind, x, y, s, t, opts=None):
    o = opts or {}
    c.save(); c.translate(x, y); c.scale(s, s)
    if kind == "briefcase":
        open_ = o.get("open", False)
        c.drawRoundRect(rect(-80, -55, 160, 110), 12, 12, fill(OUT))
        c.drawRoundRect(rect(-76, -51, 152, 102), 10, 10, fill("#3d2b1f"))
        c.drawRoundRect(rect(-24, -72, 48, 24), 8, 8, stroke("#3d2b1f", 8))
        if open_:
            c.drawRoundRect(rect(-76, -150, 152, 100), 10, 10, fill("#2b1d14"))
            for i in range(6):
                c.drawRoundRect(rect(-66 + i * 22, -42, 16, 70), 6, 6, fill("#b8322a"))
            c.drawRect(rect(-60, 26, 120, 18), fill("#444444"))
            p = skia.Path(); p.moveTo(-60, -20)
            for i in range(6):
                p.quadTo(-50 + i * 22, -50 + 10 * math.sin(t * 2 + i), -40 + i * 22, -20)
            c.drawPath(p, stroke("#e74c3c", 3))
    elif kind == "note":
        c.rotate(-6 + 2 * math.sin(t * 1.2))
        c.drawRect(rect(-70, -45, 140, 90), fill("#f3ead6"))
        c.drawRect(rect(-70, -45, 140, 90), stroke("#a89a7c", 2))
        for i in range(3):
            c.drawLine(-55, -20 + i * 22, 50 - i * 12, -20 + i * 22, stroke("#333333", 3))
    elif kind == "money":
        for i in range(int(o.get("stacks", 3))):
            yy = -i * 26
            c.drawRoundRect(rect(-90, yy - 22, 180, 44), 6, 6, fill("#3d5a32"))
            c.drawRoundRect(rect(-86, yy - 18, 172, 36), 5, 5, fill("#7c9c5e"))
            c.drawRect(rect(-14, yy - 18, 28, 36), fill("#d8c98a"))
    elif kind == "moneybag":
        p = skia.Path(); p.moveTo(-30, -70); p.quadTo(-95, 0, -70, 60); p.lineTo(70, 60); p.quadTo(95, 0, 30, -70); p.close()
        c.drawPath(p, stroke(OUT, 6)); c.drawPath(p, fill("#c8a970"))
        c.drawRect(rect(-30, -84, 60, 18), fill("#8a6b3a"))
        draw_text_c(c, "$", 0, 40, font(FONT_BIG, 80), "#4d3a1a")
    elif kind == "parachute":
        r = 260
        canopy = skia.Path(); canopy.addArc(rect(-r, -r * 0.7, 2 * r, r * 1.4), 180, 180); canopy.close()
        c.drawPath(canopy, stroke(OUT, 8))
        c.drawPath(canopy, fill(o.get("color", "#e8e2d4")))
        for i in range(6):
            xx = -r + i * r / 3
            c.drawLine(xx + r / 6, 0, xx + r / 6, -r * 0.55 * math.sin(math.acos(clamp(abs(xx + r / 6) / r))), stroke("#bdb4a0", 4))
        for xx in (-r * 0.95, -r * 0.45, r * 0.45, r * 0.95):
            c.drawLine(xx, 0, 0, r * 1.15, stroke("#cfc7b4", 3))
    elif kind == "shovel":
        c.rotate(o.get("angle", 0))
        c.drawLine(0, -150, 0, 60, stroke("#7a5230", 12))
        c.drawPath(poly([(-30, 60), (30, 60), (24, 120), (0, 135), (-24, 120)]), fill("#8f9496"))
    elif kind == "newspaper":
        c.rotate(o.get("angle", -4))
        c.drawRect(rect(-300, -360, 600, 720), fill("#efe9db"))
        f = fit(o.get("headline", "HEADLINE"), FONT_BIG, 540, 110)
        lines = o.get("headline", "HEADLINE").split("|")
        yy = -200
        draw_text_c(c, o.get("paper", "THE DAILY TIMES"), 0, -300, font(FONT_TYPE, 40), "#222222")
        c.drawLine(-270, -280, 270, -280, stroke("#222222", 3))
        for ln in lines:
            ff = fit(ln, FONT_BIG, 540, 110)
            draw_text_c(c, ln, 0, yy, ff, "#111111")
            yy += 115
        for i in range(8):
            c.drawLine(-270, yy + 20 + i * 30, 270 - (i % 3) * 60, yy + 20 + i * 30, stroke("#9a948a", 6))
    elif kind == "poster":  # wanted poster with a character head
        c.drawRect(rect(-230, -320, 460, 640), fill("#e6d6b0"))
        c.drawRect(rect(-230, -320, 460, 640), stroke("#8a7650", 6))
        draw_text_c(c, o.get("title", "WANTED"), 0, -230, font(FONT_BIG, 110), "#2a1d14")
        ch = o.get("char")
        if ch:
            c.save(); c.translate(0, 0); c.scale(1.35, 1.35)
            ch.head(c, t, "serious", False)
            c.restore()
        draw_text_c(c, o.get("sub", ""), 0, 270, font(FONT_TYPE, 40), "#2a1d14")
    elif kind == "plane_side":
        plane_side(c, t, o)
    elif kind == "bills":  # fluttering bills
        for i in range(int(o.get("n", 10))):
            ph = t * 0.9 + i * 1.7
            bx = math.sin(ph * 0.7 + i) * 180 + (h01(i) - 0.5) * 300
            by = ((t * 90 + i * 140) % 700) - 350
            c.save(); c.translate(bx, by); c.rotate(math.sin(ph) * 60)
            c.scale(1, abs(math.cos(ph * 1.3)) * 0.8 + 0.2)
            c.drawRect(rect(-40, -18, 80, 36), fill("#7c9c5e")); c.drawRect(rect(-10, -18, 20, 36), fill("#d8c98a"))
            c.restore()
    elif kind == "stamp":
        f = fit(o.get("text", "UNSOLVED"), FONT_BIG, 600, 170)
        c.rotate(-12)
        w = text_w(o.get("text", "UNSOLVED"), f) + 80
        c.drawRoundRect(rect(-w / 2, -110, w, 170), 20, 20, stroke("#c0392b", 14))
        draw_text_c(c, o.get("text", "UNSOLVED"), 0, 30, f, "#c0392b")
    elif kind == "file":
        c.drawRoundRect(rect(-260, -320, 520, 640), 16, 16, fill("#a07a4a"))
        c.drawRoundRect(rect(-260, -360, 200, 60), 12, 12, fill("#a07a4a"))
        c.drawRect(rect(-230, -290, 460, 580), fill("#efe6d0"))
        draw_text_c(c, o.get("title", "CASE FILE"), 0, -220, font(FONT_TYPE, 46), "#222222")
        for i in range(9):
            c.drawRect(rect(-200, -170 + i * 50, 400 - (i % 3) * 80, 14), fill("#c9bfa8"))
    elif kind == "gun":
        c.drawRoundRect(rect(-90, -20, 150, 30), 6, 6, fill("#2b2b2b"))
        c.drawPath(poly([(20, 0), (60, 0), (80, 80), (45, 85)]), fill("#3d2b1f"))
    elif kind == "sword":
        c.rotate(o.get("angle", 0))
        c.drawPath(poly([(-6, -200), (0, -220), (6, -200), (6, 0), (-6, 0)]), fill("#cfd4d6"))
        c.drawRect(rect(-40, 0, 80, 12), fill("#d4af37")); c.drawRect(rect(-7, 12, 14, 60), fill("#5a3a22"))
    elif kind == "fire":
        for i in range(5):
            ph = t * 3 + i
            hh = 120 + 40 * math.sin(ph)
            xx = (i - 2) * 40
            p = skia.Path(); p.moveTo(xx - 30, 0); p.quadTo(xx - 20, -hh * 0.6, xx + 8 * math.sin(ph * 1.3), -hh)
            p.quadTo(xx + 20, -hh * 0.6, xx + 30, 0); p.close()
            c.drawPath(p, fill("#e67e22" if i % 2 else "#f1c40f", 220))
    elif kind == "phone_booth":
        c.drawRect(rect(-80, -400, 160, 400), fill("#b03a2e"))
        c.drawRect(rect(-60, -360, 120, 300), fill("#9fc3d9", 120))
    c.restore()

def plane_side(c, t, o):
    """Boeing 727-style jet, side view, nose to the right. Unit ~ 900px long."""
    body = o.get("body", "#e9e6df")
    tail = o.get("tail", "#c0392b")
    # wing (far)
    c.drawPath(poly([(-40, 10), (150, 10), (40, 90), (-90, 90)]), fill(shade(body, 0.7)))
    # fuselage
    fus = skia.Path(); fus.addRoundRect(rect(-430, -60, 860, 120), 60, 60)
    c.drawPath(fus, stroke(OUT, 8)); c.drawPath(fus, fill(body))
    nose = skia.Path(); nose.moveTo(380, -60); nose.quadTo(470, -50, 470, 10); nose.quadTo(460, 55, 380, 60); nose.close()
    c.drawPath(nose, fill(body))
    c.drawPath(poly([(400, -38), (440, -34), (452, -14), (404, -14)]), fill("#2b3a4a"))
    # stripe + windows
    c.drawRect(rect(-410, -6, 820, 14), fill(o.get("stripe", "#2c3e50")))
    lit = o.get("windows_lit", True)
    for i in range(20):
        xx = -340 + i * 36
        c.drawRoundRect(rect(xx, -32, 16, 20), 6, 6, fill("#ffd77a" if lit else "#33404d"))
    # T-tail + 3 rear engines
    c.drawPath(poly([(-430, -50), (-330, -60), (-380, -250), (-450, -250)]), fill(tail))
    c.drawRect(rect(-480, -262, 150, 22), fill(tail))
    c.drawRoundRect(rect(-420, -110, 150, 50), 25, 25, fill(shade(body, 0.85)))
    c.drawRoundRect(rect(-420, -110, 150, 50), 25, 25, stroke(OUT, 5))
    c.drawPath(poly([(-380, -60), (-350, -60), (-360, -90), (-375, -90)]), fill(shade(body, 0.8)))
    # near wing
    c.drawPath(poly([(-20, 20), (130, 20), (-40, 150), (-130, 150)]), fill(shade(body, 0.88)))
    c.drawPath(poly([(-20, 20), (130, 20), (-40, 150), (-130, 150)]), stroke(OUT, 5))
    c.drawRoundRect(rect(-60, 40, 110, 40), 20, 20, fill(shade(body, 0.6)))
    # aft airstair (727 ventral stairs) – open amount 0..1
    st = o.get("stairs", 0.0)
    if st > 0:
        c.save(); c.translate(-400, 55); c.rotate(st * 38)
        c.drawRect(rect(0, 0, 150, 18), fill("#8a8d90"))
        for i in range(6):
            c.drawLine(10 + i * 24, 0, 10 + i * 24, 18, stroke("#5a5d60", 3))
        c.restore()
    # blinking light (smooth)
    blink = (math.sin(t * 5) + 1) / 2
    c.drawCircle(-470, -255, 9, fill("#ff4040", int(80 + 175 * blink)))

# ------------------------------------------------------------------ backgrounds (each fills the full canvas)
def _cloud(c, x, y, s, col, a):
    p = fill(col, a)
    for dx, dy, r in ((0, 0, 70), (60, -20, 80), (130, 0, 65), (60, 25, 70), (-50, 15, 50), (180, 20, 45)):
        c.drawCircle(x + dx * s, y + dy * s, r * s, p)

def _rain(c, t, n=110, a=90, speed=1700, ang=12):
    pnt = stroke("#a9c1d9", 3, a)
    dx = math.tan(math.radians(ang))
    for i in range(n):
        x0 = h01(i * 3.1) * (W + 300) - 150
        ph = (h01(i * 7.7) * 2000 + t * speed) % (H + 200) - 100
        x = x0 - ph * dx
        c.drawLine(x, ph, x - 60 * dx, ph + 60, pnt)

def _stars(c, t, n=90):
    for i in range(n):
        x, y = h01(i) * W, h01(i + 999) * H * 0.55
        a = 90 + 120 * (0.5 + 0.5 * math.sin(t * (0.8 + h01(i + 5)) + i))
        c.drawCircle(x, y, 1.5 + 2 * h01(i + 7), fill("#ffffff", int(a)))

def _sky(c, top, bot, horizon=H):
    p = skia.Paint(AntiAlias=True)
    p.setShader(skia.GradientShader.MakeLinear([skia.Point(0, 0), skia.Point(0, horizon)], [hexcol(top), hexcol(bot)]))
    c.drawRect(rect(0, 0, W, H), p)

def _lightning(c, t, times):
    for lt in times:
        d = t - lt
        if 0 <= d < 0.6:
            a = int(95 * clamp(d / 0.06) * math.exp(-max(0.0, d - 0.06) * 5))
            c.drawRect(rect(0, 0, W, H), fill("#dfe8ff", clamp(a, 0, 255)))

def bg_sky_night(c, t, cam, o):
    _sky(c, "#070b1a", "#2a2546")
    _stars(c, t)
    c.drawCircle(820 - cam * 0.05, 330, 70, fill("#f2edd8", 230))
    c.drawCircle(800 - cam * 0.05, 315, 70, fill("#070b1a", 0))
    for layer, (sp, yb, sc, a) in enumerate(((25, 520, 1.6, 120), (55, 900, 2.2, 150), (110, 1500, 2.8, 170))):
        for i in range(4):
            x = ((i * 520 + h01(i + layer * 9) * 300 - t * sp - cam * (0.2 + layer * 0.3)) % (W + 900)) - 450
            _cloud(c, x, yb + 140 * math.sin(i * 2.1 + layer), sc, "#3a3a5c" if layer < 2 else "#22223a", a)
    if o.get("rain", True):
        _rain(c, t)
    _lightning(c, t, o.get("lightning", []))

def bg_forest_night(c, t, cam, o):
    bg_sky_night(c, t, cam, dict(o, rain=False))
    for layer, (col, base, hgt, sp) in enumerate((("#141a2a", 1250, 380, 0.15), ("#0e1420", 1450, 470, 0.35), ("#080c14", 1700, 560, 0.7))):
        for i in range(10):
            x = ((i * 150 + h01(i + layer * 13) * 90 - cam * sp - t * 4 * (layer + 1)) % (W + 300)) - 150
            hh = hgt * (0.7 + 0.5 * h01(i * 3 + layer))
            sway = 4 * math.sin(t * 0.9 + i)
            c.drawPath(poly([(x - 70, base + 10), (x + sway, base - hh), (x + 70, base + 10)]), fill(col))
        c.drawRect(rect(0, base, W, H - base), fill(col))
    for i in range(5):  # mist
        x = ((i * 400 - t * 30) % (W + 800)) - 400
        c.drawOval(rect(x, 1300 + i * 70, 700, 120), fill("#8890a8", 22))
    _rain(c, t)
    _lightning(c, t, o.get("lightning", []))

def bg_airport(c, t, cam, o):
    c.drawRect(rect(0, 0, W, H), fill("#d8c7a4"))
    # big window with dusk sky and a parked jet
    c.save(); c.clipRect(rect(60, 260, W - 120, 640))
    _sky(c, "#4a5a7c", "#e3a76a", 900)
    c.save(); c.translate(560 - cam * 0.15, 760); c.scale(0.55, 0.55); plane_side(c, t, {"windows_lit": False}); c.restore()
    c.drawRect(rect(0, 820, W, 120), fill("#5b5b5b"))
    c.restore()
    for x in range(60, W - 60, 190):
        c.drawRect(rect(x - 6, 260, 12, 640), fill("#6b5640"))
    c.drawRect(rect(50, 250, W - 100, 20), fill("#6b5640")); c.drawRect(rect(50, 890, W - 100, 20), fill("#6b5640"))
    # departures board
    c.drawRoundRect(rect(120, 960, 840, 200), 10, 10, fill("#1b1b1b"))
    rows = o.get("board", ["FLIGHT 305  SEATTLE  2:50"])
    for i, r in enumerate(rows[:3]):
        flip = clamp((t - 0.3 - i * 0.25) / 0.5)
        f = font(FONT_TYPE, 44)
        sh = min(len(r), int(flip * len(r) + 0.999))
        c.drawString(r[:sh], 150, 1020 + i * 56, f, fill("#f5c542"))
    # floor
    c.drawRect(rect(0, 1180, W, H - 1180), fill("#9b8a6c"))
    for i in range(-12, 14):
        x0 = W / 2 + i * 90 - cam * 0.6
        c.drawLine(W / 2 + (x0 - W / 2) * 0.35, 1180, x0 + (x0 - W / 2) * 1.8, H, stroke("#8a7a5e", 3))
    for i in range(6):
        y = 1180 + (i ** 1.8) * 30
        c.drawLine(0, y, W, y, stroke("#8a7a5e", 3))
    # counter
    if o.get("counter", True):
        c.drawRect(rect(-cam * 0.6 + 600, 1180, 480, 220), fill("#7a1f1f"))
        draw_text_c(c, o.get("sign", "NORTHWEST ORIENT"), -cam * 0.6 + 840, 1260, font(FONT_BIG, 54), "#f2e6c8")
    # walking background silhouettes
    for i in range(3):
        x = ((i * 420 + t * 70 * (1 if i % 2 else -1)) % (W + 300)) - 150
        c.save(); c.translate(x, 1240); c.scale(0.35, 0.35)
        c.drawRoundRect(rect(-60, -560, 120, 330), 40, 40, fill("#6d5f4a", 160)); c.drawCircle(0, -640, 60, fill("#6d5f4a", 160))
        c.restore()

def bg_cabin(c, t, cam, o):
    c.drawRect(rect(0, 0, W, H), fill("#3a3530"))
    # ceiling + bins
    c.drawPath(poly([(0, 0), (W, 0), (W, 380), (W / 2 + 120, 640), (W / 2 - 120, 640), (0, 380)]), fill("#cfc6b6"))
    c.drawPath(poly([(0, 380), (W / 2 - 120, 640), (W / 2 - 120, 700), (0, 520)]), fill("#b4ab9a"))
    c.drawPath(poly([(W, 380), (W / 2 + 120, 640), (W / 2 + 120, 700), (W, 520)]), fill("#b4ab9a"))
    # side walls with windows showing moving clouds
    for side in (-1, 1):
        for i in range(4):
            d = i / 4
            x = W / 2 + side * (180 + 360 * (1 - d) ** 1.5)
            y = 760 - 60 * (1 - d)
            s = 0.35 + 0.65 * (1 - d) ** 1.5
            c.save(); c.translate(x, y)
            win = skia.Path(); win.addRoundRect(rect(-34 * s, -50 * s, 68 * s, 100 * s), 26 * s, 26 * s)
            c.drawPath(win, fill("#1d2238"))
            c.save(); c.clipPath(win, doAntiAlias=True)
            cx = ((t * 120 * side + i * 50) % 200) - 100
            c.drawCircle(cx * s, 0, 40 * s, fill("#4a4f6e"))
            c.restore()
            c.drawPath(win, stroke("#8f8676", 6 * s))
            c.restore()
    c.drawPath(poly([(W / 2 - 120, 700), (W / 2 + 120, 700), (W, 1300), (0, 1300)]), fill("#5a3e35"))
    c.drawPath(poly([(W / 2 - 40, 700), (W / 2 + 40, 700), (W / 2 + 240, 1300), (W / 2 - 240, 1300)]), fill("#7a2e2e"))
    # seat rows receding
    for i in range(5, -1, -1):
        d = i / 6
        s = 0.3 + 0.9 * (1 - d) ** 1.6
        y = 700 + 600 * (1 - d) ** 1.6
        for side in (-1, 1):
            x = W / 2 + side * (110 + 330 * (1 - d) ** 1.6)
            for k in range(2):
                xx = x + side * k * 150 * s
                c.drawRoundRect(rect(xx - 65 * s, y - 230 * s, 130 * s, 260 * s), 30 * s, 30 * s, fill("#2f4f7a"))
                c.drawRoundRect(rect(xx - 55 * s, y - 225 * s, 110 * s, 40 * s), 14 * s, 14 * s, fill("#e8e2d4"))
    # overhead light flicker
    a = int(30 + 10 * math.sin(t * 2.3))
    c.drawRect(rect(0, 0, W, H), fill("#ffe9b8", a))

def bg_river(c, t, cam, o):
    _sky(c, "#9fb4c8", "#dfe6ea", 900)
    for i, (col, yb, amp) in enumerate((("#6f8a7a", 820, 60), ("#4f6e5c", 900, 40))):
        p = skia.Path(); p.moveTo(0, H)
        for x in range(0, W + 41, 40):
            p.lineTo(x, yb - amp * math.sin((x + cam * (0.1 + i * 0.1)) / 180 + i * 2))
        p.lineTo(W, H); p.close()
        c.drawPath(p, fill(col))
    c.drawRect(rect(0, 980, W, 380), fill("#5d7f93"))
    for j in range(14):
        y = 1000 + j * 26
        p = skia.Path(); p.moveTo(-40, y)
        for x in range(-40, W + 41, 40):
            p.lineTo(x, y + 5 * math.sin(x / 60 + t * 2.2 + j))
        c.drawPath(p, stroke("#9ec1d4", 3, 120))
    p = skia.Path(); p.moveTo(0, 1360)
    for x in range(0, W + 41, 40):
        p.lineTo(x, 1340 + 20 * math.sin(x / 140))
    p.lineTo(W, H); p.lineTo(0, H); p.close()
    c.drawPath(p, fill("#cbb48a"))
    for i in range(14):
        x = h01(i) * W
        sway = 6 * math.sin(t * 1.5 + i)
        for k in (-12, 0, 12):
            c.drawLine(x + k, 1400 + h01(i + 3) * 200, x + k * 2 + sway, 1330 + h01(i + 3) * 200, stroke("#6f8a4a", 5))

def bg_office(c, t, cam, o):
    c.drawRect(rect(0, 0, W, H), fill("#2f3d33"))
    # window with blinds, light rays
    c.drawRect(rect(620 - cam * 0.1, 220, 360, 520), fill("#c9d6de"))
    for i in range(13):
        c.drawRect(rect(620 - cam * 0.1, 230 + i * 40, 360, 18), fill("#8a8f86"))
    ray = skia.Paint(AntiAlias=True)
    ray.setShader(skia.GradientShader.MakeLinear([skia.Point(700, 400), skia.Point(300, 1400)], [hexcol("#fff2c4", 70), hexcol("#fff2c4", 0)]))
    c.drawPath(poly([(620, 260), (980, 260), (600, 1500), (120, 1500)]), ray)
    for i in range(18):  # dust in light
        x = 400 + h01(i) * 400 + 30 * math.sin(t * 0.5 + i)
        y = 500 + ((h01(i + 4) * 900 + t * 20) % 900)
        c.drawCircle(x, y, 2.5, fill("#fff2c4", 120))
    # corkboard
    c.drawRect(rect(80 - cam * 0.1, 260, 460, 380), fill("#a07a4a"))
    pins = [(150, 330), (420, 320), (260, 520), (470, 560), (130, 590)]
    for i, (x, y) in enumerate(pins):
        c.drawRect(rect(x - 45 - cam * 0.1, y - 30, 90, 70), fill("#efe6d0"))
    for a, b in ((0, 2), (1, 2), (2, 3), (2, 4)):
        c.drawLine(pins[a][0] - cam * 0.1, pins[a][1], pins[b][0] - cam * 0.1, pins[b][1], stroke("#c0392b", 3))
    for x, y in pins:
        c.drawCircle(x - cam * 0.1, y - 30, 8, fill("#c0392b"))
    # desk
    c.drawRect(rect(0, 1300, W, 80), fill("#5a3a22")); c.drawRect(rect(0, 1380, W, H - 1380), fill("#3b2616"))
    # lamp glow
    g = skia.Paint(AntiAlias=True)
    fl = 0.9 + 0.1 * math.sin(t * 7) * math.sin(t * 3)
    g.setShader(skia.GradientShader.MakeRadial(skia.Point(860, 1250), 420, [hexcol("#ffd27a", int(110 * fl)), hexcol("#ffd27a", 0)]))
    c.drawRect(rect(0, 0, W, H), g)
    c.drawPath(poly([(800, 1150), (920, 1150), (960, 1240), (760, 1240)]), fill("#2a6b3a"))
    c.drawLine(860, 1240, 860, 1300, stroke("#888888", 8))

def bg_map(c, t, cam, o):
    c.drawRect(rect(0, 0, W, H), fill("#1c2a33"))
    for i in range(0, W, 90):
        c.drawLine(i, 0, i, H, stroke("#24343f", 2))
    for j in range(0, H, 90):
        c.drawLine(0, j, W, j, stroke("#24343f", 2))
    land = o.get("land", [(0.55, 0.0), (1.0, 0.0), (1.0, 1.0), (0.62, 1.0), (0.58, 0.8), (0.5, 0.62), (0.52, 0.45), (0.44, 0.3), (0.5, 0.15)])
    c.drawPath(poly([(x * W, 200 + y * 1300) for x, y in land]), fill("#3d4f3a"))
    c.drawPath(poly([(x * W, 200 + y * 1300) for x, y in land]), stroke("#6d8a62", 4))

def bg_street(c, t, cam, o):
    _sky(c, "#0d1020", "#3a2f45", 1100)
    _stars(c, t, 40)
    for layer, (col, sp, base) in enumerate((("#1a1d2e", 0.2, 1200), ("#11131f", 0.5, 1300))):
        for i in range(8):
            x = ((i * 170 - cam * sp) % (W + 340)) - 170
            hh = 400 + h01(i + layer * 5) * 500
            c.drawRect(rect(x, base - hh, 150, hh), fill(col))
            for wy in range(int(base - hh + 30), base - 40, 60):
                for wx in (20, 65, 110):
                    on = h01(i * 31 + wy + wx + layer) > 0.55
                    if on:
                        c.drawRect(rect(x + wx, wy, 22, 30), fill("#ffd27a", int(150 + 60 * math.sin(t + wy))))
    c.drawRect(rect(0, 1300, W, H - 1300), fill("#22232b"))
    for i in range(8):
        x = ((i * 220 - cam * 0.8 - t * 40) % (W + 220)) - 110
        c.drawRect(rect(x, 1560, 120, 16), fill("#d8d0b0", 160))
    g = skia.Paint(AntiAlias=True)
    g.setShader(skia.GradientShader.MakeRadial(skia.Point(200, 1100), 380, [hexcol("#ffcf7a", 70), hexcol("#ffcf7a", 0)]))
    c.drawRect(rect(0, 0, W, H), g)
    c.drawRect(rect(192, 760, 16, 560), fill("#2b2b2b")); c.drawCircle(200, 760, 26, fill("#ffe2a0"))
    if o.get("rain"):
        _rain(c, t, 80, 70)

def bg_battlefield(c, t, cam, o):
    _sky(c, "#4a4038", "#a58a66", 1200)
    for i in range(6):  # smoke columns
        x = 100 + i * 180 - cam * 0.2
        for k in range(6):
            yy = 1100 - k * 140 - (t * 30 % 140)
            c.drawCircle(x + 30 * math.sin(t * 0.4 + k + i), yy, 70 + k * 18, fill("#5a5048", 60))
    p = skia.Path(); p.moveTo(0, H)
    for x in range(0, W + 41, 40):
        p.lineTo(x, 1250 + 40 * math.sin(x / 120 + cam * 0.002))
    p.lineTo(W, H); p.close()
    c.drawPath(p, fill("#4a3e2c"))
    for i in range(5):  # wire posts
        x = ((i * 260 - cam * 0.7) % (W + 260)) - 130
        c.drawLine(x, 1400, x, 1280, stroke("#2b2218", 8))
        c.drawLine(x, 1300, x + 260, 1300, stroke("#3a3026", 3))
    for lt in o.get("blasts", []):
        d = t - lt
        if 0 <= d < 1.2:
            r = 80 + 500 * ease_out(d / 1.2)
            c.drawCircle(700, 1150, r, fill("#ffb347", int(200 * (1 - d / 1.2))))

def bg_palace(c, t, cam, o):
    c.drawRect(rect(0, 0, W, H), fill("#3b1d1d"))
    for i in range(6):
        x = 60 + i * 200 - cam * 0.3
        c.drawRect(rect(x, 200, 80, 1100), fill("#c9b48a")); c.drawRect(rect(x - 20, 180, 120, 40), fill("#b39e74"))
    for side in (0, 1):
        sway = 10 * math.sin(t * 0.6 + side)
        x = 0 if side == 0 else W - 260
        c.drawPath(poly([(x, 0), (x + 260, 0), (x + 200 + sway, 1300), (x + 60 + sway, 1300)]), fill("#8e1b1b"))
    c.drawRect(rect(0, 1300, W, H - 1300), fill("#6b4a2a"))
    c.drawRect(rect(W / 2 - 140, 1300, 280, H - 1300), fill("#9b1c1c"))

def bg_courtroom(c, t, cam, o):
    c.drawRect(rect(0, 0, W, H), fill("#5a3e28"))
    for i in range(8):
        c.drawRect(rect(i * 140 - cam * 0.2, 0, 10, 1100), fill("#4a321f"))
    c.drawRect(rect(200 - cam * 0.3, 700, 680, 400), fill("#3b2616"))
    c.drawCircle(540 - cam * 0.3, 450, 110, fill("#c9a94a")); c.drawCircle(540 - cam * 0.3, 450, 90, fill("#5a3e28"))
    c.drawRect(rect(0, 1100, W, H - 1100), fill("#6b4a2a"))

def bg_room(c, t, cam, o):
    c.drawRect(rect(0, 0, W, H), fill(o.get("wall", "#4d4238")))
    c.drawRect(rect(0, 1300, W, H - 1300), fill(o.get("floor", "#3a2a1e")))
    c.drawRect(rect(640 - cam * 0.2, 400, 300, 420), fill("#1d2238"))
    c.drawRect(rect(640 - cam * 0.2, 400, 300, 420), stroke("#2a1d14", 16))
    g = skia.Paint(AntiAlias=True)
    g.setShader(skia.GradientShader.MakeRadial(skia.Point(300, 900), 600, [hexcol("#ffd27a", 60), hexcol("#ffd27a", 0)]))
    c.drawRect(rect(0, 0, W, H), g)

def bg_black(c, t, cam, o):
    _sky(c, "#0b0b0d", "#1c1a1f")

BACKGROUNDS = {"sky": bg_sky_night, "sky_night": bg_sky_night, "forest_night": bg_forest_night, "airport": bg_airport,
               "cabin": bg_cabin, "river": bg_river, "office": bg_office, "map": bg_map, "street": bg_street,
               "battlefield": bg_battlefield, "palace": bg_palace, "courtroom": bg_courtroom, "room": bg_room,
               "black": bg_black}
