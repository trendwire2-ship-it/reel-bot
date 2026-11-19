"""Cinematic 2D character rig: realistic (~1:7) proportions, cel shading with a scene key light and rim light,
soft tinted outlines, and animation principles (anticipation, follow-through, ease in/out, secondary motion).

Local units: feet at y=0, top of head ~ -960. Positive limb angles swing toward the facing direction (+x)."""
import math
import skia
from engine import (hexcol, rgb, shade, fill, stroke, clamp, lerp, ease_io, ease_out, ease_back, h01, rect, poly,
                    hair_col, font, FONT_BIG, draw_text_c)

HIP_Y, SH_Y = -470.0, -790.0
HEAD_Y = -900.0
THIGH, SHIN, UPPER, FORE = 232.0, 228.0, 188.0, 172.0

DEFAULT_LIGHT = {"dx": 1.0, "rim": "#ffd9a0", "rim_a": 150, "shadow": "#120c18", "sa": 105}


def mix(c1, c2, k):
    a, b = rgb(c1) if isinstance(c1, str) else c1, rgb(c2) if isinstance(c2, str) else c2
    return tuple(lerp(x, y, k) for x, y in zip(a[:3], b[:3]))


class Character:
    def __init__(self, spec):
        s = dict(spec)
        self.s = s
        self.skin = s.get("skin", "#c99a76")
        self.hair = hair_col(s.get("hair", "black"))
        self.style = s.get("hair_style", "short")
        self.outfit = s.get("outfit", "suit")
        self.oc = s.get("outfit_color", "#1f2026")
        self.shirt = s.get("shirt_color", "#eeebe4")
        self.tie = s.get("tie_color", "#0c0c0e")
        self.pants = s.get("pants_color", self.oc if self.outfit in ("suit", "uniform", "raincoat", "coat") else "#2b3446")
        self.bw = {"slim": 0.92, "average": 1.0, "heavy": 1.2}.get(s.get("build", "average"), 1.0)
        if float(s.get("age", 35)) < 13:
            self.bw *= 1.3
        self.hscale = float(s.get("height", 1.0))
        self.female = s.get("gender", "m") == "f"
        self.child = float(s.get("age", 35)) < 13
        self.seed = h01(s.get("name", "x"))
        self.L = DEFAULT_LIGHT

    # ------------------------------------------------------------ shading primitives
    def part(self, c, path, base, outline=True, rim=True, shadow=True):
        L = self.L
        b = path.computeTightBounds()
        c.drawPath(path, fill(base))
        if shadow:
            c.save(); c.clipPath(path, doAntiAlias=True)
            p = skia.Paint(AntiAlias=True)
            x0, x1 = (b.right(), b.left()) if self.ldx > 0 else (b.left(), b.right())
            sh = hexcol(L["shadow"], 0)
            p.setShader(skia.GradientShader.MakeLinear(
                [skia.Point(x0, 0), skia.Point(x1, 0)],
                [sh, sh, hexcol(L["shadow"], L["sa"]), hexcol(L["shadow"], L["sa"] + 25)], [0, 0.46, 0.6, 1.0]))
            c.drawRect(b.makeOutset(4, 4), p)
            # soft top-down occlusion
            p2 = skia.Paint(AntiAlias=True)
            p2.setShader(skia.GradientShader.MakeLinear([skia.Point(0, b.top()), skia.Point(0, b.bottom())],
                                                        [hexcol("#000000", 0), hexcol("#000000", 45)]))
            c.drawRect(b.makeOutset(4, 4), p2)
            c.restore()
        if rim:
            moved = skia.Path(path); moved.offset(-6 * self.ldx, 3)
            cres = skia.Op(path, moved, skia.PathOp.kDifference_PathOp)
            if cres is not None:
                c.drawPath(cres, fill(L["rim"], int(L["rim_a"] * 0.8)))
        if outline:
            c.drawPath(path, stroke(shade(base if isinstance(base, str) else "#%02x%02x%02x" % tuple(int(v) for v in base[:3]), 0.42), 2.6, 230))

    def seg_path(self, pts, w):
        src = skia.Path(); src.moveTo(*pts[0])
        for q in pts[1:]:
            src.lineTo(*q)
        p = skia.Paint(Style=skia.Paint.kStroke_Style, StrokeWidth=w, StrokeCap=skia.Paint.kRound_Cap,
                       StrokeJoin=skia.Paint.kRound_Join, AntiAlias=True)
        dst = skia.Path(); p.getFillPath(src, dst)
        return dst

    def joint(self, x, y, a1, l1, a2, l2):
        r1 = math.radians(a1); ex, ey = x + math.sin(r1) * l1, y + math.cos(r1) * l1
        r2 = math.radians(a1 + a2); hx, hy = ex + math.sin(r2) * l2, ey + math.cos(r2) * l2
        return (ex, ey), (hx, hy)

    # ------------------------------------------------------------ pose solver
    def pose(self, action, t, at):
        """Returns dict of angles/offsets. at = time since the action started (for anticipation/settle)."""
        ph = t * 2 * math.pi
        sd = self.seed * 6.28
        P = dict(legL=0, kneeL=2, legR=0, kneeR=2, armL=-6, elbL=8, armR=6, elbR=-8, lift=0, lean=0, hipx=0,
                 tilt=0, look=0, breathe=math.sin(t * 1.55 + sd), tie=0, seated=False, kneel=False, expr=None)
        # idle life: weight shift + follow-through in shoulders/head
        ws = math.sin(t * 0.55 + sd)
        P["hipx"] = 7 * ws
        P["lean"] = 1.2 * math.sin(t * 0.55 + sd - 0.5)
        P["tilt"] = 1.8 * math.sin(t * 0.37 + sd) + 0.8 * math.sin(t * 0.9 + sd)
        P["armL"] += 2.5 * math.sin(t * 0.55 + sd - 0.9); P["armR"] -= 2.5 * math.sin(t * 0.55 + sd - 1.1)
        P["legL"] = -2 * ws; P["legR"] = 2 * ws
        P["tie"] = 2 * math.sin(t * 0.55 + sd - 1.4)
        g = ease_back(clamp(at / 0.55))  # gesture in with overshoot (anticipation handled by a small counter-move)
        anti = math.sin(clamp(at / 0.18) * math.pi) * (1 - clamp(at / 0.18))
        if action in ("walk", "run"):
            sp = 1.55 if action == "walk" else 2.6
            p = t * sp * 2 * math.pi + sd
            amp = 1.0 if action == "walk" else 1.55
            for side, off in (("L", 0.0), ("R", math.pi)):
                q = p + off
                P["leg" + side] = 27 * amp * math.sin(q)
                P["knee" + side] = 4 + 46 * amp * max(0.0, math.cos(q - 0.35)) ** 1.6
            P["armL"] = -22 * amp * math.sin(p); P["elbL"] = 10 + 22 * max(0.0, -math.sin(p - 0.6)) * amp
            P["armR"] = 22 * amp * math.sin(p); P["elbR"] = 10 + 22 * max(0.0, math.sin(p - 0.6)) * amp
            P["lift"] = 9 * amp * (math.cos(2 * p) + 1) / 2
            P["lean"] = 3.5 * amp + 1.2 * math.sin(2 * p)
            P["tie"] = 7 * math.sin(2 * p - 0.8)
            P["hipx"] = 0
            P["tilt"] = -1.5 * math.sin(2 * p - 0.4)
        elif action == "sit":
            P.update(legL=86, kneeL=-86, legR=82, kneeR=-82, seated=True, armL=24, elbL=40, armR=28, elbR=44, hipx=0)
        elif action == "talk":
            P["armR"] = lerp(6, 28, g) + 9 * math.sin(t * 2.1); P["elbR"] = lerp(-8, 62, g) + 14 * math.sin(t * 2.7 + 1)
            P["armL"] = -6 + 4 * math.sin(t * 1.3)
        elif action == "point":
            P["armR"] = lerp(6, 92, g) - 12 * anti + 2 * math.sin(t * 0.8); P["elbR"] = lerp(-8, 6, g)
            P["lean"] += 3 * g
        elif action == "hold":
            P["armR"] = lerp(6, 38, g); P["elbR"] = lerp(-8, 64, g); P["armL"] = lerp(-6, 30, g); P["elbL"] = lerp(8, 70, g)
        elif action == "give":
            P["armR"] = lerp(6, 72, g) - 10 * anti + 3 * math.sin(t * 0.7); P["elbR"] = lerp(-8, 8, g)
            P["lean"] += 4 * g
        elif action == "carry":
            P["armR"] = 3; P["elbR"] = 0
        elif action == "shock":
            P["armL"] = lerp(-6, -58, g); P["elbL"] = lerp(8, -82, g)
            P["armR"] = lerp(6, 62, g) + 3 * math.sin(t * 6); P["elbR"] = lerp(-8, 84, g)
            P["lean"] = -6 * g; P["lift"] = 14 * math.sin(clamp(at / 0.35) * math.pi)
            P["expr"] = "shock"
        elif action == "lean":
            P["lean"] = lerp(0, 13, g); P["armR"] = lerp(6, 42, g); P["elbR"] = lerp(-8, 48, g); P["tilt"] += 4 * g
        elif action == "fall":
            P.update(armL=-128 + 10 * math.sin(t * 1.7), elbL=-24, armR=128 - 10 * math.sin(t * 1.7 + 0.5), elbR=24,
                     legL=-16 + 7 * math.sin(t * 2.1), kneeL=28, legR=16 - 7 * math.sin(t * 2.1 + 0.6), kneeR=26,
                     tie=22 * math.sin(t * 6), hipx=0)
        elif action == "hang":
            sw = math.sin(t * 1.1 + sd)
            P.update(armL=-163, elbL=4, armR=163, elbR=-4, legL=-6 + 7 * math.sin(t * 1.1 - 0.9),
                     legR=6 + 7 * math.sin(t * 1.1 - 1.3), kneeL=8 + 4 * sw, kneeR=10 - 4 * sw,
                     tie=10 * math.sin(t * 1.1 - 1.6), hipx=0, lean=0)
        elif action == "dig":
            d = math.sin(t * 2.3 + sd)
            P.update(armR=48 + 32 * d, elbR=38, armL=40 + 30 * d, elbL=52, lean=16 + 9 * d, hipx=0)
        elif action == "salute":
            P["armR"] = lerp(6, 150, g); P["elbR"] = lerp(-8, 102, g)
        elif action == "fight":
            d = math.sin(t * 4.4)
            P.update(armR=82 + 26 * d, elbR=30, armL=62 - 20 * d, elbL=82, legL=-16, legR=22)
        elif action == "kneel":
            P.update(legL=86, kneeL=-86, legR=-6, kneeR=92, kneel=True, hipx=0)
        elif action == "turn":
            pass
        return P

    # ------------------------------------------------------------ draw
    def draw(self, c, x, y, scale, t, action="stand", face=1.0, expr="neutral", props=None, talk=False, rot=0.0,
             light=None, at=None):
        self.L = light or DEFAULT_LIGHT
        sc = scale * self.hscale
        at = t if at is None else at
        P = self.pose(action, t, at)
        expr = P["expr"] or expr
        fsign = 1 if face >= 0 else -1
        self.ldx = self.L["dx"] * fsign  # light direction in local (flipped) space
        c.save()
        c.translate(x, y)
        if rot:
            c.rotate(rot)
        # contact shadow on the ground
        if not action in ("hang", "fall"):
            sh = skia.Paint(AntiAlias=True)
            sh.setShader(skia.GradientShader.MakeRadial(skia.Point(0, 0), 150 * sc, [hexcol("#000000", 110), hexcol("#000000", 0)]))
            c.save(); c.scale(1.0, 0.18); c.drawCircle(0, 0, 150 * sc, sh); c.restore()
        c.scale(sc * max(0.08, abs(face)) * fsign, sc)
        bw = self.bw
        hip_y = HIP_Y + (150 if P["seated"] else 0) + (130 if P["kneel"] else 0) - P["lift"]
        sh_y = hip_y + (SH_Y - HIP_Y) + P["breathe"] * 2.2
        c.translate(P["hipx"], 0)
        # torso pivot (lean) at hips
        c.save()
        c.translate(0, hip_y); c.rotate(P["lean"]); c.translate(0, -hip_y)
        head_y = sh_y + (HEAD_Y - SH_Y)
        if self.style in ("long", "bob", "afro", "ponytail"):
            c.save(); c.translate(0, head_y); c.rotate(P["tilt"]); self.back_hair(c, t); c.restore()
        # back arm
        self.arm(c, -1, sh_y, P["armL"], P["elbL"], t)
        c.restore()
        # legs (not leaned)
        self.legs(c, hip_y, P)
        c.save()
        c.translate(0, hip_y); c.rotate(P["lean"]); c.translate(0, -hip_y)
        self.torso(c, sh_y, hip_y, P, t)
        # neck + head
        neck = skia.Path(); neck.addRoundRect(rect(-21, sh_y - 62, 42, 72), 12, 12)
        self.part(c, neck, shade(self.skin, 0.86), rim=False)
        if self.outfit in ("suit", "raincoat", "coat", "uniform"):
            self.collar(c, sh_y)
        c.save(); c.translate(0, head_y); c.rotate(P["tilt"])
        self.head(c, t, expr, talk)
        c.restore()
        hand = self.arm(c, 1, sh_y, P["armR"], P["elbR"], t)
        c.restore()
        c.restore()
        # world hand position (approximate, used for held props)
        r = math.radians(P["lean"])
        hx, hy = hand
        hx, hy = hx * math.cos(r) - (hy - hip_y) * math.sin(r), hx * math.sin(r) + (hy - hip_y) * math.cos(r) + hip_y
        return {"hand": (hx + P["hipx"], hy), "sc": sc}

    def arm(self, c, side, sh_y, a1, a2, t):
        x = side * 80 * self.bw
        y = sh_y + 16
        (ex, ey), (hx, hy) = self.joint(x, y, a1, UPPER, a2, FORE)
        sleeve = self.oc if self.outfit not in ("tshirt", "kid") else self.shirt
        w = 44 * self.bw
        if self.outfit in ("tshirt", "kid"):
            up = self.seg_path([(x, y), (lerp(x, ex, 0.45), lerp(y, ey, 0.45))], w)
            skin_arm = self.seg_path([(lerp(x, ex, 0.4), lerp(y, ey, 0.4)), (ex, ey), (hx, hy)], w * 0.78)
            self.part(c, skin_arm, self.skin)
            self.part(c, up, sleeve)
        else:
            arm = self.seg_path([(x, y), (ex, ey), (hx, hy)], w)
            self.part(c, arm, sleeve)
            # shirt cuff
            if self.outfit in ("suit", "raincoat", "coat"):
                ux, uy = hx - ex, hy - ey; n = math.hypot(ux, uy) or 1
                cx_, cy_ = hx - ux / n * 22, hy - uy / n * 22
                c.drawPath(self.seg_path([(cx_, cy_), (hx - ux / n * 10, hy - uy / n * 10)], w * 0.72), fill(self.shirt))
        hand = skia.Path(); hand.addOval(rect(hx - 17, hy - 15, 34, 36))
        self.part(c, hand, self.skin, rim=False)
        return (hx, hy)

    def legs(self, c, hip_y, P):
        bw = self.bw
        skin_leg = self.outfit in ("stewardess", "dress")
        for side, la, ka in ((-1, P["legL"], P["kneeL"]), (1, P["legR"], P["kneeR"])):
            x = side * 36 * bw
            (kx, ky), (fx, fy) = self.joint(x, hip_y, la, THIGH, ka, SHIN)
            col = self.skin if skin_leg else (self.pants if self.outfit != "kid" else self.skin)
            w = 54 * bw
            if self.outfit == "kid":
                shorts = self.seg_path([(x, hip_y), (lerp(x, kx, 0.55), lerp(hip_y, ky, 0.55))], w * 1.05)
                legp = self.seg_path([(lerp(x, kx, 0.5), lerp(hip_y, ky, 0.5)), (kx, ky), (fx, fy)], w * 0.72)
                self.part(c, legp, self.skin)
                self.part(c, shorts, self.pants)
            else:
                legp = self.seg_path([(x, hip_y), (kx, ky), (fx, fy)], w if not skin_leg else w * 0.74)
                self.part(c, legp, col)
            # shoe
            shoe = skia.Path(); shoe.addRoundRect(rect(fx - 24, fy - 18, 70, 30), 14, 14)
            self.part(c, shoe, self.s.get("shoe_color", "#141113"), rim=True)
            c.drawLine(fx - 10, fy - 12, fx + 30, fy - 12, stroke("#ffffff", 2.5, 60))

    def collar(self, c, sh_y):
        c.drawPath(poly([(-30, sh_y - 22), (0, sh_y + 30), (30, sh_y - 22), (22, sh_y - 36), (0, sh_y + 4), (-22, sh_y - 36)]), fill(self.shirt))

    def torso(self, c, sh_y, hip_y, P, t):
        o = self.outfit
        bw = self.bw
        tw = 172 * bw
        bottom = hip_y + 34
        if o in ("raincoat", "coat", "lab"):
            bottom = hip_y + 250
        elif o == "robe":
            bottom = hip_y + 440
        elif o == "dress":
            bottom = hip_y + 200
        elif o == "stewardess":
            bottom = hip_y + 150
        flare = 1.18 if o in ("raincoat", "coat", "lab", "robe", "dress") else 0.9
        waist = 0.74 if not self.female else 0.66
        p = skia.Path()
        p.moveTo(-tw / 2 + 6, sh_y + 4)
        p.cubicTo(-tw / 2 - 10, sh_y - 22, -tw / 2 + 20, sh_y - 34, -tw / 2 + 44, sh_y - 34)
        p.lineTo(tw / 2 - 44, sh_y - 34)
        p.cubicTo(tw / 2 - 20, sh_y - 34, tw / 2 + 10, sh_y - 22, tw / 2 - 6, sh_y + 4)
        p.cubicTo(tw / 2 - 10, sh_y + 120, tw * waist / 2, hip_y - 80, tw * flare / 2, bottom)
        p.lineTo(-tw * flare / 2, bottom)
        p.cubicTo(-tw * waist / 2, hip_y - 80, -tw / 2 + 10, sh_y + 120, -tw / 2 + 6, sh_y + 4)
        p.close()
        body = self.shirt if o in ("tshirt", "kid") else self.oc
        if o in ("stewardess", "dress"):
            sk = skia.Path(); sk.moveTo(-tw * 0.4, hip_y - 10); sk.lineTo(tw * 0.4, hip_y - 10)
            sk.lineTo(tw * 0.5, bottom); sk.lineTo(-tw * 0.5, bottom); sk.close()
            self.part(c, sk, self.s.get("skirt_color", body))
        self.part(c, p, body)
        if o in ("suit", "raincoat", "coat"):
            v = poly([(-30, sh_y - 30), (30, sh_y - 30), (0, sh_y + 150)])
            c.drawPath(v, fill(self.shirt))
            c.save(); c.clipPath(v, doAntiAlias=True); c.drawRect(rect(0 if self.ldx < 0 else -40, sh_y - 40, 40, 200), fill("#000000", 40)); c.restore()
            if self.tie != "none":
                sw = P["tie"]
                c.save(); c.translate(0, sh_y - 18); c.rotate(sw)
                tie = poly([(-10, 0), (10, 0), (7, 16), (15, 128), (0, 148), (-15, 128), (-7, 16)])
                self.part(c, tie, self.tie, rim=False)
                c.drawLine(-3, 30, -6, 120, stroke("#ffffff", 2, 40))
                c.restore()
            lap = shade(body, 0.78)
            lp = poly([(-32, sh_y - 34), (-4, sh_y + 152), (-56, sh_y + 72), (-48, sh_y + 20)])
            rp = poly([(32, sh_y - 34), (4, sh_y + 152), (56, sh_y + 72), (48, sh_y + 20)])
            for q in (lp, rp):
                self.part(c, q, lap, shadow=False, rim=False)
            # pocket square + buttons
            c.drawPath(poly([(tw * 0.18, sh_y + 92), (tw * 0.34, sh_y + 92), (tw * 0.3, sh_y + 104), (tw * 0.2, sh_y + 104)]),
                       fill(self.s.get("pocket", shade(body, 1.25)), 120))
            for by in (sh_y + 186, sh_y + 236):
                c.drawCircle(4, by, 5, fill("#0b0a0c")); c.drawCircle(3, by - 1.5, 1.6, fill("#ffffff", 70))
            if o == "raincoat":
                c.drawRect(rect(-tw * 0.4, hip_y - 26, tw * 0.8, 20), fill(shade(body, 0.72)))
        elif o == "uniform":
            c.drawLine(0, sh_y - 30, 0, bottom, stroke(shade(body, 0.68), 4))
            for by in range(int(sh_y + 10), int(bottom - 20), 52):
                c.drawCircle(0, by, 6, fill("#c9a443"))
            c.drawRect(rect(-tw * 0.38, hip_y - 30, tw * 0.76, 24), fill("#3b2a1a"))
            c.drawRect(rect(-15, hip_y - 32, 30, 28), fill("#c9a443"))
            for px in (-tw / 4, tw / 4):
                c.drawRect(rect(px - 24, sh_y + 30, 48, 40), stroke(shade(body, 0.66), 3))
            if self.s.get("medals"):
                for i in range(3):
                    c.drawRect(rect(-tw / 4 - 24 + i * 16, sh_y + 2, 13, 20), fill(["#a8322a", "#2e6aa1", "#c9a443"][i]))
        elif o == "stewardess":
            c.drawPath(poly([(-24, sh_y - 30), (24, sh_y - 30), (0, sh_y + 60)]), fill(self.shirt))
            sc_ = self.s.get("scarf_color", "#a8322a")
            c.drawPath(poly([(-18, sh_y - 8), (18, sh_y - 8), (32, sh_y + 30), (0, sh_y + 20), (-32, sh_y + 30)]), fill(sc_))
            for by in (sh_y + 120, sh_y + 176):
                c.drawCircle(0, by, 5, fill("#c9a443"))
        elif o in ("tshirt", "kid"):
            c.drawPath(poly([(-26, sh_y - 32), (26, sh_y - 32), (0, sh_y - 6)]), fill(shade(body, 0.7)))
            if self.s.get("stripe"):
                c.drawRect(rect(-tw / 2 + 8, sh_y + 80, tw - 16, 24), fill(self.s["stripe"]))
        elif o == "prison":
            c.drawPath(poly([(-26, sh_y - 32), (26, sh_y - 32), (0, sh_y + 30)]), fill(shade(body, 0.7)))
        elif o == "armor":
            for i in range(4):
                c.drawLine(-tw / 2 + 12, sh_y + 40 + i * 58, tw / 2 - 12, sh_y + 40 + i * 58, stroke(shade(body, 0.66), 4))
        elif o == "robe":
            c.drawLine(-10, sh_y - 30, 34, bottom, stroke(shade(body, 0.68), 5))
            c.drawRect(rect(-tw * 0.45, hip_y - 36, tw * 0.9, 22), fill(self.s.get("sash_color", "#c9a443")))
        elif o == "lab":
            c.drawPath(poly([(-28, sh_y - 30), (28, sh_y - 30), (0, sh_y + 120)]), fill(self.shirt))
        if self.s.get("badge"):
            c.drawCircle(-tw / 4, sh_y + 70, 14, fill("#c9a443"))

    # ------------------------------------------------------------ head
    def head(self, c, t, expr, talk):
        s = self.s
        sk = self.skin
        fx = 11
        # ear (back side)
        ear = skia.Path(); ear.addOval(rect(-50, -18, 20, 36))
        self.part(c, ear, shade(sk, 0.92), rim=False)
        jaw_w = 0.86 if not self.female else 0.78
        hp = skia.Path()
        hp.moveTo(-46, -10)
        hp.cubicTo(-48, -78, 46, -80, 46, -10)               # cranium
        hp.cubicTo(47, 22, 40 * jaw_w + fx * 0.4, 50, fx + 10, 62)  # jaw front
        hp.cubicTo(fx - 4, 68, -26, 56, -40 * jaw_w, 30)
        hp.cubicTo(-46, 16, -46, 4, -46, -10)
        hp.close()
        self.part(c, hp, sk)
        age = float(s.get("age", 35))
        fh = s.get("facial_hair", "none")
        hc = self.hair if s.get("beard_color") is None else hair_col(s.get("beard_color"))
        if fh in ("beard", "full_beard"):
            b = skia.Path(); b.moveTo(-42, 4); b.cubicTo(-40, 60, fx, 74, fx + 12, 64); b.cubicTo(40, 56, 46, 20, 46, 0)
            b.lineTo(34, 18); b.cubicTo(20, 40, -20, 40, -34, 18); b.close()
            self.part(c, b, hc, rim=False)
        elif fh == "stubble":
            b = skia.Path(); b.moveTo(-38, 14); b.cubicTo(-34, 56, fx, 66, fx + 10, 60); b.cubicTo(38, 50, 44, 18, 44, 10)
            b.cubicTo(20, 38, -10, 38, -38, 14); b.close()
            c.drawPath(b, fill(hc, 60))
        elif fh == "goatee":
            c.drawOval(rect(fx - 6, 44, 30, 22), fill(hc))
        # eyes (almond, 3/4)
        blink_p = 3.9 + self.seed * 1.4
        bt = (t + self.seed * 3) % blink_p
        o = 1.0 - math.sin(clamp((bt - (blink_p - 0.2)) / 0.2) * math.pi)
        wide = 1.35 if expr == "shock" else 1.0
        look = 2 * math.sin(t * 0.42 + self.seed * 7)
        g = s.get("glasses", "none")
        for i, ex in enumerate((-12 + fx, 20 + fx)):
            w_ = 15 if i == 0 else 17
            hgt = 8.5 * wide * clamp(o, 0.06, 1.0)
            eye = skia.Path(); eye.moveTo(ex - w_ / 2, -14); eye.quadTo(ex, -14 - hgt * 1.3, ex + w_ / 2, -14)
            eye.quadTo(ex, -14 + hgt * 0.9, ex - w_ / 2, -14); eye.close()
            if g != "sunglasses":
                c.drawPath(eye, fill("#f4efe6"))
                if o > 0.3:
                    c.save(); c.clipPath(eye, doAntiAlias=True)
                    c.drawCircle(ex + 2 + look, -14, 5.2, fill(s.get("eyes", "#3a2616")))
                    c.drawCircle(ex + 2 + look, -14, 2.4, fill("#0a0806"))
                    c.drawCircle(ex + look, -16, 1.4, fill("#ffffff", 220))
                    c.restore()
                c.drawPath(eye, stroke(shade(sk, 0.45), 2.2))
                c.drawLine(ex - w_ / 2 - 1, -14 - hgt * 0.65, ex + w_ / 2, -15 - hgt * 0.7, stroke(shade(sk, 0.4), 2.4))
        # brows
        bc = shade(self.hair, 0.85) if s.get("hair") not in ("grey", "white") else (140, 135, 128)
        bt_ = {"angry": 7, "sad": -6, "shock": -3, "serious": 3}.get(expr, 0)
        by = -30 - (4 if expr == "shock" else 0)
        c.drawPath(self.seg_path([(-22 + fx, by + bt_ * -0.4), (-4 + fx, by + bt_ * 0.5)], 5.5), fill(bc))
        c.drawPath(self.seg_path([(10 + fx, by + bt_ * 0.5), (30 + fx, by + bt_ * -0.4)], 5.5), fill(bc))
        if g in ("sunglasses", "glasses"):
            lens = []
            for i, ex in enumerate((-12 + fx, 20 + fx)):
                w_ = 26 if i == 0 else 29
                lp = skia.Path(); lp.moveTo(ex - w_ / 2, -24); lp.lineTo(ex + w_ / 2, -24)
                lp.quadTo(ex + w_ / 2 + 1, -2, ex, -3); lp.quadTo(ex - w_ / 2 - 1, -3, ex - w_ / 2, -24); lp.close()
                lens.append(lp)
            for lp in lens:
                if g == "sunglasses":
                    gp = skia.Paint(AntiAlias=True)
                    b = lp.computeTightBounds()
                    gp.setShader(skia.GradientShader.MakeLinear([skia.Point(0, b.top()), skia.Point(0, b.bottom())],
                                                                [hexcol("#1b1d24"), hexcol("#050506")]))
                    c.drawPath(lp, gp)
                    # moving glint
                    c.save(); c.clipPath(lp, doAntiAlias=True)
                    gx = ((t * 0.35 + self.seed) % 2.2) * 90 - 60
                    c.drawPath(poly([(gx + b.left(), b.top()), (gx + b.left() + 8, b.top()), (gx + b.left() - 10, b.bottom()), (gx + b.left() - 18, b.bottom())]), fill("#ffffff", 70))
                    c.drawLine(b.left() + 4, b.top() + 5, b.left() + 12, b.top() + 3, stroke(self.L["rim"], 2.5, 150))
                    c.restore()
                c.drawPath(lp, stroke("#0a0a0c", 3))
            c.drawLine(1 + fx, -21, 6 + fx, -21, stroke("#0a0a0c", 3.5))
            c.drawLine(-25 + fx, -21, -44, -16, stroke("#0a0a0c", 3.5))
        # nose: wedge + shadow on shadow side
        nose = skia.Path(); nose.moveTo(fx + 8, -14); nose.cubicTo(fx + 14, 4, fx + 20, 12, fx + 12, 18)
        nose.cubicTo(fx + 8, 20, fx + 2, 18, fx, 14)
        c.drawPath(nose, stroke(shade(sk, 0.62), 2.6))
        c.drawPath(nose, fill(shade(sk, 0.82), 120))
        # mustache
        if fh in ("mustache", "beard", "full_beard"):
            m = skia.Path(); m.moveTo(fx - 12, 32); m.cubicTo(fx - 2, 22, fx + 18, 22, fx + 28, 32); m.cubicTo(fx + 10, 28, fx, 28, fx - 12, 32)
            c.drawPath(m, stroke(hc, 7))
        # mouth
        mx = fx + 8
        if talk:
            op = 2 + 7 * abs(math.sin(t * 8.6)) * (0.6 + 0.4 * abs(math.sin(t * 2.9)))
            c.drawOval(rect(mx - 10, 37 - op / 2, 20, op + 3), fill("#4a1c1c"))
        elif expr in ("smile", "happy"):
            m = skia.Path(); m.moveTo(mx - 13, 36); m.quadTo(mx, 45, mx + 13, 35)
            c.drawPath(m, stroke(shade(sk, 0.42), 3.2))
        elif expr in ("sad", "angry", "serious"):
            m = skia.Path(); m.moveTo(mx - 12, 41); m.quadTo(mx, 36, mx + 12, 41)
            c.drawPath(m, stroke(shade(sk, 0.42), 3.2))
        elif expr == "shock":
            c.drawOval(rect(mx - 7, 34, 14, 17), fill("#4a1c1c"))
        else:
            c.drawLine(mx - 11, 39, mx + 11, 38, stroke(shade(sk, 0.42), 3.2))
        c.drawLine(mx - 7, 47, mx + 6, 47, stroke(shade(sk, 0.72), 2.2, 160))  # lower lip shade
        if age >= 50:
            for i in range(2):
                c.drawLine(-14 + fx, -46 + i * 7, 22 + fx, -46 + i * 7, stroke(shade(sk, 0.74), 1.8))
            c.drawLine(fx + 26, 18, fx + 30, 34, stroke(shade(sk, 0.74), 1.8))
        self.front_hair(c, t)
        c.save(); c.scale(0.7, 0.7); c.translate(0, -8)
        self.hat(c)
        c.restore()

    def back_hair(self, c, t):
        hc = self.hair
        sway = 3 * math.sin(t * 1.2 + self.seed * 5)
        if self.style == "long":
            p = skia.Path(); p.moveTo(-48, -30); p.cubicTo(-62 + sway, 60, -56 + sway, 120, -48 + sway, 150)
            p.lineTo(50 + sway, 150); p.cubicTo(58, 100, 60, 40, 48, -30); p.close()
            self.part(c, p, hc, rim=True)
        elif self.style == "bob":
            p = skia.Path(); p.addRoundRect(rect(-58, -64, 116, 122), 46, 46)
            self.part(c, p, hc)
        elif self.style == "afro":
            p = skia.Path(); p.addCircle(0, -30, 80); self.part(c, p, hc)
        elif self.style == "ponytail":
            p = skia.Path(); p.moveTo(-30, -36); p.cubicTo(-84 + sway, 10, -70 + sway, 80, -52 + sway, 110)
            p.cubicTo(-40, 40, -24, 0, -14, -28); p.close()
            self.part(c, p, hc)

    def front_hair(self, c, t):
        st, hc = self.style, self.hair
        if st in ("bald", "none"):
            return
        p = skia.Path()
        if st == "side_part":
            p.moveTo(-47, 0); p.cubicTo(-56, -66, -20, -86, 8, -84); p.cubicTo(44, -84, 56, -56, 48, -6)
            p.cubicTo(44, -34, 34, -48, 18, -52); p.cubicTo(0, -58, -14, -52, -22, -44)
            p.cubicTo(-30, -36, -40, -22, -47, 0); p.close()
        elif st == "receding":
            for sgn in (-1, 1):
                q = skia.Path(); q.moveTo(sgn * 47, 4); q.cubicTo(sgn * 50, -46, sgn * 34, -62, sgn * 22, -64)
                q.lineTo(sgn * 24, -44); q.cubicTo(sgn * 36, -30, sgn * 40, -12, sgn * 40, 4); q.close()
                self.part(c, q, hc, rim=False)
            return
        elif st in ("short", "buzz"):
            p.moveTo(-47, -2); p.cubicTo(-52, -76, 50, -80, 47, -2); p.cubicTo(40, -40, 20, -50, 0, -50)
            p.cubicTo(-20, -50, -40, -40, -47, -2); p.close()
        elif st == "pompadour":
            p.moveTo(-47, -2); p.cubicTo(-56, -94, 34, -112, 54, -50); p.cubicTo(50, -30, 46, -20, 47, -2)
            p.cubicTo(36, -46, 0, -54, -47, -2); p.close()
        elif st in ("long", "bob", "ponytail"):
            p.moveTo(-50, 24); p.cubicTo(-58, -76, 40, -88, 50, -10); p.cubicTo(52, 10, 50, 24, 50, 30)
            p.cubicTo(42, -10, 26, -40, 8, -48); p.cubicTo(-14, -34, -34, -32, -40, -26); p.cubicTo(-44, -6, -48, 10, -50, 24); p.close()
        elif st == "bun":
            b = skia.Path(); b.addCircle(-14, -78, 22); self.part(c, b, hc)
            p.moveTo(-47, -2); p.cubicTo(-52, -76, 50, -80, 47, -2); p.cubicTo(40, -44, 20, -54, 0, -54)
            p.cubicTo(-20, -54, -40, -44, -47, -2); p.close()
        elif st == "curly":
            for i in range(10):
                a = math.pi + i * math.pi / 9
                q = skia.Path(); q.addCircle(math.cos(a) * 44, -20 + math.sin(a) * 56, 15)
                self.part(c, q, hc, outline=False)
            return
        elif st == "afro":
            return
        elif st == "kid_messy":
            p.moveTo(-47, -2)
            for i in range(7):
                xx = -47 + i * 15.5
                p.lineTo(xx + 8, -80 + (i % 2) * 12 + 2 * math.sin(t * 2 + i)); p.lineTo(xx + 15.5, -62)
            p.lineTo(47, -2); p.cubicTo(40, -42, 20, -50, 0, -50); p.cubicTo(-20, -50, -40, -42, -47, -2); p.close()
        else:
            p.moveTo(-47, -2); p.cubicTo(-52, -76, 50, -80, 47, -2); p.cubicTo(40, -40, 20, -50, 0, -50)
            p.cubicTo(-20, -50, -40, -40, -47, -2); p.close()
        self.part(c, p, hc)
        # sheen
        sh = skia.Path(); sh.moveTo(-18, -66); sh.quadTo(6, -76, 28, -64)
        c.drawPath(sh, stroke(shade(hc, 1.6), 3, 90))
        if st == "side_part":
            c.drawLine(-22, -46, -10, -78, stroke(shade(hc, 0.6), 2.2))

    def hat(self, c):
        hat = self.s.get("hat", "none")
        hc = self.s.get("hat_color", "#2a2622")
        P = lambda pth, col: self.part(c, pth, col)
        if hat == "fedora":
            b = skia.Path(); b.addRoundRect(rect(-100, -82, 200, 20), 10, 10); P(b, hc)
            k = skia.Path(); k.moveTo(-60, -72); k.cubicTo(-66, -150, 66, -152, 60, -72); k.close(); P(k, hc)
            c.drawRect(rect(-60, -92, 120, 13), fill("#0d0d0d"))
        elif hat == "cap":
            k = skia.Path(); k.moveTo(-68, -40); k.cubicTo(-66, -122, 66, -122, 68, -40); k.close(); P(k, hc)
            v = skia.Path(); v.addRoundRect(rect(20, -50, 92, 18), 9, 9); P(v, shade(hc, 0.8))
        elif hat == "military":
            k = skia.Path(); k.addRoundRect(rect(-74, -102, 148, 52), 16, 16); P(k, hc)
            c.drawRoundRect(rect(-40, -58, 132, 16), 8, 8, fill("#0d0d0d")); c.drawCircle(0, -78, 10, fill("#c9a443"))
        elif hat == "helmet":
            k = skia.Path(); k.moveTo(-86, -30); k.cubicTo(-86, -134, 86, -134, 86, -30); k.close(); P(k, hc)
        elif hat == "pillbox":
            k = skia.Path(); k.addRoundRect(rect(-36, -122, 72, 36), 10, 10); P(k, hc)
        elif hat == "crown":
            k = poly([(-56, -78), (-56, -138), (-30, -104), (0, -146), (30, -104), (56, -138), (56, -78)]); P(k, "#d4a32a")
            for xx in (-28, 0, 28):
                c.drawCircle(xx, -90, 6, fill("#a8322a"))
        elif hat == "tophat":
            b = skia.Path(); b.addRoundRect(rect(-92, -84, 184, 18), 9, 9); P(b, "#111111")
            k = skia.Path(); k.addRect(rect(-56, -192, 112, 112)); P(k, "#111111")
        elif hat == "beret":
            k = skia.Path(); k.addOval(rect(-80, -124, 150, 60)); P(k, hc)
