#!/usr/bin/env python3
"""Free panel painter for motion comics: turns each shot's text "prompt" into a 1080x1920 painted image.

Order of providers (all free, no paid credits):
  1. Pollinations.ai image endpoint (FLUX, no key, native 1080x1920, ~1 request per 15 s for anonymous use).
  2. Fallback: Cloudflare Workers AI (FLUX.1 schnell, square, centre-cropped) if CF_ACCOUNT_ID + CF_API_TOKEN are set.
Images are cached by prompt+seed in out/cache, so re-renders cost nothing and give identical art.

Story format:
  "comic": {"style": "...optional extra style words...",
            "characters": {"bonnie": "petite woman, 1930s, wavy strawberry-blonde bob, beret, ..."},
            "shots": [{"scene": 0, "word": 0, "prompt": "[bonnie] leans out of a 1934 Ford V8 ...", "move": "push_in"}]}
  "[id]" in a prompt is replaced by that character's description, so every panel describes them identically.
"""
import hashlib, json, os, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "out", "cache")
W, H = 1080, 1920

HOUSE_STYLE = ("bold semi-realistic digital comic book painting, graphic novel art, confident black ink outlines, "
               "dramatic cinematic chiaroscuro lighting, deep blacks, rich crimson, gold and moonlit blue palette, "
               "gritty painterly texture, film grain, highly detailed, vertical composition")
NEGATIVE = "no text, no letters, no words, no captions, no speech bubbles, no logo, no watermark, no signature"


def full_prompt(story, shot):
    cm = story["comic"]
    p = shot["prompt"]
    for cid, desc in cm.get("characters", {}).items():
        p = p.replace(f"[{cid}]", f"{cid.replace('_', ' ')} ({desc})")
    style = HOUSE_STYLE + (", " + cm["style"] if cm.get("style") else "")
    return f"{p}. Style: {style}. {NEGATIVE}."


def _seed(story, i):
    return int(hashlib.md5(f"{story.get('id', 'x')}-{i}".encode()).hexdigest()[:6], 16)


def _cloudflare(prompt, seed):
    acc, tok = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
    if not (acc and tok):
        return None
    url = f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    body = json.dumps({"prompt": prompt[:2000], "steps": 8, "seed": seed}).encode()
    req = urllib.request.Request(url, body, {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    import base64
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.load(r)
    return base64.b64decode(res["result"]["image"])


def _pollinations(prompt, seed):
    q = urllib.parse.quote(prompt[:1800], safe="")
    url = (f"https://image.pollinations.ai/prompt/{q}?width={W}&height={H}&seed={seed}"
           f"&model=flux&nologo=true&enhance=false&private=true")
    req = urllib.request.Request(url, headers={"User-Agent": "facts-on-facts-reel-bot/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
        if not r.headers.get("content-type", "").startswith("image"):
            raise RuntimeError("not an image: " + data[:200].decode("utf-8", "replace"))
    return data


def paint_story(story):
    """Fill shot['image'] with a local file path for every shot that only has a 'prompt'. Returns count painted."""
    os.makedirs(CACHE, exist_ok=True)
    made = 0
    last_poll = 0.0
    for i, sh in enumerate(story["comic"]["shots"]):
        if sh.get("image") or not sh.get("prompt"):
            continue
        prompt, seed = full_prompt(story, sh), sh.get("seed", _seed(story, i))
        path = os.path.join(CACHE, "paint-" + hashlib.md5(f"{prompt}|{seed}".encode()).hexdigest() + ".jpg")
        if not os.path.exists(path):
            data, err = None, None
            for attempt in range(6):
                try:
                    data = _cloudflare(prompt, seed) if attempt >= 4 else None
                    if data is None:
                        wait = 16 - (time.time() - last_poll)
                        if wait > 0:
                            time.sleep(wait)
                        last_poll = time.time()
                        data = _pollinations(prompt, seed)
                    break
                except Exception as e:  # rate limit / timeout: back off and retry
                    err = e
                    print(f"paint shot {i} attempt {attempt + 1} failed: {e}", flush=True)
                    time.sleep(20 * (attempt + 1))
            if data is None:
                raise RuntimeError(f"could not paint shot {i}: {err}")
            open(path, "wb").write(data)
            made += 1
            print(f"painted shot {i + 1}/{len(story['comic']['shots'])}", flush=True)
        sh["image"] = path
    return made


if __name__ == "__main__":
    st = json.load(open(sys.argv[1]))
    print(paint_story(st), "panels painted")
