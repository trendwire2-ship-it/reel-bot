#!/usr/bin/env python3
"""Motion-comic renderer: painted shot images (and optional AI video clips) brought to life with depth-based 2.5D
parallax, camera moves, weather/light FX, then the house captions, hook banners, voice and music.

Usage: COMIC_VARIANT=comic|hybrid|full python3 scripts/comic.py story.json out.mp4
Story needs "comic": {"shots": [{"scene": i, "word": w, "image": url, "clip": url|null, "key": bool,
                                 "move": "push_in|pull_out|pan_left|pan_right|tilt_up|tilt_down", "fx": [...]}]}
fx: rain, heavy_rain, fog, dust, lightning, flicker, embers, snow
"""
import hashlib, json, math, multiprocessing as mp, os, subprocess, sys, tempfile, urllib.request
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("REEL_FPS", "30")
import render as R  # noqa
from engine import W, H, hexcol, fill, stroke, rect, clamp, ease_io, ease_out, h01  # noqa
import skia

FPS = 30
CACHE = os.path.join(R.ROOT, "out", "cache")
XF = 0.32  # crossfade seconds between shots

def fetch(url):
    if os.path.exists(url):
        return url
    os.makedirs(CACHE, exist_ok=True)
    ext = os.path.splitext(url.split("?")[0])[1] or ".bin"
    p = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + ext)
    if not os.path.exists(p):
        for attempt in range(4):
            try:
                urllib.request.urlretrieve(url, p + ".part"); os.replace(p + ".part", p); break
            except Exception as e:
                print("download retry", attempt, e)
    return p

def cover_resize(img):
    import cv2
    h, w = img.shape[:2]
    s = max(W / w, H / h)
    img = cv2.resize(img, (int(math.ceil(w * s)), int(math.ceil(h * s))), interpolation=cv2.INTER_CUBIC)
    y0 = (img.shape[0] - H) // 2; x0 = (img.shape[1] - W) // 2
    return img[y0:y0 + H, x0:x0 + W]

_depth_pipe = None
def depth_map(path, rgb):
    """Relative depth 0 (far) .. 1 (near), cached. Depth Anything V2 Small (Apache-2.0); falls back to a vertical ramp."""
    import cv2
    cp = path + ".depth.npy"
    if os.path.exists(cp):
        return np.load(cp)
    d = None
    try:
        global _depth_pipe
        if _depth_pipe is None:
            from transformers import pipeline
            _depth_pipe = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf", device=-1)
        from PIL import Image
        out = _depth_pipe(Image.fromarray(rgb[:, :, ::-1]))
        d = np.asarray(out["predicted_depth"], dtype=np.float32)
        d = cv2.resize(d, (W, H), interpolation=cv2.INTER_CUBIC)
        d = (d - d.min()) / (np.ptp(d) + 1e-6)
    except Exception as e:
        print("depth fallback:", type(e).__name__, str(e)[:120])
        d = np.tile(np.linspace(0.2, 0.8, H, dtype=np.float32)[:, None], (1, W))
    d = cv2.GaussianBlur(d, (0, 0), 6)
    np.save(cp, d)
    return d

def load_clip(path):
    import cv2
    cap = cv2.VideoCapture(path); frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(cover_resize(f))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    return frames, fps

MOVES = {"push_in": (1.03, 1.14, 0, 0, 0, 0), "pull_out": (1.15, 1.03, 0, 0, 0, 0),
         "pan_left": (1.12, 1.12, 50, -50, 0, 0), "pan_right": (1.12, 1.12, -50, 50, 0, 0),
         "tilt_up": (1.12, 1.12, 0, 0, 60, -60), "tilt_down": (1.12, 1.12, 0, 0, -60, 60)}

class Shot:
    def __init__(self, spec, use_clip):
        import cv2
        self.spec = spec
        self.img = cover_resize(cv2.imread(fetch(spec["image"])))
        self.depth = depth_map(fetch(spec["image"]), self.img)
        self.clip = None
        if use_clip and spec.get("clip"):
            try:
                self.clip, self.clip_fps = load_clip(fetch(spec["clip"]))
                if len(self.clip) < 5:
                    self.clip = None
            except Exception as e:
                print("clip load failed:", e)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.xx, self.yy = xx, yy

    def frame(self, lt, dur):
        import cv2
        p = ease_io(clamp(lt / max(dur, 0.1)))
        if self.clip is not None:
            n = len(self.clip)
            span = n / self.clip_fps
            rate = min(1.0, span / max(dur, 0.1)) if dur > span else 1.0  # slow-mo to fill longer shots
            i = int(clamp(lt * rate * self.clip_fps, 0, n - 1))
            base = self.clip[i]
            z = 1.0 + 0.04 * p
            M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, z)
            return cv2.warpAffine(base, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        z0, z1, x0, x1, y0, y1 = MOVES.get(self.spec.get("move", "push_in"), MOVES["push_in"])
        z = z0 + (z1 - z0) * p
        tx = x0 + (x1 - x0) * p; ty = y0 + (y1 - y0) * p
        par = 28.0 * (p - 0.5)  # parallax strength: near layers slide more than far ones
        dz = 0.035 * (p - 0.5)
        d = self.depth
        sx = (self.xx - W / 2) / (z * (1 + dz * d)) + W / 2 - tx - par * d * (1 if (x1 - x0) >= 0 else -1)
        sy = (self.yy - H / 2) / (z * (1 + dz * d)) + H / 2 - ty - par * 0.35 * d
        return cv2.remap(self.img, sx, sy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

# ------------------------------------------------------------------ FX (procedural overlays)
def fx_draw(c, fx, t, k):
    if "rain" in fx or "heavy_rain" in fx:
        heavy = "heavy_rain" in fx
        from worlds import rain
        rain(c, t, 90 if heavy else 55, 70 if heavy else 50, 1900, 70, 2.2, seed=k)
        rain(c, t, 24 if heavy else 12, 80, 2800, 150, 4.5, seed=k + 9, col="#cfd9ee")
    if "fog" in fx:
        from worlds import draw_fog
        draw_fog(c, t, 900, 700, "#9aa6c8", 55, 22, 4.5, k)
        draw_fog(c, t, 1300, 600, "#9aa6c8", 45, 40, 3.5, k + 3)
    if "dust" in fx:
        from worlds import dust
        dust(c, t, 0, 0, W, H, 40, "#fff1cf", 110)
    if "embers" in fx:
        for i in range(30):
            x = (h01(i + k) * W + 40 * math.sin(t + i)) % W
            y = H - ((h01(i + 7) * H + t * (60 + 40 * h01(i))) % H)
            c.drawCircle(x, y, 2.5, fill("#ffb347", int(150 + 80 * math.sin(t * 3 + i))))
    if "snow" in fx:
        for i in range(70):
            x = (h01(i + k) * W + 30 * math.sin(t * 0.7 + i)) % W
            y = (h01(i + 3) * H + t * (50 + 40 * h01(i))) % H
            c.drawCircle(x, y, 2 + 2 * h01(i + 5), fill("#ffffff", 180))
    if "lightning" in fx:
        for lt in (0.6 + 2.3 * h01(k), 2.9 + h01(k + 1)):
            d = (t % 4.2) - lt
            if 0 <= d < 0.5:
                c.drawRect(rect(0, 0, W, H), fill("#dfe6ff", int(95 * clamp(d / 0.05) * math.exp(-max(0.0, d - 0.05) * 7))))
    if "flicker" in fx:
        a = int(30 * max(0.0, math.sin(t * 13) * math.sin(t * 5.3) - 0.3))
        if a:
            c.drawRect(rect(0, 0, W, H), fill("#000000", a))

# ------------------------------------------------------------------ timeline + render
def plan(story, scenes, words):
    shots = story["comic"]["shots"]
    out = []
    for i, sh in enumerate(shots):
        ws = [w for w in words if w["scene"] == sh["scene"]]
        wi = min(max(0, int(sh.get("word", 0))), max(0, len(ws) - 1))
        st = scenes[sh["scene"]]["s"] if sh.get("word", 0) == 0 or not ws else ws[wi]["s"] - 0.08
        out.append({"i": i, "s": max(0.0, st)})
    out[0]["s"] = 0.0
    for i, o in enumerate(out):
        o["e"] = out[i + 1]["s"] if i + 1 < len(out) else scenes[-1]["e"]
    return out

def worker(args):
    story, tl, f0, f1, outp, variant = args
    shots_spec = story["comic"]["shots"]
    use = lambda sp: variant == "full" or (variant == "hybrid" and sp.get("key"))
    cache = {}
    def shot(i):
        if i not in cache:
            if len(cache) > 3:
                cache.pop(next(iter(cache)))
            cache[i] = Shot(shots_spec[i], use(shots_spec[i]))
        return cache[i]
    info = skia.ImageInfo.Make(W, H, skia.kBGRA_8888_ColorType, skia.kPremul_AlphaType)
    surf = skia.Surface.MakeRaster(info); c = surf.getCanvas()
    post = R.Post()
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-g", str(FPS * 2), outp], stdin=subprocess.PIPE)
    buf = np.empty((H, W, 4), np.uint8)
    plan_ = tl["plan"]; total = tl["total"]
    for fi in range(f0, f1):
        t = fi / FPS
        k = 0
        for j, o in enumerate(plan_):
            if t >= o["s"]:
                k = j
        o = plan_[k]
        img = shot(k).frame(t - o["s"], o["e"] - o["s"])
        nxt = k + 1 if k + 1 < len(plan_) and t > plan_[k + 1]["s"] - XF else None
        if nxt is not None:
            o2 = plan_[nxt]
            q = ease_io((t - (o2["s"] - XF)) / XF)
            img2 = shot(nxt).frame(t - o2["s"], o2["e"] - o2["s"])
            img = (img.astype(np.float32) * (1 - q) + img2.astype(np.float32) * q).astype(np.uint8)
        bgra = np.dstack([img, np.full((H, W), 255, np.uint8)])
        c.clear(hexcol("#000000"))
        c.drawImage(skia.Image.fromarray(np.ascontiguousarray(bgra), colorType=skia.kBGRA_8888_ColorType), 0, 0)
        fx_draw(c, shots_spec[k].get("fx", []), t, k)
        # key-moment punch: brief white flash when a key shot starts
        if shots_spec[k].get("key") and 0 <= t - o["s"] < 0.25 and k > 0:
            c.drawRect(rect(0, 0, W, H), fill("#ffffff", int(90 * (1 - (t - o["s"]) / 0.25))))
        post.apply(surf, c, fi, 0.22, ("#5a2a1a", 0.08))
        # house UI: hook banners, captions, follow card, fade-out
        R.draw_banner(c, story.get("hook"), 0.0, t, dur=3.2, y=330)
        for i, s in enumerate(tl["scenes"]):
            if story["scenes"][i].get("hook"):
                R.draw_banner(c, story["scenes"][i]["hook"], s["s"], t, dur=2.6, y=330, color="#c0302a" if i % 2 else "#d4a017")
        R.draw_watermark(c, t, sum(map(ord, story.get("id", "x"))))
        R.draw_captions(c, tl["groups"], t)
        R.draw_follow_card(c, story.get("cta", "MORE TRUE STORIES DAILY"), t, total)
        if t > total - 0.6:
            c.drawRect(rect(0, 0, W, H), fill("#000000", int(255 * ease_io((t - (total - 0.6)) / 0.6))))
        surf.readPixels(info, buf, W * 4)
        ff.stdin.write(buf.tobytes())
    ff.stdin.close(); ff.wait()
    return outp

def render(story_path, out_path, variant):
    story = json.load(open(story_path))
    tmp = tempfile.mkdtemp()
    import pickle, shutil
    os.makedirs(CACHE, exist_ok=True)
    vc = os.path.join(CACHE, f"voice-{story.get('id', 'x')}.pkl")
    if os.path.exists(vc):
        voice_src, words, scenes, total = pickle.load(open(vc, "rb"))
        voice = os.path.join(tmp, "voice.wav"); shutil.copy(voice_src, voice)
    else:
        voice, words, scenes, total = R.build_audio(story, tmp)
        keep = os.path.join(CACHE, f"voice-{story.get('id', 'x')}.wav"); shutil.copy(voice, keep)
        pickle.dump((keep, words, scenes, total), open(vc, "wb"))
    hits = [0.05] + [s["s"] for i, s in enumerate(scenes) if story["scenes"][i].get("hook")]
    music = R.make_music(total, [s["s"] for s in scenes[1:]], hits, tmp, seed=sum(map(ord, story.get("id", "x"))))
    tl = {"scenes": scenes, "groups": R.caption_groups(words), "total": total, "plan": plan(story, scenes, words)}
    # prefetch media + depth once (shared cache for all workers)
    for sp in story["comic"]["shots"]:
        Shot(sp, variant == "full" or (variant == "hybrid" and sp.get("key")))
    nframes = int(total * FPS)
    nw = max(1, min(mp.cpu_count(), 4))
    b = [round(i * nframes / nw) for i in range(nw + 1)]
    parts = [os.path.join(tmp, f"p{i}.mp4") for i in range(nw)]
    with mp.get_context("fork").Pool(nw) as pool:
        pool.map(worker, [(story, tl, b[i], b[i + 1], parts[i], variant) for i in range(nw)])
    lst = os.path.join(tmp, "l.txt"); open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    silent = os.path.join(tmp, "v.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", voice, "-i", music, "-filter_complex",
                    "[1:a]highpass=f=70,acompressor=threshold=-21dB:ratio=2.5:attack=12:release=220:makeup=2[v];[2:a]volume=0.15[m];"
                    "[v][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    *R.COPYRIGHT_META, "-t", f"{total:.3f}", out_path], check=True)
    print(f"rendered {out_path} ({variant}, {total:.1f}s)")

if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2], os.environ.get("COMIC_VARIANT", "comic"))
