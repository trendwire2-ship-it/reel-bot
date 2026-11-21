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

def parse_slots():
    """SLOTS like "America/New_York:9,America/New_York:13,Africa/Accra:20" (plain hours use TZ_NAME)."""
    out = []
    for item in os.environ.get("SLOTS", "America/New_York:9,America/New_York:13,Africa/Accra:20").split(","):
        tz, _, h = item.strip().rpartition(":")
        out.append((tz or os.environ.get("TZ_NAME", "America/New_York"), int(h)))
    return out

def due_slot(log):
    """Return 'YYYY-MM-DD@H' (+tz) for the slot due now and not yet used, else None."""
    now_utc = dt.datetime.now(dt.timezone.utc)
    for tz, h in parse_slots():
        n = now_utc.astimezone(ZoneInfo(tz))
        start = n.replace(hour=h, minute=0, second=0, microsecond=0)
        if start - dt.timedelta(minutes=50) <= n < start + dt.timedelta(hours=3):
            key = f"{start:%Y-%m-%d}@{h}" + ("" if tz == "America/New_York" else f"@{tz}")
            if not any(e.get("slot") == key for e in log):
                return key
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

def check_facebook():
    page, token = os.environ.get("FB_PAGE_ID", ""), os.environ.get("FB_PAGE_TOKEN", "")
    if not page or not token:
        raise SystemExit("FB_PAGE_ID or FB_PAGE_TOKEN secret is missing.")
    q = urllib.parse.quote(token)
    info = api("GET", f"{GRAPH}/{page}?fields=id,name,link&access_token={q}")
    print(f"OK: token works for Page '{info.get('name')}' (id {info.get('id')})")
    reels = api("GET", f"{GRAPH}/{page}/video_reels?limit=1&access_token={q}")
    print(f"OK: can access the Page's Reels ({len(reels.get('data', []))} found).")
    dbg = api("GET", f"{GRAPH}/me?fields=id,name&access_token={q}")
    if str(dbg.get("id")) != str(page):
        print("WARNING: this looks like a user token, not the Page token. Use the access_token from me/accounts.")
    print("Facebook connection looks good.")

FOLLOW_LINE = os.environ.get("FOLLOW_LINE", "🔔 Follow Facts on Facts for a new true story every day.")
CORE_TAGS = ["#FactsOnFacts", "#Reels"]

def build_description(story):
    cap = story.get("caption", "").strip()
    tags = list(story.get("hashtags", []))
    # pull any hashtags already typed into the caption into the list
    for tg in [w for w in cap.split() if w.startswith("#")]:
        tags.append(tg); cap = cap.replace(tg, "")
    cap = " ".join(cap.split(" ")).strip()
    seen, out = set(), []
    for tg in tags + CORE_TAGS:
        k = tg.lower()
        if k not in seen:
            seen.add(k); out.append(tg)
    return f"{cap}\n\n{FOLLOW_LINE}\n\n{' '.join(out[:10])}"

def pinned_text(story):
    if story.get("pinned_comment"):
        return story["pinned_comment"]
    q = [ln for ln in story.get("caption", "").split("\n") if "?" in ln]
    ask = q[-1].replace("Tell us below 👇", "").strip() if q else "What do you think happened?"
    return f"📌 {ask} Drop your answer below 👇 New true story every day, follow so you don't miss the next one."

def comment_as_page(video_id, text):
    """First comment as the Page (needs pages_manage_engagement). Pinning itself isn't available in the API."""
    token = os.environ["FB_PAGE_TOKEN"]
    body = urllib.parse.urlencode({"message": text, "access_token": token}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{GRAPH}/{video_id}/comments", data=body, method="POST"), timeout=60) as r:
            cid = json.loads(r.read()).get("id")
            print("Comment posted:", cid)
            return cid
    except urllib.error.HTTPError as e:
        print("WARNING: could not post the comment (add pages_manage_engagement to the token?):", e.read().decode()[:300])
        return None

def set_cover(video_id, story_path):
    """Generate the cover image and upload it as the reel's preferred thumbnail."""
    out = os.path.join(ROOT, "out", os.path.basename(story_path)[:-5] + "-cover.jpg")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    try:
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "cover.py"), story_path, out], check=True)
    except Exception as e:
        print("WARNING: cover generation failed:", e); return False
    token = os.environ["FB_PAGE_TOKEN"]
    boundary = "----reelbot" + str(int(time.time() * 1000))
    parts = []
    for k, v in (("is_preferred", "true"), ("access_token", token)):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"source\"; filename=\"cover.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".encode())
    parts.append(open(out, "rb").read()); parts.append(f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"{GRAPH}/{video_id}/thumbnails", data=b"".join(parts), method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            print("Cover set:", r.read().decode()[:200]); return True
    except urllib.error.HTTPError as e:
        print("WARNING: could not set cover:", e.read().decode()[:300]); return False

def backfill_covers():
    log = json.load(open(LOG)) if os.path.exists(LOG) else []
    for e in log:
        p = os.path.join(ROOT, "posted", e["id"] + ".json")
        if e.get("cover_set") or not e.get("video_id") or not os.path.exists(p):
            continue
        if set_cover(e["video_id"], p):
            e["cover_set"] = True
    json.dump(log, open(LOG, "w"), indent=1)

def backfill_comments():
    log = json.load(open(LOG)) if os.path.exists(LOG) else []
    for e in log:
        if e.get("comment_id") or not e.get("video_id"):
            continue
        p = os.path.join(ROOT, "posted", e["id"] + ".json")
        story = json.load(open(p)) if os.path.exists(p) else {}
        cid = comment_as_page(e["video_id"], pinned_text(story))
        if cid:
            e["comment_id"] = cid
    json.dump(log, open(LOG, "w"), indent=1)

def main():
    if os.environ.get("COMMENT_BACKFILL") == "1":
        backfill_comments()
        return
    if os.environ.get("COVER_BACKFILL") == "1":
        backfill_covers()
        return
    if os.environ.get("CHECK_FB") == "1":
        check_facebook()
        return
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
        print("Description:\n" + build_description(story))
        print("DRY_RUN: rendered", out, "- not posting.")
        return
    desc = build_description(story)
    print("Description:\n" + desc)
    vid = publish_reel(out, desc, story.get("title", ""))
    dest = os.path.join(ROOT, "posted", os.path.basename(path))
    shutil.move(path, dest)
    entry = {"id": story["id"], "slot": slot, "video_id": vid, "at": dt.datetime.utcnow().isoformat() + "Z"}
    try:
        if set_cover(vid, dest):
            entry["cover_set"] = True
    except Exception as e:  # a cover problem must never block posting
        print("WARNING: cover step failed:", e)
    time.sleep(20)
    cid = comment_as_page(vid, pinned_text(story))
    if cid:
        entry["comment_id"] = cid
    log.append(entry)
    json.dump(log, open(LOG, "w"), indent=1)
    print("Posted", story["id"], "video", vid)

if __name__ == "__main__":
    main()
