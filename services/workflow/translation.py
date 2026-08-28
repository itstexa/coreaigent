"""Pinned, offline Turkish/English translation for Jamba-facing wording."""

from __future__ import annotations

import os
import re
from pathlib import Path


MODEL_SPECS = {
    ("tr", "en"): ("Helsinki-NLP/opus-mt-tc-big-tr-en", "2261c8fc7b1af59caee87f8ff0ecf3fbccfe8391"),
    ("en", "tr"): ("Helsinki-NLP/opus-mt-tc-big-en-tr", "e539fc16a8a1a0ea5950eb339b595bfcce990e90"),
}
_MODELS = {}
MAX_CHUNK_CHARACTERS = 900


class TranslationUnavailable(RuntimeError):
    pass


def _chunks(text: str):
    """Keep Marian inputs bounded without dropping a sentence."""
    chunks, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text.strip()):
        if not sentence:
            continue
        if len(sentence) > MAX_CHUNK_CHARACTERS:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(sentence[index:index + MAX_CHUNK_CHARACTERS] for index in range(0, len(sentence), MAX_CHUNK_CHARACTERS))
            continue
        if current and len(current) + len(sentence) + 1 > MAX_CHUNK_CHARACTERS:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks or [text]


def _model(source_language: str, target_language: str):
    key = (source_language, target_language)
    if key not in MODEL_SPECS:
        raise TranslationUnavailable(f"Unsupported translation pair: {source_language}->{target_language}")
    if key not in _MODELS:
        model_id, revision = MODEL_SPECS[key]
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            cache_dir = Path(os.environ.get("HF_HOME", "/var/cache/huggingface"))
            tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision, cache_dir=str(cache_dir), local_files_only=True)
            model = AutoModelForSeq2SeqLM.from_pretrained(model_id, revision=revision, cache_dir=str(cache_dir), local_files_only=True)
            model.eval()
        except Exception as exc:  # model artifacts are prepared before an offline run
            raise TranslationUnavailable(f"Local translation model is unavailable: {model_id}") from exc
        _MODELS[key] = (tokenizer, model)
    return _MODELS[key]


def translate(text: str, source_language: str | None, target_language: str) -> str:
    """Translate human-readable wording only; callers retain schema keys and IDs."""
    source_language = source_language or "tr"
    if not isinstance(text, str) or not text.strip() or source_language == target_language:
        return text
    tokenizer, model = _model(source_language, target_language)
    translated = []
    try:
        for chunk in _chunks(text):
            encoded = tokenizer(chunk, return_tensors="pt", truncation=True, max_length=512)
            output = model.generate(**encoded, num_beams=4, max_new_tokens=512, early_stopping=True)
            translated.append(tokenizer.decode(output[0], skip_special_tokens=True).strip())
    except Exception as exc:
        raise TranslationUnavailable("Local translation generation failed") from exc
    return "\n".join(part for part in translated if part)
