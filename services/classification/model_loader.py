import os
import logging
from typing import Tuple

# Air-gapped: set offline env vars BEFORE importing transformers/huggingface_hub
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

logger = logging.getLogger(__name__)

MODEL_ID = "serda-dev/Jamba2-3B-Turkish"
MODEL_REVISION = "9524af9e857e0359b8a3dad72bc216b65d3c0acd"

_model = None
_tokenizer = None


def get_model_and_tokenizer() -> Tuple[AutoModelForCausalLM, AutoTokenizer]:
    global _model, _tokenizer

    if _model is not None and _tokenizer is not None:
        return _model, _tokenizer

    device_map = "cuda:0" if torch.cuda.is_available() else "cpu"
    if device_map == "cpu":
        logger.warning("CUDA not available, falling back to CPU. Inference will be slow.")

    logger.info(f"Loading model '{MODEL_ID}' (revision={MODEL_REVISION}) on {device_map}...")
    _model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        dtype=torch.bfloat16,
        device_map=device_map,
        local_files_only=True,
    )
    _tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        local_files_only=True,
    )
    logger.info("Model and tokenizer loaded successfully.")
    return _model, _tokenizer
