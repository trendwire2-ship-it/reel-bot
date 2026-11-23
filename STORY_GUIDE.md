# Story guide (for the daily writer)

## House style
Every story is a FREE painted **motion comic** (no paid tools, no Higgsfield, zero credits): you write a text
`prompt` for each panel and the repo paints it for free at render time. Every story ALSO keeps the full cinematic
scene layout (bg, cast, actions...) so it can fall back to the free 2.5D cinematic style if painting fails.
Every reel is 55–65 seconds. The renderers burn in the "© FACTS ON FACTS" watermark automatically; never ask for
text, logos or watermarks inside generated art. See "Motion comic stories" at the end.

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


## Motion comic stories (every story, free)
Add a `"comic"` block to every story (keep all the normal fields too):
```json
"comic": {"variant": "comic",
  "characters": {"clyde": "slim white man in his 20s, slicked-back dark hair, 1930s three-piece suit, fedora",
                 "bonnie": "petite white woman in her 20s, wavy strawberry-blonde bob, 1930s beret and dress"},
  "shots": [
    {"scene": 0, "word": 0, "move": "push_in", "fx": ["dust"],
     "prompt": "Low angle on a dusty Louisiana back road at dawn: [clyde] and [bonnie] in a tan 1934 Ford V8 slowing beside a broken-down truck, lawmen hidden in the bushes, tense, ambush about to happen"},
    {"scene": 0, "word": 9, "move": "pan_left", "fx": [], "prompt": "..."}]}
```
- 12–16 shots, a new panel every 3–5 seconds of narration. Every scene gets at least one panel.
- `scene` / `word`: the panel appears on that word (0-based index into that scene's `say`). Shots in order; the
  first is scene 0, word 0 and must be the single most dramatic image of the story (it is the first frame).
- `prompt` (40+ characters): ONE concrete moment: who, doing what, where, the era (year, clothes, cars, weapons),
  camera angle (low angle, close-up, wide shot, over-the-shoulder), lighting and mood. Do not write style words or
  "no text": the house painting style is added automatically.
- People: define each recurring person once in `characters` with their real documented look (age, build, hair,
  facial hair, glasses, period clothes) and write `[id]` in the prompt. Never put a real person's name in a
  prompt; describe them. No gore, no blood, no corpses, no weapons pointed at the viewer.
- `action` (REQUIRED, 10–30 words): what MOVES in this panel's clip, as one simple continuous action over about
  3 seconds: "the two men walk slowly down the gallery, flashlight beams sweeping across the paintings", "the frame
  crashes onto the marble floor and shatters". Every panel is animated into a real AI video clip from this text, so
  describe visible motion (walking, turning, smashing, running, smoke, waves), not thoughts or backstory. One action
  per panel; avoid complex multi-person fights or fast spinning, which animate badly.
- `move`: push_in | pull_out | pan_left | pan_right | tilt_up | tilt_down (vary them; used if a clip fails).
- `fx` (optional overlays): rain, heavy_rain, fog, dust, lightning, flicker, embers, snow.
- Run `python3 scripts/validate.py <file>`; it checks the comic block.
