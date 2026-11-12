"""Generate the validated 60-image, 240-second final proof in one POST."""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import aiimg, local_resources, oneshot
from tools.run_kheops_campaign import build_workflow, code_hash, sha256, save, LEGACY_MARKER, LEGACY_MARKER_SHA256

FOLDER = ROOT / "outputs/kheops_final_240_2026-11-10"
DENSITY = ROOT / "outputs/text_diagnostics/kheops_240_density.json"
PLANS = ROOT / "outputs/text_diagnostics/kheops_240_image_plans.json"
SERVER = "http://127.0.0.1:8188"
SEEDS = tuple(range(73001, 73061))

def main():
    import requests
    from PIL import Image
    if FOLDER.exists(): raise RuntimeError("Final 240 folder already exists")
    density, plans = json.loads(DENSITY.read_text(encoding="utf-8")), json.loads(PLANS.read_text(encoding="utf-8"))
    if not density["image_schedule"]["selection_accepted"] or not plans["accepted"]: raise RuntimeError("Planning gate failed")
    workflow = build_workflow(plans["image_plans"], SEEDS)
    FOLDER.mkdir()
    current = code_hash()
    result = subprocess.run([sys.executable,"-m","unittest","discover","-s","tests"], cwd=ROOT,
                            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding="utf-8",errors="replace")
    (FOLDER/"final_tests.log").write_text(result.stdout,encoding="utf-8")
    if result.returncode or code_hash()!=current: raise RuntimeError("Tests or code stability gate failed")
    plan={"code_hash":current,"expected_images":60,"seeds":list(SEEDS),"workflow":workflow,
          "graph_sha256":oneshot.graph_hash(workflow),"density_sha256":sha256(DENSITY),
          "plans_sha256":sha256(PLANS),"visual_plan_fingerprint":plans.get("distinct_prompts"),
          "legacy_marker_sha256_before":sha256(LEGACY_MARKER)}
    save(FOLDER/"plan.json",plan)
    posts=0
    def preflight():
        if code_hash()!=current or sha256(LEGACY_MARKER)!=LEGACY_MARKER_SHA256: raise RuntimeError("Integrity gate failed")
        q=requests.get(SERVER+"/queue",timeout=5);q.raise_for_status()
        if q.json().get("queue_running") or q.json().get("queue_pending"): raise RuntimeError("ComfyUI busy")
        info=requests.get(SERVER+"/object_info",timeout=30);info.raise_for_status(); data=info.json()
        for node,field,name in (("UNETLoader","unet_name",aiimg.QWEN_TURBO_UNET),("CLIPLoader","clip_name",aiimg.QWEN_TURBO_CLIP),("VAELoader","vae_name",aiimg.QWEN_TURBO_VAE)):
            if name not in data[node]["input"]["required"][field][0]: raise RuntimeError("Missing component "+name)
    def submit(payload,client_id):
        nonlocal posts;posts+=1
        if posts!=1: raise RuntimeError("Second POST forbidden")
        return requests.post(SERVER+"/prompt",json={"prompt":payload,"client_id":client_id},timeout=30)
    def history(pid):
        r=requests.get(SERVER+"/history/"+pid,timeout=30);r.raise_for_status();return r.json()
    def download(image):
        r=requests.get(SERVER+"/view",params=image,timeout=30);r.raise_for_status();return r.content
    execution=oneshot.run(FOLDER,seed=SEEDS[0],preflight={"mode":"final_240_one_post","code_hash":current,
        "visual_plan_fingerprint":str(plans["distinct_prompts"]),"expected_images":60,"max_prompt_posts":1,
        "legacy_marker_sha256":LEGACY_MARKER_SHA256},workflow=workflow,preflight_check=preflight,
        submit=submit,history=history,download=download,max_polls=1800,poll_interval=2,
        image_size=lambda p:list(Image.open(p).size),expected_image_size=(720,1280),
        validate_execution=lambda executed: (_ for _ in ()).throw(ValueError("Graph mismatch")) if executed!=workflow else None,
        render_phase=local_resources.render_phase(comfy_url=SERVER,required_components=(aiimg.QWEN_TURBO_UNET,aiimg.QWEN_TURBO_CLIP,aiimg.QWEN_TURBO_VAE)))
    post={"prompt_post_count":posts,"legacy_marker_unchanged":sha256(LEGACY_MARKER)==LEGACY_MARKER_SHA256,"accepted":None}
    save(FOLDER/"postconditions.json",post)
    print(json.dumps({"status":execution.get("execution_status"),"images":execution.get("image_count"),**post}))
    return 0 if execution.get("execution_status")=="succeeded" and execution.get("image_count")==60 else 2
if __name__=="__main__": raise SystemExit(main())
