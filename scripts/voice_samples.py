#!/usr/bin/env python3
"""Render the same dramatic passage in several free narrator voices, for the owner to pick one.
Writes out/voices/<name>.mp3. All engines are free (Chatterbox MIT, Kokoro Apache-2.0, Edge read-aloud voices)."""
import os, subprocess, sys, tempfile
import numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R

TEXT = ["Two police officers buzzed the door of a Boston museum. They weren't police.",
        "Within minutes, both guards were handcuffed in the basement.",
        "Thirteen works of art, worth about $500 million, vanished into the night.",
        "And to this day... the empty frames still hang on the wall."]

OUT = os.path.join(R.ROOT, "out", "voices")
os.makedirs(OUT, exist_ok=True)
tmp = tempfile.mkdtemp()


def save(name, res):
    parts = []
    for a, _ in res:
        parts += [a, np.zeros(int(0.35 * R.SR), np.float32)]
    wav = os.path.join(tmp, name + ".wav")
    sf.write(wav, np.concatenate(parts), R.SR)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-af", R.VOICE_FX + ",loudnorm=I=-14:TP=-1.5",
                    "-b:a", "160k", os.path.join(OUT, name + ".mp3")], check=True)
    print("saved", name, flush=True)


def run(name, env, fn):
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        save(name, fn())
    except Exception as e:
        print("FAILED", name, type(e).__name__, str(e)[:200], flush=True)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def edge(voice):
    def f():
        R.VOICE = voice
        res, eng = R.tts_scenes(TEXT, tmp)
        assert eng == "edge", eng
        return res
    return f


# 1-2. Offline Kokoro narrators
run("1-deep-american-onyx", {"KOKORO_VOICE": "am_onyx"}, lambda: R.kokoro_scenes(TEXT))
run("2-british-documentary-george", {"KOKORO_VOICE": "bm_george"}, lambda: R.kokoro_scenes(TEXT))
run("3-british-storyteller-fable", {"KOKORO_VOICE": "bm_fable"}, lambda: R.kokoro_scenes(TEXT))
# 4-6. Edge narrators, slowed a touch and pitched down for gravitas
run("4-american-christopher", {"VOICE_MODE": "edge", "EDGE_RATE": "-6", "EDGE_PITCH": "-4Hz"}, edge("en-US-ChristopherNeural"))
run("5-american-guy", {"VOICE_MODE": "edge", "EDGE_RATE": "-6", "EDGE_PITCH": "-3Hz"}, edge("en-US-GuyNeural"))
run("6-american-davis", {"VOICE_MODE": "edge", "EDGE_RATE": "-6", "EDGE_PITCH": "-3Hz"}, edge("en-US-DavisNeural"))
# 7. Expressive Chatterbox performance of the deep narrator (dramatic delivery)
onyx = os.path.join(tmp, "onyx_ref.wav")
try:
    os.environ["KOKORO_VOICE"] = "am_onyx"
    ref = R.kokoro_scenes(["In the dead of night, the city held its breath. Somewhere out there, the truth was waiting. "
                           "Nobody knew it yet, but history was about to change forever."])[0][0]
    sf.write(onyx, ref, R.SR)
    R.REF = onyx
    run("7-dramatic-deep-performer", {"VOICE_EXAGGERATION": "0.8", "VOICE_CFG": "0.3", "VOICE_TEMP": "0.8"},
        lambda: R.clone_scenes(TEXT, 1.0))
except Exception as e:
    print("FAILED 7", e)
# 8. The owner's own voice, dramatic settings
own = os.path.join(R.ROOT, "assets", "voice_ref.wav")
if os.path.exists(own):
    R.REF = own
    run("8-your-voice-dramatic", {"VOICE_EXAGGERATION": "0.8", "VOICE_CFG": "0.3", "VOICE_TEMP": "0.8"},
        lambda: R.clone_scenes(TEXT, 1.0))
