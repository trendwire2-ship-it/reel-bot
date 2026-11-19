# Story guide (for the daily writer)

Each story is one JSON file in `queue/`, named `YYYY-MM-DD-N-slug.json` (N = 1, 2, 3 for that day's 9 AM, 1 PM and 7 PM New York slots).
Files post oldest-name-first, so date-prefixed names keep the order. See `posted/` and `queue/` for complete examples.

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
- 215–235 spoken words total (the renderer keeps it under 89 seconds; aim for 80–88 s).
- 10–15 scenes, each 1–3 short sentences, 6–30 words. Short punchy sentences. Fragments are good.
- Write numbers naturally: "1971", "$200,000", "8:13 PM" — the voice reads them correctly.

## Retention structure (every story)
1. **0–3 s cold open**: start at the most shocking moment, state the mystery or stakes in the first sentence.
   Top-level `"hook"` = 2–5 word banner (e.g. "HE WAS NEVER FOUND").
2. **Open a loop** early that only closes at the end ("But that's not the strangest part").
3. **Re-hook every ~10–15 s**: add `"hook"` banners to 4–5 scenes at turning points ("THEN HE SAID THIS...",
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
{"say": "...", "hook": "OPTIONAL BANNER", "bg": "...", "bg_opts": {...}, "camera": "push_in|pull_out|pan_left|pan_right|drift|rise",
 "transition": "zoom|push_left|push_right", "text": {"big": "NOV 24, 1971", "sub": "PORTLAND, OREGON", "y": 0.27, "color": "#ffd60a", "size": 150},
 "cast": [{"id": "cooper", "x": [0.1, 0.5], "y": 0.88, "scale": 1.0, "action": "walk", "face": 1, "expr": "serious",
           "talk": false, "enter": "fade|left|right|drop|rise", "appear": 0.0, "hold": "briefcase", "chute": false, "sway": 0, "rot": 0, "z": 1}],
 "props": [{"kind": "money", "x": 0.5, "y": 0.6, "scale": 1.0, "motion": "pop|drop|float|slam|none", "appear": 0.5, "opts": {}, "z": 0}]}
```
- Any number can be `[start, end]` (or more keyframes): it moves smoothly across the scene. Keep something moving in every scene.
- `x` is 0–1 across, `y` is 0–1 down (for people, `y` is where the feet are; 0.86–0.92 = standing on the floor;
  `y` 1.2–1.3 with `scale` 2–2.2 = chest-up close-up).
- Keep important things between y 0.18 and 0.68: captions sit at ~0.72, Facebook's buttons cover the bottom and right edge.
- Backgrounds: airport, cabin, sky (night clouds; opts rain, lightning:[seconds]), forest_night, river, office,
  map, street (opts rain), battlefield (opts blasts:[seconds]), palace, courtroom, room (opts wall, floor), black.
- Actions: stand, walk, run, talk, point, hold, give, carry, shock, lean, fall, hang (use with chute), dig, salute, fight, kneel, sit.
- Expressions: neutral, serious, smile, sad, angry, shock.
- Props: briefcase(opts open), note, money(opts stacks), moneybag, parachute, shovel, newspaper(opts headline "LINE1|LINE2", paper),
  poster(opts title, char=<cast id>, sub), plane_side(opts stairs 0–1, tail colour), bills, stamp(opts text), file(opts title),
  gun, sword, fire, phone_booth.
- Use `close-ups` (big scale) on the key person 2–3 times; vary backgrounds and cameras every scene.

## Caption (Facebook description)
1–2 sentences that tease without spoiling, then a question, then 5–7 hashtags (#truecrime #history #mystery ...).
