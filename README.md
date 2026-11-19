# reel-bot

Faceless history / war / true-crime reels, auto-posted to a Facebook Page.

- `queue/*.json` — stories waiting to be posted (oldest file name posts first). Written by a Claude scheduled task.
- `scripts/render.py` — turns a story into a 9:16 reel: free Kokoro voice, motion graphics, captions, music.
- `scripts/post.py` — at 9 AM / 1 PM / 7 PM New York time, renders the next story and publishes it as a Reel.
- `.github/workflows/post-reels.yml` — runs the poster on GitHub's free servers. Your laptop can stay off.
- `posted/` — stories already posted, plus `log.json`.

Secrets needed (Settings → Secrets and variables → Actions): `FB_PAGE_ID`, `FB_PAGE_TOKEN`.

Manual controls: Actions → Post reels → Run workflow → tick **dry_run** to preview without posting, or **force** to post the next reel now.
Each run's video is downloadable from the run page under "Artifacts".

Story format: see any file in `queue/`. Visual types: `title`, `date`, `note`, `stat`, `icon`, `silhouette`, `stamp`, `map`.
Icons: plane, parachute, money, silhouette, magnifier, skull, sword, crown, gun, fire.
