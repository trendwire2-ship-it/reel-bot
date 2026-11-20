#!/usr/bin/env python3
"""Check story JSON files before they enter the queue: structure, length, facts fields, and a test render of
frames from every scene (no voice needed). Usage: python3 scripts/validate.py queue/*.json [--sheet out.png]"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("REEL_FPS", "30")
import render as R  # noqa
import skia, numpy as np

ACTIONS = {"stand", "walk", "run", "talk", "point", "hold", "give", "carry", "shock", "lean", "fall", "hang", "dig",
           "salute", "fight", "kneel", "sit", "turn"}
PROPS = {"briefcase", "note", "money", "moneybag", "parachute", "shovel", "newspaper", "poster", "plane_side", "bills",
         "stamp", "file", "gun", "sword", "fire", "phone_booth", "raft", "submarine", "dummy_head"}
TRANS = {"whip_left", "whip_right", "push", "fog", "flash", "dissolve", "zoom", "push_left", "push_right"}

def check(path, sheet=None):
    errs, warns = [], []
    try:
        d = json.load(open(path))
    except Exception as e:
        return [f"not valid JSON: {e}"], []
    for k in ("id", "title", "caption", "hook", "scenes", "cast", "sources"):
        if k not in d:
            errs.append(f"missing '{k}'")
    if errs:
        return errs, warns
    words = sum(len(s["say"].split()) for s in d["scenes"])
    if not 200 <= words <= 245:
        errs.append(f"{words} spoken words (need 215-235)")
    if not 9 <= len(d["scenes"]) <= 16:
        errs.append(f"{len(d['scenes'])} scenes (need 10-15)")
    if len(d.get("sources", [])) < 2:
        errs.append("needs at least 2 source URLs")
    tags = d.get("hashtags", [])
    if not 5 <= len(tags) <= 8 or not all(isinstance(x, str) and x.startswith("#") and " " not in x for x in tags):
        errs.append("needs 'hashtags': 5-8 tags like \"#TrueCrime\" (mix broad + topic-specific)")
    if "?" not in d["caption"] or "#" in d["caption"]:
        errs.append("caption must end on a question and contain no hashtags (put them in 'hashtags')")
    if d.get("style", "sketch") == "sketch":
        nb = 0
        for i, s in enumerate(d["scenes"]):
            bts = s.get("beats")
            nw = len(s["say"].split())
            if not bts:
                errs.append(f"scene {i}: needs 'beats' (sketch style: a hand-lettered title per shot)")
                continue
            last = -1
            for b in bts:
                if not b.get("title") or len(b["title"].split()) > 5:
                    errs.append(f"scene {i}: beat title must be 1-5 words ({b.get('title')!r})")
                w = int(b.get("word", 0))
                if w <= last or w >= nw:
                    errs.append(f"scene {i}: beat word index {w} must increase and be < {nw}")
                last = w
                if b.get("frame", "medium") not in ("wide", "medium", "close"):
                    errs.append(f"scene {i}: frame must be wide|medium|close")
            nb += len(bts)
        tot = sum(len(s["say"].split()) for s in d["scenes"]) / 2.7
        if nb and tot / nb > 3.6:
            warns.append(f"only {nb} shots for ~{tot:.0f}s: aim for a new shot every 1.5-3 s")
    if sum(1 for s in d["scenes"] if s.get("hook")) < 3:
        warns.append("fewer than 3 re-hook banners")
    for i, s in enumerate(d["scenes"]):
        if s.get("bg", "black") not in R.WORLDS:
            errs.append(f"scene {i}: unknown bg '{s.get('bg')}'")
        if s.get("transition") and s["transition"] not in TRANS:
            errs.append(f"scene {i}: unknown transition '{s['transition']}'")
        for ca in s.get("cast", []):
            if ca.get("id") not in d["cast"]:
                errs.append(f"scene {i}: cast id '{ca.get('id')}' not defined in cast")
            if ca.get("action", "stand") not in ACTIONS:
                errs.append(f"scene {i}: unknown action '{ca.get('action')}'")
        for pr in s.get("props", []):
            if pr.get("kind") not in PROPS:
                errs.append(f"scene {i}: unknown prop '{pr.get('kind')}'")
    if errs:
        return errs, warns
    # estimated timeline (2.7 words/s) and a test render of every scene
    t, scenes, wl = 0.15, [], []
    for i, s in enumerate(d["scenes"]):
        ws = s["say"].split(); dur = len(ws) / 2.7 + 0.2
        for j, w in enumerate(ws):
            wl.append({"w": w, "s": t + j * dur / len(ws), "e": t + (j + 0.9) * dur / len(ws), "scene": i})
        scenes.append({"s": t, "e": t + dur}); t += dur + 0.22
    scenes[-1]["e"] += 1.0
    tl = {"scenes": scenes, "groups": R.caption_groups(wl), "total": scenes[-1]["e"]}
    sketch_mode = d.get("style", "sketch") == "sketch"
    if sketch_mode:
        import sketch as S
        tl.update(style="sketch", fps=30, shots=S.plan_shots(d, scenes, wl))
    info = skia.ImageInfo.Make(R.W, R.H, skia.kBGRA_8888_ColorType, skia.kPremul_AlphaType)
    surf = skia.Surface.MakeRaster(info); c = surf.getCanvas()
    tiles = []
    for i, s in enumerate(scenes):
        for k, tt in enumerate((s["s"] + 0.05, (s["s"] + s["e"]) / 2, s["e"] - 0.05)):
            try:
                if sketch_mode:
                    S.SketchRenderer(R.Stage(d), tl).frame(c, min(tt, tl["total"] - 0.01), 0)
                else:
                    R.render_frame(c, R.Stage(d), tl, min(tt, tl["total"] - 0.01), surf, 0, R.Post())
            except Exception as e:
                errs.append(f"scene {i}: render error {type(e).__name__}: {e}")
                break
            if k == 1 and sheet:
                a = np.empty((R.H, R.W, 4), np.uint8); surf.readPixels(info, a, R.W * 4)
                from PIL import Image
                tiles.append(Image.fromarray(a[:, :, [2, 1, 0]]).resize((216, 384)))
    if sheet and tiles:
        from PIL import Image
        cols = min(8, len(tiles)); rows = (len(tiles) + cols - 1) // cols
        im = Image.new("RGB", (216 * cols, 384 * rows))
        for i, tl_ in enumerate(tiles):
            im.paste(tl_, ((i % cols) * 216, (i // cols) * 384))
        im.save(sheet)
    return errs, warns

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sheet = sys.argv[sys.argv.index("--sheet") + 1] if "--sheet" in sys.argv else None
    if sheet in args:
        args.remove(sheet)
    bad = 0
    for p in args:
        e, w = check(p, sheet.replace(".png", f"-{os.path.basename(p)[:-5]}.png") if sheet else None)
        print(("FAIL " if e else "OK   ") + p)
        for x in e:
            print("   error:", x)
        for x in w:
            print("   warning:", x)
        bad += bool(e)
    sys.exit(1 if bad else 0)
