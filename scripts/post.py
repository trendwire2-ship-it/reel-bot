#!/usr/bin/env python3
"""Pick the next queued story if a posting slot is due, render it, and publish it as a Facebook Page Reel.

Env: FB_PAGE_ID, FB_PAGE_TOKEN (secrets). Optional: SLOTS="9,13,19", TZ_NAME="America/New_York",
FORCE=1 (post now regardless of slot), DRY_RUN=1 (render only, don't post).
"""
import datetime as dt, glob, json, os, shutil, subprocess, sys, time, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPH = "https://graph.facebook.com/v25.0"
LOG = os.path.join(ROOT, "posted", "log.json")

def now_local():
    return dt.datetime.now(ZoneInfo(os.environ.get("TZ_NAME", "America/New_York")))

def due_slot(log):
    """Return 'YYYY-MM-DD@H' for the slot that is due now and not yet used, else None."""
    slots = [int(s) for s in os.environ.get("SLOTS", "9,13,19").split(",")]
    n = now_local()
    for h in sorted(slots, reverse=True):
        start = n.replace(hour=h, minute=0, second=0, microsecond=0)
        if n < start - dt.timedelta(minutes=50):
            continue
        if start - dt.timedelta(minutes=50) <= n < start + dt.timedelta(hours=3):  # early start for render time; tolerate late cron
            key = f"{start:%Y-%m-%d}@{h}"
            return None if any(e.get("slot") == key for e in log) else key
    return None

def api(method, url, data=None, headers=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Graph API error {e.code}: {e.read().decode()[:800]}")

def publish_reel(video_path, description, title):
    page, token = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    start = api("POST", f"{GRAPH}/{page}/video_reels", {"upload_phase": "start", "access_token": token})
    vid = start["video_id"]
    size = os.path.getsize(video_path)
    with open(video_path, "rb") as f:
        req = urllib.request.Request(
            f"https://rupload.facebook.com/video-upload/v25.0/{vid}", data=f.read(), method="POST",
            headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
        with urllib.request.urlopen(req, timeout=600) as r:
            print("upload:", r.read().decode()[:200])
    fin = api("POST", f"{GRAPH}/{page}/video_reels", {
        "upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
        "description": description, "title": title, "access_token": token})
    print("finish:", fin)
    # poll status until published or error (max ~5 min)
    for _ in range(30):
        st = api("GET", f"{GRAPH}/{vid}?fields=status&access_token={urllib.parse.quote(token)}")
        s = st.get("status", {})
        print("status:", s.get("video_status"), s.get("publishing_phase", {}).get("status"))
        if s.get("video_status") == "error" or s.get("publishing_phase", {}).get("status") == "error":
            raise SystemExit(f"Facebook reported an error: {s}")
        if s.get("publishing_phase", {}).get("status") == "complete":
            break
        time.sleep(10)
    return vid

def main():
    log = json.load(open(LOG)) if os.path.exists(LOG) else []
    slot = "manual" if os.environ.get("FORCE") == "1" else due_slot(log)
    if not slot:
        print(f"No slot due at {now_local():%Y-%m-%d %H:%M %Z}; nothing to do.")
        return
    queue = sorted(glob.glob(os.path.join(ROOT, "queue", "*.json")))
    if not queue:
        print("Queue is empty; nothing to post.")
        return
    path = queue[0]
    story = json.load(open(path))
    out = os.path.join(ROOT, "out", story["id"] + ".mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "render.py"), path, out], check=True)
    if os.environ.get("DRY_RUN") == "1":
        print("DRY_RUN: rendered", out, "- not posting.")
        return
    vid = publish_reel(out, story["caption"], story.get("title", ""))
    shutil.move(path, os.path.join(ROOT, "posted", os.path.basename(path)))
    log.append({"id": story["id"], "slot": slot, "video_id": vid, "at": dt.datetime.utcnow().isoformat() + "Z"})
    json.dump(log, open(LOG, "w"), indent=1)
    print("Posted", story["id"], "video", vid)

if __name__ == "__main__":
    main()
