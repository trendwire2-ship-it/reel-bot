#!/usr/bin/env python3
"""Send image->video jobs to a free Kaggle GPU notebook (LTX-Video) and collect the clips.

usage: kaggle_clips.py jobs.json out_dir
  jobs.json: {"jobs": [{"name": "...", "image": "https://...jpg", "motion": "what moves", "seed": 7}], "cfg": {...}}
Needs KAGGLE_USERNAME and KAGGLE_KEY (an API token) in the environment.
"""
import json, os, shutil, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLUG = os.environ.get("KAGGLE_KERNEL", "reel-bot-clips")


def kaggle(*args, check=True):
    r = subprocess.run(["kaggle", *args], capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    if check and r.returncode != 0:
        raise RuntimeError(f"kaggle {' '.join(args)} failed: {out[-800:]}")
    return out


def run(jobs, cfg, out_dir, timeout_s=4 * 3600):
    user = os.environ["KAGGLE_USERNAME"]
    os.environ.setdefault("KAGGLE_API_TOKEN", os.environ.get("KAGGLE_KEY", ""))
    d = tempfile.mkdtemp()
    code = open(os.path.join(ROOT, "kaggle", "ltx_kernel.py")).read()
    code = code.replace("__JOBS__", json.dumps(jobs)).replace("__CFG__", json.dumps(cfg))
    open(os.path.join(d, "ltx_kernel.py"), "w").write(code)
    json.dump({"id": f"{user}/{SLUG}", "title": SLUG, "code_file": "ltx_kernel.py", "language": "python",
               "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
               "dataset_sources": [], "competition_sources": [],
               "kernel_sources": []}, open(os.path.join(d, "kernel-metadata.json"), "w"))
    print(kaggle("kernels", "push", "-p", d), flush=True)
    t0 = time.time()
    time.sleep(60)
    while True:
        st = kaggle("kernels", "status", f"{user}/{SLUG}", check=False)
        print(f"[{int(time.time() - t0)}s] {st}", flush=True)
        low = st.lower()
        if "complete" in low or "error" in low or "cancel" in low:
            break
        if time.time() - t0 > timeout_s:
            print("timed out waiting for Kaggle", flush=True)
            break
        time.sleep(60)
    tmp = tempfile.mkdtemp()
    print(kaggle("kernels", "output", f"{user}/{SLUG}", "-p", tmp, check=False)[-1500:], flush=True)
    os.makedirs(out_dir, exist_ok=True)
    got = []
    for root, _, files in os.walk(tmp):
        for f in files:
            if f.endswith(".mp4") or f == "log.txt":
                shutil.copy(os.path.join(root, f), os.path.join(out_dir, f))
                if f.endswith(".mp4"):
                    got.append(f[:-4])
    if os.path.exists(os.path.join(out_dir, "log.txt")):
        print(open(os.path.join(out_dir, "log.txt")).read()[-3000:], flush=True)
    return got


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))
    got = run(spec["jobs"], spec.get("cfg", {}), sys.argv[2])
    print("clips:", got)
