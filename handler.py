"""Runpod Serverless handler for fishaudio/drama-3.

Starts `sgl-omni serve` on localhost once per worker, waits for /health, then
forwards each job's input to the server's OpenAI-compatible
POST /v1/audio/speech route and returns the audio base64-encoded.

Job input is the /v1/audio/speech request body, for example:

    {"input": "Hello there!", "response_format": "wav"}
    {"input": "[sighs] Fine.", "references": [{"audio_path": "https://...", "text": "..."}]}

`text` is accepted as an alias for `input`. Streaming is not supported through
the queue, so `stream` is always forced off.
"""

import base64
import os
import subprocess
import sys
import time

import requests
import runpod

MODEL_ID = os.environ.get("MODEL_ID", "fishaudio/drama-3")
HF_CACHE_ROOT = "/runpod-volume/huggingface-cache/hub"
PORT = int(os.environ.get("SGL_OMNI_PORT", "8000"))
BASE_URL = f"http://127.0.0.1:{PORT}"
STARTUP_TIMEOUT_S = int(os.environ.get("STARTUP_TIMEOUT_S", "1800"))
REQUEST_TIMEOUT_S = int(os.environ.get("REQUEST_TIMEOUT_S", "600"))
# Extra flags for `sgl-omni serve`, e.g. "--tts_engine.gpu_memory_fraction 0.85".
EXTRA_ARGS = os.environ.get("SGL_OMNI_EXTRA_ARGS", "").split()


def resolve_model_path(model_id: str) -> str:
    """Return the Runpod cached-model snapshot if present, else the HF repo id.

    With the endpoint's Model field set to the repo, Runpod stages the weights
    under HF_CACHE_ROOT before the worker starts. Without it, sgl-omni
    downloads the repo itself into the container's HF cache.
    """
    org, name = model_id.split("/", 1)
    model_root = os.path.join(HF_CACHE_ROOT, f"models--{org}--{name}")
    snapshots_dir = os.path.join(model_root, "snapshots")
    refs_main = os.path.join(model_root, "refs", "main")

    if os.path.isfile(refs_main):
        with open(refs_main) as f:
            candidate = os.path.join(snapshots_dir, f.read().strip())
        if os.path.isdir(candidate):
            return candidate

    if os.path.isdir(snapshots_dir):
        versions = sorted(
            d for d in os.listdir(snapshots_dir)
            if os.path.isdir(os.path.join(snapshots_dir, d))
        )
        if versions:
            return os.path.join(snapshots_dir, versions[-1])

    print(f"Cached model not found under {model_root}; downloading {model_id}.")
    return model_id


def start_server() -> subprocess.Popen:
    model_path = resolve_model_path(MODEL_ID)
    cmd = [
        "sgl-omni", "serve",
        "--model-path", model_path,
        "--model-name", MODEL_ID,
        "--host", "127.0.0.1",
        "--port", str(PORT),
        *EXTRA_ARGS,
    ]
    print("Launching:", " ".join(cmd))
    return subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)


def wait_until_healthy(proc: subprocess.Popen) -> None:
    deadline = time.time() + STARTUP_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"sgl-omni exited during startup with code {proc.returncode}")
        try:
            if requests.get(f"{BASE_URL}/health", timeout=5).status_code == 200:
                print("sgl-omni is healthy.")
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    raise TimeoutError(f"sgl-omni not healthy after {STARTUP_TIMEOUT_S}s")


server = start_server()
wait_until_healthy(server)


def handler(job):
    payload = dict(job["input"] or {})
    if "input" not in payload and "text" in payload:
        payload["input"] = payload.pop("text")
    if not payload.get("input"):
        return {"error": "Provide the text to speak in `input`."}
    payload["stream"] = False
    payload.setdefault("response_format", "wav")

    if server.poll() is not None:
        # Exit so Runpod replaces the worker instead of failing every job.
        runpod.serverless.progress_update(job, "sgl-omni server died")
        sys.exit(f"sgl-omni exited with code {server.returncode}")

    started = time.time()
    resp = requests.post(f"{BASE_URL}/v1/audio/speech", json=payload, timeout=REQUEST_TIMEOUT_S)
    if resp.status_code != 200:
        return {"error": f"sgl-omni returned HTTP {resp.status_code}", "detail": resp.text[:2000]}

    return {
        "audio_base64": base64.b64encode(resp.content).decode("ascii"),
        "format": payload["response_format"],
        "content_type": resp.headers.get("content-type"),
        "generation_seconds": round(time.time() - started, 3),
    }


runpod.serverless.start({"handler": handler})
