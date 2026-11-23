# Runs on Kaggle's free T4 GPU. Turns each painted panel into a short action clip with LTX-Video
# (open weights, Lightricks). The job list is injected by scripts/kaggle_clips.py as JOBS below.
# Output: /kaggle/working/clips/<name>.mp4 plus log.txt
import json, os, subprocess, sys, time, urllib.request, traceback

JOBS = json.loads(r'''__JOBS__''')
CFG = json.loads(r'''__CFG__''')
OUT = "/kaggle/working/clips"
os.makedirs(OUT, exist_ok=True)
LOG = open("/kaggle/working/log.txt", "a")


def log(*a):
    msg = " ".join(str(x) for x in a)
    print(msg, flush=True)
    LOG.write(msg + "\n"); LOG.flush()


t0 = time.time()
log("gpu:", subprocess.run("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader", shell=True,
                           capture_output=True, text=True).stdout.strip())
subprocess.run("pip install -q -U 'diffusers>=0.34' transformers accelerate sentencepiece imageio imageio-ffmpeg",
               shell=True)
import torch
from diffusers.pipelines.ltx.pipeline_ltx_condition import LTXVideoCondition
from diffusers.utils import export_to_video, load_image

dtype = torch.bfloat16 if CFG.get("dtype", "bf16") == "bf16" else torch.float16
# Try the fastest 2B models first; each entry: (repo, pipeline, steps, guidance)
CANDIDATES = CFG.get("candidates") or [
    ["Lightricks/LTX-Video-0.9.8-2B-distilled", "condition", 8, 1.0],
    ["Lightricks/LTX-Video-0.9.6-distilled", "condition", 8, 1.0],
    ["Lightricks/LTX-Video-0.9.5", "condition", 30, 3.0],
    ["Lightricks/LTX-Video", "i2v", 30, 3.0]]
pipe = None
for repo, kind, steps, guid in CANDIDATES:
    try:
        if kind == "condition":
            from diffusers import LTXConditionPipeline as P
        else:
            from diffusers import LTXImageToVideoPipeline as P
        pipe = P.from_pretrained(repo, torch_dtype=dtype)
        CFG.setdefault("steps", steps); CFG.setdefault("guidance", guid); CFG["kind"] = kind
        log("loaded", repo, kind)
        break
    except Exception as e:
        log("could not load", repo, str(e)[:160])
if pipe is None:
    raise SystemExit("no LTX model could be loaded")
pipe.vae.enable_tiling()
if CFG.get("offload", True):
    pipe.enable_model_cpu_offload()
else:
    pipe.to("cuda")
log(f"model loaded in {time.time() - t0:.0f}s")

W, H, NF = CFG.get("width", 512), CFG.get("height", 896), CFG.get("frames", 97)
NEG = "worst quality, inconsistent motion, blurry, jittery, distorted, deformed face, extra limbs, text, watermark"
for j in JOBS:
    out = os.path.join(OUT, j["name"] + ".mp4")
    if os.path.exists(out):
        continue
    t = time.time()
    try:
        src = f"/kaggle/working/{j['name']}.jpg"
        urllib.request.urlretrieve(j["image"], src)
        img = load_image(src).resize((W, H))
        kw = dict(prompt=j["motion"], negative_prompt=NEG, width=W, height=H, num_frames=NF,
                  num_inference_steps=CFG.get("steps", 8), guidance_scale=CFG.get("guidance", 1.0),
                  decode_timestep=0.05, decode_noise_scale=0.025,
                  generator=torch.Generator().manual_seed(j.get("seed", 7)), output_type="pil")
        if CFG["kind"] == "condition":
            kw["conditions"] = [LTXVideoCondition(image=img, frame_index=0)]
            kw["image_cond_noise_scale"] = 0.0
        else:
            kw["image"] = img
        if CFG.get("timesteps"):
            kw["timesteps"] = CFG["timesteps"]; kw.pop("num_inference_steps")
        frames = pipe(**kw).frames[0]
        export_to_video(frames, out, fps=24)
        log(f"clip {j['name']}: {time.time() - t:.0f}s")
    except Exception as e:
        log(f"clip {j['name']} FAILED: {e}")
        traceback.print_exc(file=LOG)
    if time.time() - t0 > CFG.get("budget_s", 3 * 3600):
        log("time budget reached"); break
log(f"done in {time.time() - t0:.0f}s")
