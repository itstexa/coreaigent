FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/var/cache/huggingface \
    TRANSFORMERS_CACHE=/var/cache/huggingface/transformers \
    HUGGINGFACE_HUB_CACHE=/var/cache/huggingface/hub \
    TOKENIZERS_PARALLELISM=false \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gcc \
    git \
    git-lfs \
    tini \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt \
 && python -m pip install --no-cache-dir packaging ninja \
 && CXX11_ABI=$(python -c 'import torch; print("TRUE" if torch._C._GLIBCXX_USE_CXX11_ABI else "FALSE")') \
 && PYTHON_TAG=$(python -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")') \
 && python -m pip install --no-cache-dir \
      "https://github.com/state-spaces/mamba/releases/download/v2.2.4/mamba_ssm-2.2.4+cu12torch2.5cxx11abi${CXX11_ABI}-${PYTHON_TAG}-${PYTHON_TAG}-linux_x86_64.whl" \
      "https://github.com/Dao-AILab/causal-conv1d/releases/download/v1.5.0.post8/causal_conv1d-1.5.0.post8+cu12torch2.5cxx11abi${CXX11_ABI}-${PYTHON_TAG}-${PYTHON_TAG}-linux_x86_64.whl" \
 && python - <<'PY'
import causal_conv1d, mamba_ssm, torch
assert torch.__version__.startswith("2.5.1")
print("Jamba CUDA dependencies imported")
PY

COPY app.py /app/app.py
RUN mkdir -p /var/cache/huggingface

EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --retries=12 \
  CMD curl --fail http://127.0.0.1:8080/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
