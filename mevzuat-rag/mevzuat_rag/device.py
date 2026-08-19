"""Central device resolution — the only place in this package allowed to
know about "cuda"/"mps"/"cpu" literals. Every model loader calls
``resolve_device()`` instead of hardcoding a device string, so the package
runs unchanged on a dev GPU box, an edge device, or a CPU-only server.
"""
from __future__ import annotations

import os


def resolve_device() -> str:
    """env DEVICE > CUDA > MPS > CPU, in that order."""
    env_device = os.environ.get("DEVICE")
    if env_device:
        return env_device

    try:
        import torch
    except ImportError:
        return "cpu"

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def resolve_dtype(device: str):
    """CUDA gets bf16 (falls back to fp16 if unsupported), everything else fp32."""
    import torch

    if device == "cuda":
        return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    return torch.float32
