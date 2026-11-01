# Runpod Serverless worker for fishaudio/drama-3 on SGLang-Omni.
#
# The base image is the same SGLang build upstream sglang-omni pins in its own
# docker/Dockerfile (torch 2.14 / CUDA 13). Model weights are NOT baked in:
# set the endpoint's Model field to fishaudio/drama-3 so Runpod caches them on
# the host at /runpod-volume/huggingface-cache (see handler.py).
ARG SGLANG_IMAGE=lmsysorg/sglang@sha256:5fc09edb6a0bb1d5b6992b543723c66d08f86d7a507e951e87e0d05db4ac766e
FROM ${SGLANG_IMAGE}

# sglang-omni commit the worker was written against (main, 2026-10-31).
ARG SGLANG_OMNI_COMMIT=e727710aa6a0b29cef7dc362155c350dae313f21

RUN apt-get update \
    && apt-get install -y --no-install-recommends sox \
    && rm -rf /var/lib/apt/lists/*

# Install sglang-omni's dependencies plus the fishaudio extra into the base
# image's /opt/sglang virtualenv, reusing upstream's protobuf override, then
# the package itself without letting it touch the pinned stack.
RUN git clone --filter=blob:none https://github.com/sgl-project/sglang-omni.git /opt/sglang-omni \
    && git -C /opt/sglang-omni checkout "${SGLANG_OMNI_COMMIT}" \
    && python3 -c 'import tomllib; print("\n".join(tomllib.load(open("/opt/sglang-omni/pyproject.toml", "rb"))["tool"]["uv"]["override-dependencies"]))' > /tmp/omni-overrides.txt \
    && uv pip install --python /opt/sglang/bin/python3 --no-build-isolation \
        --overrides /tmp/omni-overrides.txt -r /opt/sglang-omni/pyproject.toml \
        descript-audiotools==0.7.2 descript-audio-codec==1.0.0 \
    && uv pip install --python /opt/sglang/bin/python3 --no-deps --reinstall flashinfer-python==0.7.1 \
    && uv pip install --python /opt/sglang/bin/python3 --no-deps --no-build-isolation /opt/sglang-omni \
    && uv pip install --python /opt/sglang/bin/python3 "runpod>=1.12.0" requests \
    && rm /tmp/omni-overrides.txt

ENV FLASHINFER_WORKSPACE_BASE=/root \
    FLASHINFER_JIT_DEBUG=0 \
    LD_LIBRARY_PATH=/opt/sglang/lib/python3.12/site-packages/nvidia/nccl/lib:${LD_LIBRARY_PATH} \
    PYTHONUNBUFFERED=1 \
    MODEL_ID=fishaudio/drama-3

WORKDIR /app
COPY handler.py /app/handler.py

ENTRYPOINT []
CMD ["/opt/sglang/bin/python3", "-u", "/app/handler.py"]
