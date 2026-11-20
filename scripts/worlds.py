"""Multiplane 2.5D environments. Each world returns layers [(depth, fn, is_foreground)], a colour grade and a key light.
depth 0 = sky (doesn't move with camera), 1.0 = character plane, >1 = foreground (moves faster than camera)."""
import math
import numpy as np
import skia
from engine import (W, H, hexcol, shade, fill, stroke, clamp, lerp, ease_io, ease_out, h01, rect, poly, font, FONT_BIG,
                    FONT_TYPE, draw_text_c, text_w, plane_side, BACKGROUNDS)

M = 260  # overscan margin for parallax/zoom

def grad_v(top, bot, y0=0, y1=H, a0=255, a1=255):
    p = skia.Paint(AntiAlias=True)
    p.setShader(skia.GradientShader.MakeLinear([skia.Point(0, y0), skia.Point(0, y1)], [hexcol(top, a0), hexcol(bot, a1)]))
    return p

def radial(cx, cy, r, col, a, col2=None, a2=0):
    p = skia.Paint(AntiAlias=True)
    p.setShader(skia.GradientShader.MakeRadial(skia.Point(cx, cy), r, [hexcol(col, a), hexcol(col2 or col, a2)]))
    return p

def screen(p):
    p.setBlendMode(skia.BlendMode.kScreen)
    return p

# ------------------------------------------------------------------ cached sprites
_cache = {}

def _img_from(arr):
    return skia.Image.fromarray(np.ascontiguousarray(arr), colorType=skia.kRGBA_8888_ColorType)

def fog_tex():
    """Soft tileable fog/noise texture (white with alpha)."""
    if "fog" not in _cache:
        rng = np.random.default_rng(3)
        acc = np.zeros((256, 512), np.float32)
        for scale, amp in ((8, 1.0), (16, 0.5), (32, 0.25)):
            g = rng.random((scale, scale * 2)).astype(np.float32)
            g = np.concatenate([g, g[:, :1]], 1); g = np.concatenate([g, g[:1, :]], 0)
            ys = np.linspace(0, scale, 256, endpoint=False); xs = np.linspace(0, scale * 2, 512, endpoint=False)
            y0 = ys.astype(int); x0 = xs.astype(int); fy = (ys - y0)[:, None]; fx = (xs - x0)[None, :]
            fy = fy * fy * (3 - 2 * fy); fx = fx * fx * (3 - 2 * fx)
            a = g[y0][:, x0]; b = g[y0][:, x0 + 1]; cc = g[y0 + 1][:, x0]; d = g[y0 + 1][:, x0 + 1]
            acc += amp * ((a * (1 - fx) + b * fx) * (1 - fy) + (cc * (1 - fx) + d * fx) * fy)
        acc = (acc - acc.min()) / (np.ptp(acc) + 1e-9)
        al = (np.clip((acc - 0.35) / 0.65, 0, 1) ** 1.4 * 255).astype(np.uint8)
        arr = np.zeros((256, 512, 4), np.uint8); arr[..., :3] = 255; arr[..., 3] = al
        # premultiply
        arr[..., :3] = (arr[..., :3].astype(np.uint16) * al[..., None] // 255).astype(np.uint8)
        _cache["fog"] = _img_from(arr)
    return _cache["fog"]

def draw_fog(c, t, y, h, col="#9aa8c8", a=60, speed=18, scale=4.0, seed=0):
    img = fog_tex()
    tw = 512 * scale
    off = (t * speed + seed * 937) % tw
    p = skia.Paint(AntiAlias=True)
    p.setColorFilter(skia.ColorFilters.Blend(hexcol(col, 255), skia.BlendMode.kModulate))
    p.setAlphaf(a / 255)
    samp = skia.SamplingOptions(skia.FilterMode.kLinear)
    x = -off - M
    while x < W + M:
        c.drawImageRect(img, skia.Rect.MakeXYWH(x, y, tw, h), samp, p)
        x += tw

def cloud_sprite(kind=0):
    key = ("cloud", kind)
    if key not in _cache:
        s = skia.Surface(640, 300)
        cv = s.getCanvas(); cv.clear(skia.ColorTRANSPARENT)
        p = skia.Paint(AntiAlias=True); p.setImageFilter(skia.ImageFilters.Blur(10, 10))
        cv.saveLayer(None, p)
        rnd = np.random.default_rng(kind + 11)
        for i in range(14):
            x = 110 + rnd.random() * 420; y = 150 + rnd.normal(0, 22); r = 50 + rnd.random() * 70
            g = skia.Paint(AntiAlias=True)
            g.setShader(skia.GradientShader.MakeLinear([skia.Point(0, y - r), skia.Point(0, y + r)],
                                                       [hexcol("#ffffff"), hexcol("#8d93a8")]))
            cv.drawCircle(x, y, r, g)
        cv.restore()
        _cache[key] = s.makeImageSnapshot()
    return _cache[key]

def draw_cloud(c, x, y, s, col, a, kind=0):
    img = cloud_sprite(kind % 4)
    p = skia.Paint(AntiAlias=True)
    p.setColorFilter(skia.ColorFilters.Blend(hexcol(col), skia.BlendMode.kModulate)); p.setAlphaf(a / 255)
    c.drawImageRect(img, skia.Rect.MakeXYWH(x, y, 640 * s, 300 * s), skia.SamplingOptions(skia.FilterMode.kLinear), p)

def rain(c, t, n, a, speed, length, width, ang=10, seed=0, col="#b9cbe6"):
    pnt = stroke(col, width, a)
    dx = math.tan(math.radians(ang))
    span = H + 2 * M
    for i in range(n):
        x0 = h01(i * 3.1 + seed) * (W + 2 * M) - M
        y = (h01(i * 7.7 + seed) * 4000 + t * speed) % span - M
        x = x0 - y * dx
        c.drawLine(x, y, x - length * dx, y + length, pnt)

def pine(c, x, base, h, w, col):
    p = skia.Path(); p.moveTo(x, base - h)
    tiers = 5
    for i in range(tiers):
        yy = base - h + (i + 1) * h / tiers
        ww = w * (0.35 + 0.65 * (i + 1) / tiers)
        p.lineTo(x + ww / 2, yy); p.lineTo(x + ww * 0.22, yy - h / tiers * 0.25)
    for i in reversed(range(tiers)):
        yy = base - h + (i + 1) * h / tiers
        ww = w * (0.35 + 0.65 * (i + 1) / tiers)
        p.lineTo(x - ww * 0.22, yy - h / tiers * 0.25) if i < tiers - 1 else None
        p.lineTo(x - ww / 2, yy)
    p.close()
    c.drawPath(p, fill(col))
    c.drawRect(rect(x - w * 0.04, base - 6, w * 0.08, 30), fill(col))

def ridge(c, base, amp, freq, col, seed, a=255):
    p = skia.Path(); p.moveTo(-M, H + M)
    for x in range(-M, W + M + 1, 30):
        y = base - amp * (0.55 * math.sin(x * freq + seed) + 0.3 * math.sin(x * freq * 2.3 + seed * 2) + 0.15 * math.sin(x * freq * 5.1 + seed))
        p.lineTo(x, y)
    p.lineTo(W + M, H + M); p.close()
    c.drawPath(p, fill(col, a))

def godrays(c, t, x, y, ang, col, a, n=5, spread=26, length=2400):
    for i in range(n):
        an = math.radians(ang + (i - n / 2) * spread / n)
        w = 60 + 50 * h01(i + 3)
        flick = 0.75 + 0.25 * math.sin(t * 0.6 + i * 1.7)
        dx, dy = math.sin(an), math.cos(an)
        nx, ny = dy, -dx
        pts = [(x - nx * w * 0.3, y - ny * w * 0.3), (x + nx * w * 0.3, y + ny * w * 0.3),
               (x + dx * length + nx * w * 2.2, y + dy * length + ny * w * 2.2), (x + dx * length - nx * w * 2.2, y + dy * length - ny * w * 2.2)]
        p = skia.Paint(AntiAlias=True)
        p.setShader(skia.GradientShader.MakeLinear([skia.Point(x, y), skia.Point(x + dx * length, y + dy * length)],
                                                   [hexcol(col, int(a * flick)), hexcol(col, 0)]))
        c.drawPath(poly(pts), p)

def dust(c, t, x0, y0, w, h, n, col="#fff1cf", a=110):
    for i in range(n):
        x = x0 + (h01(i) * w + 30 * math.sin(t * 0.35 + i)) % w
        y = y0 + (h01(i + 40) * h - t * (6 + 10 * h01(i + 2))) % h
        c.drawCircle(x, y, 1.6 + 1.8 * h01(i + 9), fill(col, int(a * (0.5 + 0.5 * math.sin(t * 0.8 + i)))))

# ------------------------------------------------------------------ worlds
def night_sky(c, t, o):
    c.drawRect(rect(-M, -M, W + 2 * M, H + 2 * M), grad_v("#050913", "#1a1f38", -M, H * 0.9))
    c.drawRect(rect(-M, H * 0.45, W + 2 * M, H), grad_v("#1a1f38", "#2a2340", H * 0.45, H * 1.1, 0, 255))
    for i in range(110):
        x, y = h01(i) * (W + 2 * M) - M, h01(i + 999) * H * 0.55 - M * 0.5
        a = 70 + 110 * (0.5 + 0.5 * math.sin(t * (0.6 + h01(i + 5)) + i))
        c.drawCircle(x, y, 1.1 + 1.8 * h01(i + 7), fill("#e8eeff", int(a)))
    mx, my = o.get("moon", (780, 360))
    c.drawCircle(mx, my, 420, screen(radial(mx, my, 420, "#6f86c8", 90, "#6f86c8", 0)))
    c.drawCircle(mx, my, 150, screen(radial(mx, my, 150, "#dfe6ff", 120, "#dfe6ff", 0)))
    c.drawCircle(mx, my, 62, fill("#f1efe2"))
    c.drawCircle(mx - 14, my - 10, 16, fill("#d9d6c6")); c.drawCircle(mx + 18, my + 16, 10, fill("#d9d6c6"))

def clouds_layer(c, t, y, s, col, a, speed, n=4, seed=0):
    span = W + 2 * M + 640 * s
    for i in range(n):
        x = (h01(i + seed * 17) * span + -t * speed + i * span / n) % span - M - 640 * s * 0.5
        draw_cloud(c, x, y + 120 * math.sin(i * 2.3 + seed), s, col, a, kind=i + seed)

def W_forest_night(o):
    lt = o.get("lightning", [])
    def flash(t):
        v = 0.0
        for l in lt:
            d = t - l
            if 0 <= d < 0.9:
                v = max(v, clamp(d / 0.06) * math.exp(-max(0, d - 0.06) * 4.5))
        return v
    def sky(c, t, o_):
        night_sky(c, t, o)
        clouds_layer(c, t, 180, 1.6, "#4a5378", 150, 12, 3, 1)
        f = flash(t)
        if f > 0:
            c.drawRect(rect(-M, -M, W + 2 * M, H + 2 * M), fill("#c9d6ff", int(70 * f)))
    def mountains(c, t, o_):
        ridge(c, 1060, 160, 0.004, "#1c2340", 2.0)
        draw_fog(c, t, 900, 360, "#7d8bb8", 55, 8, 4.5, 1)
        ridge(c, 1180, 110, 0.006, "#151a30", 4.1)
    def trees_far(c, t, o_):
        for i in range(16):
            x = i * 95 - M + 40 * h01(i)
            pine(c, x, 1330, 260 + 120 * h01(i + 3), 120, "#10152a")
        c.drawRect(rect(-M, 1320, W + 2 * M, H), fill("#10152a"))
        draw_fog(c, t, 1180, 300, "#8090c0", 50, 14, 4.0, 2)
    def trees_mid(c, t, o_):
        for i in range(10):
            x = i * 150 - M + 60 * h01(i + 20)
            sway = 2 * math.sin(t * 0.8 + i)
            c.save(); c.translate(x, 1560); c.rotate(sway * 0.3); pine(c, 0, 0, 420 + 160 * h01(i + 5), 170, "#0a0e1d"); c.restore()
        c.drawRect(rect(-M, 1550, W + 2 * M, H), fill("#0a0e1d"))
        rain(c, t, 70, 55, 1500, 50, 2, seed=1)
        draw_fog(c, t, 1420, 260, "#6f7fb0", 45, 22, 3.2, 3)
    def fg(c, t, o_):
        rain(c, t, 26, 70, 2600, 140, 4.5, seed=2, col="#c8d6f0")
        for sx in (-1, 1):
            x = -80 if sx < 0 else W + 80
            sway = 6 * math.sin(t * 0.9 + sx)
            c.save(); c.translate(x, 1750); c.rotate(sway * 0.4)
            pine(c, 0, 0, 1500, 520, "#05070e")
            c.restore()
    return {"layers": [(0.0, sky, False), (0.15, mountains, False), (0.4, trees_far, False), (0.7, trees_mid, False), (1.55, fg, True)],
            "grade": ("#1b2a5c", 0.22), "light": {"dx": -1, "rim": "#a9c0ff", "rim_a": 150, "shadow": "#070b18", "sa": 125},
            "bloom": 0.35, "flash": flash}

def W_sky(o):
    base = W_forest_night(o)
    def sky(c, t, o_):
        night_sky(c, t, o)
        clouds_layer(c, t, 140, 1.7, "#454d70", 160, 10, 3, 4)
    def clouds_mid(c, t, o_):
        clouds_layer(c, t, 700, 2.1, "#383f60", 200, 40, 3, 5)
        draw_fog(c, t, 900, 500, "#6a78a8", 45, 30, 4.0, 6)
        if o.get("rain", True):
            rain(c, t, 70, 50, 1500, 50, 2, seed=3)
    def clouds_low(c, t, o_):
        clouds_layer(c, t, 1350, 2.6, "#262b45", 235, 90, 3, 7)
    def fg(c, t, o_):
        clouds_layer(c, t, 1500, 3.4, "#1a1d30", 210, 260, 2, 8)
        if o.get("rain", True):
            rain(c, t, 22, 70, 2600, 140, 4.5, seed=4, col="#c8d6f0")
    f = base["flash"]
    def sky2(c, t, o_):
        sky(c, t, o_)
        v = f(t)
        if v > 0:
            c.drawRect(rect(-M, -M, W + 2 * M, H + 2 * M), fill("#c9d6ff", int(70 * v)))
    return {"layers": [(0.0, sky2, False), (0.3, clouds_mid, False), (0.75, clouds_low, False), (1.7, fg, True)],
            "grade": ("#1b2a5c", 0.2), "light": base["light"], "bloom": 0.4, "flash": f}

def W_airport(o):
    board = o.get("board", ["FLT 305  SEATTLE   2:50"])
    def outside(c, t, o_):
        c.drawRect(rect(-M, -M, W + 2 * M, 1000 + M), grad_v("#2e3a5e", "#e0956a", 120, 860))
        c.drawCircle(860, 820, 380, screen(radial(860, 820, 380, "#ffb27a", 140, "#ffb27a", 0)))
        ridge(c, 830, 40, 0.01, "#4a4256", 1.0)
        c.drawRect(rect(-M, 830, W + 2 * M, 200), fill("#3d3a44"))
        for i in range(14):
            x = i * 90 - M + ((t * 4) % 90)
            c.drawCircle(x, 880, 4, fill("#ffd27a", int(160 + 90 * math.sin(t * 3 + i))))
        c.save(); c.translate(520, 790); c.scale(0.5, 0.5); plane_side(c, t, {"windows_lit": False}); c.restore()
    def hall(c, t, o_):
        # window wall frame, ceiling, columns
        c.drawRect(rect(-M, -M, W + 2 * M, 280 + M), fill("#2a2420"))
        for i in range(-2, 9):
            x = i * 170
            c.drawRect(rect(x - 9, 250, 18, 760), fill("#1d1916"))
        c.drawRect(rect(-M, 240, W + 2 * M, 22), fill("#1d1916")); c.drawRect(rect(-M, 1000, W + 2 * M, 26), fill("#1d1916"))
        for i in range(-1, 8):
            x = 80 + i * 170
            c.drawRect(rect(x - 40, 210, 80, 10), fill("#ffe2b0"))
            c.drawPath(poly([(x - 40, 220), (x + 40, 220), (x + 140, 1000), (x - 140, 1000)]), screen(grad_v("#ffcf8a", "#ffcf8a", 220, 1000, 34, 0)))
        # wall below windows with split-flap board
        c.drawRect(rect(-M, 1026, W + 2 * M, 300), fill("#5a4632"))
        bx, by = 130, 1060
        c.drawRoundRect(rect(bx, by, 820, 210), 10, 10, fill("#121212"))
        draw_text_c(c, "DEPARTURES", bx + 410, by + 40, font(FONT_TYPE, 30), "#f5c542")
        f = font(FONT_TYPE, 40)
        for r, row in enumerate(board[:3]):
            for k, ch in enumerate(row[:28]):
                cx = bx + 30 + k * 27.5; cy = by + 70 + r * 46
                c.drawRect(rect(cx, cy, 24, 38), fill("#1d1d1d"))
                flip = clamp((t - 0.25 - r * 0.25 - k * 0.025) / 0.18)
                if flip <= 0:
                    continue
                sq = abs(math.cos(flip * math.pi)) if flip < 1 else 1.0
                c.save(); c.translate(cx + 12, cy + 19); c.scale(1, max(0.05, sq) if flip < 1 else 1)
                shown = ch if flip > 0.5 else chr(65 + (k * 7 + r) % 26)
                c.drawString(shown, -10, 13, f, fill("#f5c542"))
                c.restore()
                c.drawLine(cx, cy + 19, cx + 24, cy + 19, stroke("#000000", 1.5))
        # counter
        if o.get("counter", True):
            cx = 640
            c.drawRect(rect(cx, 1190, 520, 260), fill("#6a1d1d"))
            c.drawRect(rect(cx, 1190, 520, 26), fill("#8a2a24"))
            draw_text_c(c, o.get("sign", "NORTHWEST ORIENT"), cx + 260, 1300, font(FONT_BIG, 50), "#f0e2c0")
    def floor(c, t, o_):
        c.drawRect(rect(-M, 1320, W + 2 * M, H), grad_v("#5e4c38", "#2b2118", 1320, H))
        for i in range(-14, 16):
            x0 = W / 2 + i * 110
            c.drawLine(W / 2 + (x0 - W / 2) * 0.3, 1320, x0 + (x0 - W / 2) * 1.6, H + M, stroke("#4a3b2c", 3))
        for i in range(8):
            y = 1320 + (i ** 1.9) * 16
            c.drawLine(-M, y, W + M, y, stroke("#4a3b2c", 3))
        # reflections of the bright window
        c.drawRect(rect(-M, 1330, W + 2 * M, 260), screen(grad_v("#e0956a", "#e0956a", 1330, 1590, 70, 0)))
        # passengers walking (silhouettes)
        for i in range(4):
            d = 1 if i % 2 else -1
            x = ((i * 380 + t * 85 * d) % (W + 400)) - 200
            y = 1350 + i * 18
            c.save(); c.translate(x, y); c.scale(d * 0.21, 0.21)
            ph = t * 1.5 * 2 * math.pi + i
            col = ["#2b2530", "#3a2e2a", "#2a2e38", "#33292a"][i]
            c.drawRoundRect(rect(-70, -800, 140, 340), 50, 50, fill(col)); c.drawCircle(0, -880, 52, fill(col))
            for s_ in (-1, 1):
                a = math.radians(26 * math.sin(ph) * s_)
                c.drawLine(s_ * 30, -470, s_ * 30 + math.sin(a) * 460, -470 + math.cos(a) * 460, stroke(col, 50))
            c.restore()
    def fg(c, t, o_):
        x = ((-t * 60) % (W + 900)) - 300
        c.drawRect(rect(x, -M, 170, H + 2 * M), grad_v("#120e0b", "#0a0806"))
        c.drawRect(rect(x + 150, -M, 20, H + 2 * M), fill("#ffcf8a", 40))
    return {"layers": [(0.08, outside, False), (0.45, hall, False), (0.7, floor, False), (1.6, fg, True)],
            "grade": ("#7a4a1c", 0.16), "light": {"dx": 1, "rim": "#ffd49a", "rim_a": 150, "shadow": "#1a0f08", "sa": 110},
            "bloom": 0.3}

def W_cabin(o):
    def shell(c, t, o_):
        c.drawRect(rect(-M, -M, W + 2 * M, H + 2 * M), fill("#1a1512"))
        vx, vy = W / 2, 760
        c.drawPath(poly([(-M, -M), (W + M, -M), (W + M, 420), (vx + 150, vy - 90), (vx - 150, vy - 90), (-M, 420)]), grad_v("#d6cbb6", "#8a7f6c", -M, vy))
        c.drawPath(poly([(-M, 420), (vx - 150, vy - 90), (vx - 150, vy - 20), (-M, 600)]), fill("#a59a86"))
        c.drawPath(poly([(W + M, 420), (vx + 150, vy - 90), (vx + 150, vy - 20), (W + M, 600)]), fill("#a59a86"))
        c.drawRect(rect(vx - 150, vy - 90, 300, 220), fill("#3b3029"))  # bulkhead
        c.drawRect(rect(vx - 40, vy - 40, 80, 170), fill("#6f2a2a"))
        for i in range(8):  # ceiling lights receding
            d = i / 8
            y = lerp(-60, vy - 90, d ** 0.6)
            w = lerp(420, 120, d ** 0.6)
            c.drawRoundRect(rect(vx - w / 2, y, w, lerp(26, 6, d)), 6, 6, fill("#fff1cf"))
            c.drawCircle(vx, y + 30, lerp(260, 60, d), screen(radial(vx, y + 30, lerp(260, 60, d), "#ffcf8a", 60, "#ffcf8a", 0)))
        for side in (-1, 1):  # windows with night clouds
            for i in range(5):
                d = i / 5
                s = lerp(1.0, 0.25, d ** 0.7)
                x = vx + side * lerp(470, 170, d ** 0.7)
                y = lerp(560, vy - 30, d ** 0.7)
                c.save(); c.translate(x, y)
                win = skia.Path(); win.addRoundRect(rect(-40 * s, -58 * s, 80 * s, 116 * s), 32 * s, 32 * s)
                c.drawPath(win, grad_v("#0a1022", "#232a48", -58 * s, 58 * s))
                c.save(); c.clipPath(win, doAntiAlias=True)
                cx = ((t * 160 * -side + i * 70) % 260) - 130
                c.drawCircle(cx * s, 10 * s, 50 * s, fill("#4a5272", 200))
                c.drawCircle(cx * s + 60 * s, -20 * s, 34 * s, fill("#3a4262", 200))
                c.restore()
                c.drawPath(win, stroke("#cfc4ae", 8 * s))
                c.restore()
        c.drawPath(poly([(vx - 150, vy + 130), (vx + 150, vy + 130), (W + M, H + M), (-M, H + M)]), fill("#3b2a24"))
        c.drawPath(poly([(vx - 40, vy + 130), (vx + 40, vy + 130), (vx + 330, H + M), (vx - 330, H + M)]), grad_v("#5a1f1f", "#7a2a28", vy, H))
    def rows(c, t, o_):
        vx, vy = W / 2, 760
        for i in range(6, -1, -1):
            d = i / 7
            s = lerp(1.15, 0.22, d ** 0.65)
            y = lerp(1500, vy + 120, d ** 0.65)
            for side in (-1, 1):
                for k in range(3):
                    x = vx + side * (lerp(250, 70, d ** 0.65) + k * 165 * s)
                    seat = skia.Path(); seat.addRoundRect(rect(x - 74 * s, y - 280 * s, 148 * s, 300 * s), 36 * s, 36 * s)
                    c.drawPath(seat, grad_v("#33507e", "#1b2b46", y - 280 * s, y))
                    c.drawRoundRect(rect(x - 62 * s, y - 274 * s, 124 * s, 46 * s), 14 * s, 14 * s, fill("#e9e2d2"))
                    # passengers' heads above seat backs
                    if h01(i * 7 + k * 3 + side) > 0.35 and i > 0:
                        hc = ["#1d1714", "#6a4a2a", "#c9a45a", "#8a8780", "#3a2618"][int(h01(i + k + side * 2) * 5)]
                        bob = 3 * s * math.sin(t * (0.6 + h01(i + k)) + i + k)
                        c.drawOval(rect(x - 36 * s, y - 360 * s + bob, 72 * s, 92 * s), fill("#c99a7a"))
                        c.drawOval(rect(x - 38 * s, y - 370 * s + bob, 76 * s, 60 * s), fill(hc))
                        c.drawRoundRect(rect(x - 74 * s, y - 286 * s, 148 * s, 46 * s), 14 * s, 14 * s, fill("#e9e2d2"))
                    c.drawPath(seat, stroke("#0e1626", 3 * s))
        dust(c, t, 0, 300, W, 1100, 26, "#fff1cf", 70)
    def fg(c, t, o_):
        for side in (-1, 1):
            x = -120 if side < 0 else W - 160
            c.drawRoundRect(rect(x, 1150, 280, 1100), 80, 80, grad_v("#141c2c", "#070a12", 1150, H))
            c.drawRoundRect(rect(x + 20, 1170, 240, 70), 22, 22, fill("#8f897c", 160))
    return {"layers": [(0.25, shell, False), (0.6, rows, False), (1.45, fg, True)],
            "grade": ("#8a4e1a", 0.18), "light": {"dx": 1, "rim": "#ffd8a0", "rim_a": 140, "shadow": "#1a0f08", "sa": 115},
            "bloom": 0.32}

def W_office(o):
    labels = o.get("labels") or [""]
    def wall(c, t, o_):
        c.drawRect(rect(-M, -M, W + 2 * M, H + 2 * M), grad_v("#26302a", "#141a17", 0, H))
        # window with blinds
        wx, wy = 700, 180
        c.drawRect(rect(wx, wy, 330, 560), fill("#c5d0d8"))
        for i in range(14):
            c.drawRect(rect(wx, wy + 10 + i * 40, 330, 20), fill("#6f746c"))
        godrays(c, t, wx + 160, wy + 260, 210, "#ffe9b8", 38, 4, 30, 1900)
        dust(c, t, 200, 400, 800, 1200, 30, "#fff1cf", 120)
    def board(c, t, o_):
        bx, by, bw_, bh = 70, 250, 600, 640
        c.drawRect(rect(bx - 14, by - 14, bw_ + 28, bh + 28), fill("#3b2616"))
        c.drawRect(rect(bx, by, bw_, bh), fill("#9c7448"))
        rnd = [(0.12, 0.1), (0.62, 0.08), (0.36, 0.42), (0.78, 0.5), (0.1, 0.72), (0.56, 0.8)]
        pins = []
        for i, (u, v) in enumerate(rnd):
            x, y = bx + u * bw_, by + v * bh
            rot = (h01(i) - 0.5) * 10
            c.save(); c.translate(x + 70, y + 55); c.rotate(rot)
            if i % 2 == 0:  # photo / sketch
                c.drawRect(rect(-70, -55, 140, 120), fill("#efe8d8"))
                c.drawRect(rect(-60, -46, 120, 88), fill("#5c5850"))
                c.drawCircle(0, -10, 22, fill("#8a8478")); c.drawRoundRect(rect(-32, 12, 64, 40), 18, 18, fill("#8a8478"))
                c.drawRect(rect(-14, -16, 28, 8), fill("#222222"))
            else:  # clipping with label
                c.drawRect(rect(-80, -50, 160, 110), fill("#e9e2cf"))
                lab = labels[(i // 2) % len(labels)]
                if lab:
                    f = font(FONT_BIG, 26 if len(lab) < 10 else 20)
                    draw_text_c(c, lab, 0, -18, f, "#1c1a17")
                else:
                    c.drawRect(rect(-60, -34, 120, 22), fill("#3a3632"))
                for k in range(4):
                    c.drawLine(-64, 0 + k * 13, 60 - (k % 2) * 30, 0 + k * 13, stroke("#8f897a", 4))
            c.restore()
            pins.append((x + 70, y + 8))
        # animated red strings, drawn on one after another
        for k, (a, b) in enumerate(((0, 2), (1, 2), (2, 3), (2, 4), (4, 5), (3, 5))):
            pr = ease_io((t - 0.4 - k * 0.35) / 0.6)
            if pr <= 0:
                continue
            (x1, y1), (x2, y2) = pins[a], pins[b]
            c.drawLine(x1, y1, lerp(x1, x2, pr), lerp(y1, y2, pr), stroke("#c0302a", 3.2))
        for x, y in pins:
            c.drawCircle(x, y, 8, fill("#c0302a")); c.drawCircle(x - 2, y - 2, 2.5, fill("#ffffff", 150))
    def desk(c, t, o_):
        c.drawRect(rect(-M, 1430, W + 2 * M, 60), fill("#4a3020"))
        c.drawRect(rect(-M, 1490, W + 2 * M, H), grad_v("#2e1d12", "#140c07", 1490, H))
        lx = 900
        fl = 0.92 + 0.08 * math.sin(t * 5.3) * math.sin(t * 2.1)
        c.drawCircle(lx, 1400, 560, screen(radial(lx, 1400, 560, "#ffc56a", int(120 * fl), "#ffc56a", 0)))
        c.drawPath(poly([(lx - 70, 1270), (lx + 70, 1270), (lx + 110, 1360), (lx - 110, 1360)]), fill("#2a5a34"))
        c.drawLine(lx, 1360, lx, 1430, stroke("#8a8a8a", 9))
        c.drawRect(rect(60, 1380, 300, 60), fill("#c9b48a")); c.drawRect(rect(80, 1350, 280, 40), fill("#d8c79e"))
        # coffee steam
        c.drawRoundRect(rect(450, 1370, 70, 70), 10, 10, fill("#e8e2d6"))
        for k in range(3):
            p = skia.Path(); y0 = 1360
            p.moveTo(470 + k * 15, y0)
            for j in range(1, 8):
                p.lineTo(470 + k * 15 + 10 * math.sin(t * 2 + j * 0.9 + k), y0 - j * 22)
            c.drawPath(p, stroke("#ffffff", 4, 40))
    return {"layers": [(0.2, wall, False), (0.5, board, False), (1.3, desk, True)],
            "grade": ("#7a5a20", 0.16), "light": {"dx": 1, "rim": "#ffd090", "rim_a": 150, "shadow": "#100a06", "sa": 120},
            "bloom": 0.3}

def W_river(o):
    def sky(c, t, o_):
        c.drawRect(rect(-M, -M, W + 2 * M, H), grad_v("#8ea1b0", "#d6dcd8", -M, 1000))
        clouds_layer(c, t, 120, 1.8, "#e8ebe8", 170, 6, 3, 9)
        c.drawCircle(300, 300, 500, screen(radial(300, 300, 500, "#fff4dc", 60, "#fff4dc", 0)))
    def hills(c, t, o_):
        ridge(c, 900, 90, 0.004, "#7f9290", 1.3)
        draw_fog(c, t, 760, 280, "#e6ece8", 70, 6, 4.0, 4)
        ridge(c, 960, 60, 0.007, "#5f7568", 3.3)
        for i in range(18):
            x = i * 80 - M
            c.drawCircle(x, 960 - 30 * h01(i), 50 + 20 * h01(i + 1), fill("#4a6050"))
    def water(c, t, o_):
        c.drawRect(rect(-M, 980, W + 2 * M, 420), grad_v("#6f8b96", "#4b6672", 980, 1400))
        c.drawRect(rect(-M, 985, W + 2 * M, 60), fill("#4a6050", 90))  # tree reflection
        for j in range(16):
            y = 1000 + j * 25
            p = skia.Path(); p.moveTo(-M, y)
            for x in range(-M, W + M + 1, 30):
                p.lineTo(x, y + 4 * math.sin(x / 55 + t * 1.9 + j * 1.3))
            c.drawPath(p, stroke("#b8d0d8", 2.5, 90 - j * 3))
    def bank(c, t, o_):
        p = skia.Path(); p.moveTo(-M, 1380)
        for x in range(-M, W + M + 1, 40):
            p.lineTo(x, 1370 + 22 * math.sin(x / 150))
        p.lineTo(W + M, H + M); p.lineTo(-M, H + M); p.close()
        c.drawPath(p, grad_v("#c8b088", "#9b845e", 1370, H))
        for i in range(40):
            c.drawCircle(h01(i) * W, 1420 + h01(i + 3) * 480, 3 + 4 * h01(i + 6), fill("#8a7550", 120))
    def fg(c, t, o_):
        for i in range(9):
            x = -100 + i * 160 + (60 if i % 2 else 0)
            if 250 < x < 830:
                continue
            for k in range(5):
                sway = 10 * math.sin(t * 1.3 + i + k * 0.5)
                p = skia.Path(); p.moveTo(x + k * 14, H + 40)
                p.quadTo(x + k * 14 + sway * 0.5, 1650, x + k * 18 + sway, 1500 - 60 * h01(i + k))
                c.drawPath(p, stroke(["#53683a", "#6b7f45", "#45592f"][k % 3], 9))
    return {"layers": [(0.0, sky, False), (0.2, hills, False), (0.55, water, False), (0.85, bank, False), (1.5, fg, True)],
            "grade": ("#5f7a74", 0.12), "light": {"dx": -1, "rim": "#f4f0e6", "rim_a": 120, "shadow": "#1c2622", "sa": 95},
            "bloom": 0.22}


def W_prison(o):
    def back(c, t, o_):
        c.drawRect(rect(-M, -M, W + 2 * M, H + 2 * M), grad_v("#1d2224", "#0e1112", -M, H))
        for i in range(4):  # high barred windows with moonlight
            x = 120 + i * 250
            c.drawRect(rect(x, 140, 110, 170), fill("#3a4a66"))
            for k in range(5):
                c.drawRect(rect(x + 10 + k * 22, 140, 6, 170), fill("#111416"))
            godrays(c, t, x + 55, 300, 20 - i * 6, "#b8c8e8", 30, 3, 20, 1500)
    def tiers(c, t, o_):
        vx = W / 2
        for side in (-1, 1):
            for tier in range(3):
                y0 = 420 + tier * 330
                for i in range(7):
                    d = i / 7
                    x = vx + side * lerp(560, 150, d ** 0.7)
                    w_ = lerp(170, 40, d ** 0.7); h_ = lerp(260, 90, d ** 0.7)
                    yy = lerp(y0, 560 + tier * 120, d ** 0.7)
                    c.drawRect(rect(x - w_ / 2, yy, w_, h_), fill("#16191b"))
                    for k in range(6):
                        c.drawRect(rect(x - w_ / 2 + k * w_ / 6, yy, max(2, w_ * 0.04), h_), fill("#6e7478"))
                    c.drawRect(rect(x - w_ / 2, yy + h_ - 6, w_, 6), fill("#4a5054"))
                c.drawLine(vx + side * 650, y0 + 270, vx + side * 120, 560 + tier * 120 + 80, stroke("#5a6064", 6))
        for i in range(6):  # hanging lights
            y = 200 + i * 40; x = vx + (i - 2.5) * 30
            c.drawCircle(x, y, 14, fill("#fff6d8"))
            c.drawCircle(x, y + 40, 260 - i * 25, screen(radial(x, y + 40, 260 - i * 25, "#dfe8ff", 40, "#dfe8ff", 0)))
        c.drawPath(poly([(vx - 120, 900), (vx + 120, 900), (W + M, H + M), (-M, H + M)]), grad_v("#3a3f42", "#1a1d1f", 900, H))
        c.drawRect(rect(vx - 160, 1200, 320, 500), screen(grad_v("#dfe8ff", "#dfe8ff", 1200, 1700, 30, 0)))
        if o.get("guard", True):  # patrolling guard silhouette in the distance
            x = vx + 120 * math.sin(t * 0.25)
            c.save(); c.translate(x, 1040); c.scale(0.16, 0.16)
            c.drawRoundRect(rect(-70, -800, 140, 340), 50, 50, fill("#0c0e10")); c.drawCircle(0, -880, 52, fill("#0c0e10"))
            c.drawRoundRect(rect(-80, -960, 160, 40), 14, 14, fill("#0c0e10"))
            for s_ in (-1, 1):
                a = math.radians(20 * math.sin(t * 6 + (0 if s_ < 0 else math.pi)))
                c.drawLine(s_ * 30, -470, s_ * 30 + math.sin(a) * 460, -470 + math.cos(a) * 460, stroke("#0c0e10", 50))
            c.restore()
        dust(c, t, 0, 300, W, 1200, 22, "#e8f0ff", 60)
    def fg(c, t, o_):
        if o.get("bars"):
            for k in range(-1, 9):
                x = k * 150 + 20
                c.drawRect(rect(x, -M, 26, H + 2 * M), grad_v("#2a2e30", "#0e1011"))
                c.drawRect(rect(x + 4, -M, 5, H + 2 * M), fill("#9aa2a8", 70))
            c.drawRect(rect(-M, 300, W + 2 * M, 24), fill("#1a1d1f"))
    return {"layers": [(0.15, back, False), (0.55, tiers, False), (1.5, fg, True)],
            "grade": ("#4a6a6a", 0.16), "light": {"dx": 1, "rim": "#dfe8ff", "rim_a": 150, "shadow": "#06090c", "sa": 125},
            "bloom": 0.3}

def W_sea_night(o):
    def sky(c, t, o_):
        night_sky(c, t, dict(o, moon=o.get("moon", (300, 380))))
        clouds_layer(c, t, 260, 1.5, "#3f4766", 120, 8, 3, 12)
    def horizon(c, t, o_):
        hy = 980
        if o.get("city", True):
            for i in range(60):
                x = -M + i * 26
                hh = 20 + 90 * h01(i + 30) ** 2
                c.drawRect(rect(x, hy - hh, 22, hh), fill("#141a2c"))
                if h01(i * 3) > 0.35:
                    c.drawCircle(x + 11, hy - hh * h01(i + 7), 2.5, fill("#ffd48a", int(150 + 90 * math.sin(t * 2 + i))))
        if o.get("island", False):
            ix = o.get("island_x", 760)
            c.drawPath(poly([(ix - 260, hy + 6), (ix - 200, hy - 70), (ix - 60, hy - 110), (ix + 140, hy - 100), (ix + 260, hy + 6)]), fill("#0d1120"))
            c.drawRect(rect(ix - 120, hy - 170, 220, 70), fill("#121729"))
            c.drawRect(rect(ix + 120, hy - 230, 16, 130), fill("#121729"))
            for k in range(8):
                c.drawCircle(ix - 100 + k * 26, hy - 140, 3, fill("#ffe2a0", 200))
            ang = t * 40 % 360
            bx, by = ix + 128, hy - 232
            r = math.radians(ang)
            p = skia.Paint(AntiAlias=True)
            p.setShader(skia.GradientShader.MakeLinear([skia.Point(bx, by), skia.Point(bx + math.cos(r) * 900, by + math.sin(r) * 120)],
                                                       [hexcol("#fff2c8", int(110 * abs(math.cos(r)))), hexcol("#fff2c8", 0)]))
            c.drawPath(poly([(bx, by), (bx + math.cos(r) * 900, by + math.sin(r) * 120 - 60), (bx + math.cos(r) * 900, by + math.sin(r) * 120 + 60)]), p)
            c.drawCircle(bx, by, 9, fill("#fff2c8"))
        draw_fog(c, t, hy - 140, 260, "#8090b8", 60, 12, 4.0, 13)
    def water(c, t, o_):
        hy = 980
        c.drawRect(rect(-M, hy, W + 2 * M, H), grad_v("#141a30", "#05070e", hy, H))
        mx = o.get("moon", (300, 380))[0]
        for j in range(40):  # moon glitter path
            y = hy + 10 + j ** 1.6 * 2.2
            wdt = 30 + j * 6
            off = 20 * math.sin(t * 1.4 + j * 0.9)
            c.drawRect(rect(mx - wdt / 2 + off, y, wdt * (0.4 + 0.6 * h01(j + int(t * 3) % 7)), 3 + j * 0.15), fill("#dfe6ff", int(150 - j * 3)))
        for j in range(26):
            y = hy + 20 + j ** 1.5 * 3.4
            p = skia.Path(); p.moveTo(-M, y)
            for x in range(-M, W + M + 1, 40):
                p.lineTo(x, y + (2 + j * 0.5) * math.sin(x / (40 + j * 6) + t * (1.1 + j * 0.05) + j))
            c.drawPath(p, stroke("#4a5680", 1.5 + j * 0.12, 120))
    def fg(c, t, o_):
        for k in range(2):
            base = 1700 + k * 120
            p = skia.Path(); p.moveTo(-M, H + M)
            for x in range(-M, W + M + 1, 30):
                p.lineTo(x, base - 50 * math.sin(x / 210 + t * (1.2 + k * 0.3) + k * 2) - 25 * math.sin(x / 90 + t * 2.1))
            p.lineTo(W + M, H + M); p.close()
            c.drawPath(p, grad_v("#0c1222", "#03050a", base - 80, H))
            c.drawPath(p, stroke("#6a78a8", 2, 90))
        if o.get("rain"):
            rain(c, t, 24, 70, 2600, 140, 4.5, seed=6, col="#c8d6f0")
    return {"layers": [(0.0, sky, False), (0.2, horizon, False), (0.6, water, False), (1.5, fg, True)],
            "grade": ("#1b2a5c", 0.2), "light": {"dx": -1, "rim": "#b8c8ff", "rim_a": 150, "shadow": "#05080f", "sa": 125},
            "bloom": 0.38}

def legacy(name):
    fn = BACKGROUNDS[name]
    def build(o):
        return {"layers": [(0.6, lambda c, t, o_: fn(c, t, 0, o), False)],
                "grade": {"street": ("#26306a", 0.15), "battlefield": ("#6a4a2a", 0.15), "palace": ("#6a2a1a", 0.12),
                          "courtroom": ("#6a4a20", 0.12), "room": ("#6a4a20", 0.12), "map": ("#203040", 0.1),
                          "black": ("#000000", 0.0)}.get(name, ("#000000", 0.0)),
                "light": {"dx": 1, "rim": "#ffd8a0", "rim_a": 130, "shadow": "#100a06", "sa": 110}, "bloom": 0.25}
    return build

WORLDS = {"forest_night": W_forest_night, "sky": W_sky, "sky_night": W_sky, "airport": W_airport, "cabin": W_cabin,
          "office": W_office, "evidence": W_office, "river": W_river, "prison": W_prison, "sea_night": W_sea_night}
for _n in ("street", "battlefield", "palace", "courtroom", "room", "map", "black"):
    WORLDS[_n] = legacy(_n)
