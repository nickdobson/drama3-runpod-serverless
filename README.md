# drama3-runpod-serverless

Runpod Serverless (queue) worker for [fishaudio/drama-3](https://huggingface.co/fishaudio/drama-3),
served with [SGLang-Omni](https://github.com/sgl-project/sglang-omni). `handler.py` starts
`sgl-omni serve` on localhost and forwards each job to its `/v1/audio/speech` route.

## Endpoint settings

| Setting | Value | Why |
|---|---|---|
| Source | GitHub → this repo, branch `main`, Dockerfile `Dockerfile` | |
| Type | Queue | |
| GPU | 80 GB Hopper: H100 (`ADA_80_PRO`), H200 (`HOPPER_141`) as fallback | 37.0 GB of weights in the engine's 0.70 memory share needs ≥ 53 GB; plus the vocoder (0.10) and the 6 GiB preprocessing reserve |
| Min CUDA | 13.0 | base image is torch 2.14 / CUDA 13 |
| Model (cached models) | `fishaudio/drama-3` | 41.5 GB of weights staged on the host, not downloaded at boot |
| Container disk | 80 GB | only used if the cached model is missing and sgl-omni downloads it |
| Workers | min 0, max 1 | scale to zero |
| Execution timeout | 600 s | |
| FlashBoot | on | |

## Request

```bash
curl -s -X POST "https://api.runpod.ai/v2/$ENDPOINT_ID/runsync" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"input": {"input": "Hello, how are you?"}}' \
  | python -c "import sys,json,base64; open('out.wav','wb').write(base64.b64decode(json.load(sys.stdin)['output']['audio_base64']))"
```

`input` takes any `/v1/audio/speech` field: `input` (or `text`), `references`
(`[{"audio_path": "<url>", "text": "<transcript>"}]`, or `data` with base64 audio),
`response_format`, `temperature`, `top_p`, `top_k`, `max_new_tokens`, `seed`.
The output is `{"audio_base64", "format", "content_type", "generation_seconds"}`.

## Worker env (optional)

- `SGL_OMNI_EXTRA_ARGS`: extra `sgl-omni serve` flags, e.g. `--tts_engine.gpu_memory_fraction 0.85`
- `STARTUP_TIMEOUT_S` (default 1800), `REQUEST_TIMEOUT_S` (default 600)
- `MODEL_ID`: set to `fishaudio/drama-3-int4` (and the Model field to match) to fit a 48 GB card
