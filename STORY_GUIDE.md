# Story guide (for the daily writer)

## House style
Every story is a painted **motion comic made with Higgsfield** (the owner's choice; like the Bonnie and Clyde reel).
If Higgsfield credits run low, write the FREE version instead (same story, panels described by text prompts, painted
and animated for free by the repo). Every story ALSO keeps the full cinematic scene layout (bg, cast, actions...) as
a last-resort fallback. Every reel is 55–65 seconds. The renderers burn in the "© FACTS ON FACTS" watermark
automatically; never ask for text, logos or watermarks inside generated art. See "Motion comic stories" at the end.

## Topics
Rotate history, war and true crime. Prefer famous, well-documented, decades-old cases and events (US/UK audiences).
Avoid: cases involving children as victims, sexual crimes, recent cases (< 25 years) with living suspects who were never
convicted, anything still in court, and graphic gore. Never name or accuse anyone the record does not support. Don't
repeat a topic already in `posted/` or `queue/`.

## Accuracy (non-negotiable)
Before writing, look up every fact (names, dates, numbers, quotes) on at least two reliable sources (FBI, Britannica,
national archives, major newspapers, Wikipedia cross-checked). Put 2+ URLs in `sources`. If a detail is disputed, leave
it out or say "reportedly". Quotes must be the documented wording.

## Length & pacing
- 150–170 spoken words total. HARD CAP: every reel is 55–65 seconds (the renderer speeds up anything past 64.5 s).
- 8–11 scenes, each 1–3 short sentences, 6–25 words. Short punchy sentences. Fragments are good.
- Write numbers naturally: "1971", "$200,000", "8:13 PM" — the voice reads them correctly.

## Retention structure (every story)
1. **0–2 s payoff-first opening (the #1 rule; Meta's own data shows our weak reels lose 88% of viewers here)**:
   the FIRST sentence is the most shocking payoff/contradiction, max 12 words, said in the first 2 seconds.
   NEVER open with a date, a place, a name intro or scene-setting ("May 23, 1934. A Louisiana back road..." is
   banned). Dates and places come in scene 1 or later.
   Good: "Bonnie and Clyde were stopped cold by a broken-down truck." / "He robbed a plane, then jumped out of it."
   / "The FBI's perfect witness was the man they'd tried to kill."
   Top-level `"hook"` = 2–5 word banner that is on screen from the very first frame and makes the same promise
   (e.g. "130 BULLETS IN 16 SECONDS"). The first picture must show the most dramatic image of the story.
2. **Open a loop** early that only closes at the end ("But that's not the strangest part").
3. **Re-hook every ~10–15 s**: add `"hook"` banners to 3–4 scenes at turning points ("THEN HE SAID THIS...",
   "9 YEARS LATER...", "HERE'S THE TWIST"). Use a pattern interrupt: new location, time jump, a number, a quote.
4. **Escalate**: each scene raises stakes or reveals something new. No filler, no background lectures.
5. **Payoff + question**: resolve the loop, then end with a debatable question and "Tell me in the comments."

## Characters must resemble the real people
Every real person on screen gets a `cast` entry built from documented appearance in that period (photos,
descriptions, portraits): skin tone (hex), hair colour + style, facial hair, glasses, typical clothing/uniform, hat,
build, height, age. Generic people (clerks, crowds) can be generic. Never draw a real child victim; a generic
child is fine only where the record involves a child witness/finder.

Cast spec keys: `skin`(hex) `hair`(black|brown|dark_brown|blonde|red|auburn|grey|white|#hex)
`hair_style`(short|side_part|receding|bald|pompadour|buzz|long|bob|bun|ponytail|curly|afro|kid_messy)
`eyes`(hex) `glasses`(none|glasses|sunglasses) `facial_hair`(none|mustache|beard|stubble|goatee) `beard_color`
`outfit`(suit|raincoat|coat|uniform|stewardess|tshirt|dress|kid|robe|prison|armor|lab) `outfit_color` `shirt_color`
`tie_color`("none" to hide) `pants_color` `scarf_color` `sash_color` `medals`(true) `badge`(true)
`hat`(none|fedora|cap|military|helmet|pillbox|crown|tophat|beret) `hat_color` `build`(slim|average|heavy)
`height`(0.7–1.1) `age` `gender`(m|f).

## Scenes
```
{"say": "...", "hook": "OPTIONAL BANNER", "bg": "...", "bg_opts": {...},
 "camera": "push_in|pull_out|pan_left|pan_right|track_left|track_right|drift|rise|crane_down",
 "transition": "whip_left|whip_right|push|fog|flash|dissolve", "shake": [[start_s, duration_s, strength_px]],
 "text": {"big": "NOV 24, 1971", "sub": "PORTLAND, OREGON", "y": 0.27, "color": "#ffd60a", "size": 150},
 "label": {"name": "DAN COOPER", "role": "NAME GIVEN AT THE TICKET COUNTER", "y": 0.6, "at": 1.0},
 "cast": [{"id": "cooper", "x": [0.1, 0.5], "y": 0.88, "scale": 1.0, "action": "walk", "face": 1, "expr": "serious",
           "talk": false, "enter": "fade|left|right|drop|rise", "appear": 0.0, "hold": "briefcase", "chute": false, "sway": 0, "rot": 0, "z": 1}],
 "props": [{"kind": "money", "x": 0.5, "y": 0.6, "scale": 1.0, "motion": "pop|drop|float|slam|none", "appear": 0.5, "opts": {}, "z": 0}]}
```
- Any number can be `[start, end]` (or more keyframes): it moves smoothly across the scene. Keep something moving in every scene.
- `x` is 0–1 across, `y` is 0–1 down (for people, `y` is where the feet are; 0.86–0.92 = standing on the floor;
  `y` 1.2–1.3 with `scale` 2–2.2 = chest-up close-up).
- Keep important things between y 0.18 and 0.68: captions sit at ~0.72, Facebook's buttons cover the bottom and right edge.
- Backgrounds (multiplane, lit, with fog/rain/parallax): forest_night (opts lightning:[s]), sky (night flight; opts rain,
  lightning), airport (opts board:[3 rows], counter, sign), cabin, office/evidence (evidence board with animated red strings;
  opts labels:[short facts already in the script]), river (overcast day), prison (cellblock; opts bars: view from inside a cell, guard: patrolling guard),
  sea_night (moonlit sea; opts city: skyline lights, island + island_x: island with lighthouse, moon: [x,y], rain). Simpler: map, street (opts rain),
  battlefield (opts blasts:[s]), palace, courtroom, room (opts wall, floor), black.
- Visual style: premium noir documentary. One transition per scene, vary them (whip for time/place jumps, push for
  zooming into a detail, fog for mysterious jumps, flash for shocks, dissolve for calm moments). Use "shake" only for
  real physical action (a jolt, a blast), 15–30 px. A dollar amount in text.big counts up automatically.
- Evidence-board labels and any on-screen text must only repeat facts that are in the narration. Always set
  bg_opts.labels for office/evidence scenes (otherwise the clippings are blank).
- Actions: stand, walk, run, talk, point, hold, give, carry, shock, lean, fall, hang (use with chute), dig, salute, fight, kneel, sit.
- Expressions: neutral, serious, smile, sad, angry, shock.
- Props: briefcase(opts open), note, money(opts stacks), moneybag, parachute, shovel, newspaper(opts headline "LINE1|LINE2", paper),
  poster(opts title, char=<cast id>, sub), plane_side(opts stairs 0–1, tail colour), bills, stamp(opts text), file(opts title),
  gun, sword, fire, phone_booth, raft (bobbing, with paddles; seat people on it with action sit and a lower z),
  submarine (surfaced, bobbing), dummy_head(opts hair).
- Use `close-ups` (big scale) on the key person 2–3 times; vary backgrounds and cameras every scene.

## Caption + hashtags (the Facebook post text)
The poster builds the description as: caption, then "🔔 Follow Facts on Facts for a new true story every day.",
then the hashtags (plus #FactsOnFacts, added automatically). Facebook flags more than 5 hashtags.
- `caption`: three short lines separated by blank lines (\n\n), no hashtags:
  1. Scroll-stopping hook (under 15 words): the most shocking fact or a tense contradiction, one fitting emoji
     ("He hijacked a plane, took $200,000… then jumped out into a storm at night. 🪂").
  2. Tease (1 sentence) that adds stakes but doesn't give away the ending.
  3. A debatable question + "Tell us below 👇".
- `hashtags`: exactly 3 tags: 1 broad (#TrueCrime or #History or #WW2), 1 topic-specific (#DBCooper), 1 community
  tag (#UnsolvedMysteries #ColdCase #MilitaryHistory). CamelCase, no spaces. With #FactsOnFacts that makes 4.
- `pinned_comment`: the Page's own first comment, posted automatically (the owner pins it). One debate question with
  numbered options + a follow nudge, e.g. "📌 Which do you believe? 1️⃣ He died in the jump 2️⃣ He got away 👇".
- Optional `cover`: {"title": "2-5 word cover hook", "scene": index, "focus": cast id, "tag": "TRUE STORY"}.
  The cover (thumbnail) shows the focus character close-up with the title; defaults to `hook` and the biggest
  close-up. Write a cover title that creates curiosity ("HE FOOLED HITLER", "NEVER SEEN AGAIN").
- Optional `cta`: the end-of-video follow card text (default "MORE TRUE STORIES DAILY"; keep under 26 characters).


## Motion comic stories
### A) Higgsfield (default) — budget max 45 credits per story
Check the Higgsfield `balance` first. Only make a Higgsfield comic if the balance is at least 50 credits; otherwise
write version B and say so in the run summary.
1. Style reference: the owner's logo, Higgsfield media id `455225e4-119b-4022-821e-771632558344`, passed as
   `image_references` on every image (re-import from
   https://raw.githubusercontent.com/trendwire2-ship-it/reel-bot/main/assets/brand/logo.png if it stops working).
2. Character sheets first, for each person who appears in 2+ panels: `nano_banana_pro`, aspect_ratio 16:9,
   resolution 2k, the same person shown front / three-quarter / profile on plain grey, matching their real
   documented look. Pass the sheet's job id as a second `image_references` item in every panel showing them, and
   say "the person from the second reference image (same face, hair, clothes)".
3. Panels: 12–15 `nano_banana_pro` images, aspect_ratio 9:16, resolution 2k. Prompt start: "In EXACTLY the art style
   of the reference image: bold semi-realistic digital comic painting, confident ink outlines, dramatic cinematic
   lighting, deep blacks, rich red, gold and moonlit blue palette, gritty grain texture, vertical 9:16 composition.
   No text, no letters, no logo, no watermark." then one concrete, period-accurate moment. Use
   `generate_image_batch` + `jobs_wait`.
4. Key clips: exactly 3 (`kling3_0`, mode std, duration 3, sound off, aspect_ratio 9:16, the panel's job id as
   `start_image`): the FIRST shot (scene 0, word 0) plus the 2 biggest moments. Short motion prompt: what moves and
   how the camera moves.
5. Write the block (image/clip = the Higgsfield result URLs):
   ```json
   "comic": {"engine": "higgsfield", "variant": "hybrid", "prepared": true, "shots": [
     {"scene": 0, "word": 0, "image": "https://...png", "clip": "https://...mp4", "key": true, "move": "push_in", "fx": ["dust"]},
     {"scene": 0, "word": 9, "image": "https://...png", "move": "pan_left", "fx": []}]}
   ```
   Typical spend: 2 sheets x2 + 15 panels x2 + 3 clips x3.75 = about 45 credits.

### B) Free fallback (only when credits are below 50)
Same block shape, but instead of `image`/`clip` each shot has a `prompt` (40+ characters, one concrete moment,
no style words) and an `action` (10–30 words: what visibly moves in ~3 seconds), plus `"engine": "free"`,
`"variant": "comic"` and a `characters` map ({"id": "real documented look"}, referenced as `[id]` in prompts).
The repo paints and animates these for free.

### Rules for both
- 12–16 shots, a new panel every 3–5 seconds of narration; every scene gets at least one panel.
- `scene` / `word`: the panel appears on that word (0-based index into that scene's `say`). Shots in order; the
  first is scene 0, word 0 and must be the most dramatic image of the story.
- Never put a real person's name in an image prompt; describe them. No gore, no blood, no corpses.
- `move`: push_in | pull_out | pan_left | pan_right | tilt_up | tilt_down (vary them).
- `fx` (optional overlays): rain, heavy_rain, fog, dust, lightning, flicker, embers, snow.
- Run `python3 scripts/validate.py <file>`; it checks the comic block.
