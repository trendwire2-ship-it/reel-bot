#!/usr/bin/env python3
"""Daily prep for free full-motion comics (runs in GitHub Actions, before posting).

For every queued story with a "comic" block that is not prepared yet:
  1. paint each panel for free (Cloudflare, scripts/paint.py) and store it as a GitHub release asset,
  2. send every panel to the free Kaggle GPU, where LTX-Video animates it into a ~3.4 s action clip,
  3. store the clips as release assets, write their URLs into the story (variant "full") and mark it prepared.
If Kaggle fails, the story still has its painted panels and posts as a moving-painting comic.
"""
import glob, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
REPO = os.environ.get("GITHUB_REPOSITORY", "trendwire2-ship-it/reel-bot")
TAG = "media"
STYLE = "painted graphic-novel comic art style, consistent characters, smooth natural motion, cinematic"


def gh(*args, check=True):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}: {(r.stdout + r.stderr)[-500:]}")
    return r.stdout


def upload(paths):
    if not paths:
        return
    gh("release", "view", TAG, "-R", REPO, check=False) or gh(
        "release", "create", TAG, "-R", REPO, "--title", "Reel media (panels and clips)",
        "--notes", "Painted panels and animated clips used by Facts on Facts reels. (c) Facts on Facts.")
    for i in range(0, len(paths), 20):
        gh("release", "upload", TAG, *paths[i:i + 20], "-R", REPO, "--clobber")


def url(name):
    return f"https://github.com/{REPO}/releases/download/{TAG}/{name}"


def motion_text(sh):
    act = sh.get("action") or "subtle natural movement, people breathe and shift, light and atmosphere drift"
    return f"{act}. {STYLE}."


def main(only=None):
    import paint
    stories = []
    for p in sorted(glob.glob(os.path.join(ROOT, "queue", "*.json"))):
        if only and only not in p:
            continue
        d = json.load(open(p))
        if d.get("comic") and not d["comic"].get("prepared") and d["comic"].get("engine") != "higgsfield":
            stories.append((p, d))
    if not stories:
        print("nothing to prepare"); return
    os.makedirs(os.path.join(ROOT, "out", "media"), exist_ok=True)
    jobs = []
    for p, d in stories:
        paint.paint_story(d)  # local paths in shot["image"]
        files = []
        for i, sh in enumerate(d["comic"]["shots"]):
            if not str(sh["image"]).startswith("https://"):
                name = f"{d['id']}-p{i:02d}.jpg"
                dst = os.path.join(ROOT, "out", "media", name)
                subprocess.run(["cp", sh["image"], dst], check=True)
                files.append(dst)
                sh["image"] = url(name)
            if sh.get("clip"):
                continue  # keep clips that already exist (e.g. paid Kling clips)
            jobs.append({"name": f"{d['id']}-c{i:02d}", "image": sh["image"], "motion": motion_text(sh),
                         "seed": 7 + i})
        upload(files)
        json.dump(d, open(p, "w"), indent=1, ensure_ascii=False)  # panels saved even if Kaggle fails
        print(f"painted {len(files)} panels for {d['id']}", flush=True)

    got = []
    if os.environ.get("KAGGLE_KEY") and os.environ.get("KAGGLE_USERNAME"):
        import kaggle_clips
        cfg = {"dtype": "fp16", "width": 480, "height": 832, "frames": 81, "budget_s": 3 * 3600,
               "candidates": [["Lightricks/LTX-Video-0.9.5", "condition", 30, 3.0]]}
        try:
            got = kaggle_clips.run(jobs, cfg, os.path.join(ROOT, "out", "clips"))
        except Exception as e:
            print("Kaggle step failed:", e, flush=True)
    clips = [os.path.join(ROOT, "out", "clips", g + ".mp4") for g in got]
    upload(clips)
    have = set(got)
    for p, d in stories:
        n = 0
        for i, sh in enumerate(d["comic"]["shots"]):
            name = f"{d['id']}-c{i:02d}"
            if name in have and not sh.get("clip"):
                sh["clip"] = url(name + ".mp4"); n += 1
        d["comic"]["variant"] = "full"
        d["comic"]["prepared"] = True
        json.dump(d, open(p, "w"), indent=1, ensure_ascii=False)
        print(f"{d['id']}: {n}/{len(d['comic']['shots'])} panels animated", flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
