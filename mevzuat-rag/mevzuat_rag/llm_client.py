"""Shared DeepSeek (OpenAI-compatible) client factory — used by every stage
that makes an LLM call (generation, multi-query, HyDE, and later router/CRAG).
"""
from __future__ import annotations

import os

from openai import OpenAI


def get_client(api_key: str | None = None, base_url: str | None = None) -> OpenAI:
    return OpenAI(
        api_key=api_key or os.environ.get("DEEPSEEK_API_KEY"),
        base_url=base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    )
