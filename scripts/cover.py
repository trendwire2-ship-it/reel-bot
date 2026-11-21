#!/usr/bin/env python3
"""Make a click-worthy cover (thumbnail) for a story: key character close-up from the reel's own art,
cinematic grade, and a big bold hook title. Usage: python3 scripts/cover.py story.json cover.jpg"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("REEL_FPS", "30")
import render as R  # noqa
from engine import W, H, hexcol, fill, stroke, rect, font, FONT_BIG, FONT_TYPE, fit, text_w  # noqa
import skia, numpy as np

def pick_scene(story):
    cv = story.get("cover", {})
    if "scene" in cv:
        return int(cv["scene"])
    best, score = 0, -1
    for i, s in enumerate(story["scenes"]):
        for ca in s.get("cast", []):
            sc = ca.get("scale", 1.0)
            sc = max(sc) if isinstance(sc, list) else sc
            sc += 0.6 if ca.get("expr") in ("serious", "shock") else 0
            if sc > score:
                best, score = i, sc
    return best

def draw_comic_bg(story, c):
    """Painted key art: cover.image, else the first key shot, else the first shot."""
    import comic, cv2
    shots = story["comic"]["shots"]
    url = story.get("cover", {}).get("image") or next((x["image"] for x in shots if x.get("key")), shots[0]["image"])
    img = comic.cover_resize(cv2.imread(comic.fetch(url)))
    bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    c.drawImage(skia.Image.fromarray(np.ascontiguousarray(bgra), colorType=skia.kBGRA_8888_ColorType), 0, 0)

def make_cover(story, out):
    # estimated timeline (no audio needed)
    t, scenes = 0.15, []
    for s in story["scenes"]:
        d = len(s["say"].split()) / 2.7 + 0.2
        scenes.append({"s": t, "e": t + d}); t += d + 0.22
    si = pick_scene(story)
    s = scenes[si]
    lt = story.get("cover", {}).get("t", (s["e"] - s["s"]) * 0.6)
    st = None if story.get("comic") else R.Stage(story)
    info = skia.ImageInfo.Make(W, H, skia.kBGRA_8888_ColorType, skia.kPremul_AlphaType)
    surf = skia.Surface.MakeRaster(info); c = surf.getCanvas()
    c.clear(hexcol("#000000"))
    sc = story["scenes"][si]
    cam = None
    cast = sorted(sc.get("cast", []), key=lambda ca: -(max(ca["scale"]) if isinstance(ca.get("scale"), list) else ca.get("scale", 1.0)))
    focus = story.get("cover", {}).get("focus")
    ca = next((x for x in cast if x["id"] == focus), cast[0] if cast else None)
    if ca is not None and st is not None:
        p = min(1.0, lt / max(0.1, s["e"] - s["s"]))
        sca = R.val(ca.get("scale"), p, 1.0)
        hs = st.cast[ca["id"]].hscale if ca["id"] in st.cast else 1.0
        x = R.val(ca.get("x"), p, 0.5) * W
        y = R.val(ca.get("y"), p, 0.86) * H
        face_y = y - 0.62 * sca * hs * 900
        z = max(1.0, min(2.8, 2.3 / max(sca, 0.4)))
        cam = {"zoom": z, "pan": x - W / 2, "pany": face_y - H / 2 - 0.16 * H / z}
    if story.get("comic"):
        draw_comic_bg(story, c)
    else:
        wd = st.draw_scene(c, si, lt, s["e"] - s["s"], cam_override=cam, overlays=False)
        R.Post().apply(surf, c, 0, wd.get("bloom", 0.3), wd.get("grade"))
    c.drawRect(rect(0, 0, W, H), R.vignette_paint())
    # readability gradients
    for y0, y1, a0, a1 in ((0, 980, 235, 0), (H - 520, H, 0, 220)):
        p = skia.Paint(AntiAlias=True)
        p.setShader(skia.GradientShader.MakeLinear([skia.Point(0, y0), skia.Point(0, y1)], [hexcol("#000000", a0), hexcol("#000000", a1)]))
        c.drawRect(rect(0, y0, W, y1 - y0), p)
    title = (story.get("cover", {}).get("title") or story.get("hook") or story["title"]).upper()
    words = title.split()
    lines, cur = [], ""
    f = font(FONT_BIG, 170)
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and text_w(trial, f) > W - 120:
            lines.append(cur); cur = w
        else:
            cur = trial
    lines.append(cur)
    size = 170 if len(lines) <= 3 else 130
    f = font(FONT_BIG, size)
    y = H * 0.27 - (len(lines) - 1) * size * 0.35
    hl = len(lines) - 1  # last line highlighted
    y_start = y
    for i, ln in enumerate(lines):
        fl = fit(ln, FONT_BIG, W - 110, size)
        w = text_w(ln, fl)
        x = W / 2 - w / 2
        if i == hl:
            c.save(); c.translate(W / 2, y - size * 0.32); c.rotate(-2)
            c.drawRect(rect(-w / 2 - 30, -size * 0.62, w + 60, size * 1.08), fill("#c0302a"))
            c.restore()
        sh = skia.Paint(AntiAlias=True, Color=hexcol("#000000", 200)); sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 14))
        c.drawString(ln, x + 6, y + 10, fl, sh)
        c.drawString(ln, x, y, fl, stroke("#000000", 12))
        c.drawString(ln, x, y, fl, fill("#ffffff" if i == hl else "#ffd21f"))
        y += size * 1.0
    # top tag + brand
    tag = story.get("cover", {}).get("tag", "TRUE STORY")
    ft = font(FONT_BIG, 60); tw = text_w(tag, ft)
    ty = y_start - size * 0.85 - 120
    c.drawRoundRect(rect(W / 2 - tw / 2 - 34, ty, tw + 68, 96), 48, 48, fill("#0b0b0d", 220))
    c.drawRoundRect(rect(W / 2 - tw / 2 - 34, ty, tw + 68, 96), 48, 48, stroke("#ffd21f", 4))
    c.drawString(tag, W / 2 - tw / 2, ty + 70, ft, fill("#ffd21f"))
    fb = font(FONT_TYPE, 44); bt = "FACTS ON FACTS"
    c.drawString(bt, W / 2 - text_w(bt, fb) / 2, H - 150, fb, fill("#f3efe6", 230))
    buf = np.empty((H, W, 4), np.uint8); surf.readPixels(info, buf, W * 4)
    from PIL import Image
    Image.fromarray(buf[:, :, [2, 1, 0]]).save(out, quality=92)
    return out

if __name__ == "__main__":
    make_cover(json.load(open(sys.argv[1])), sys.argv[2])
    print("cover:", sys.argv[2])
