"""Grounded answer generation over retrieved legislation chunks, via DeepSeek's
OpenAI-compatible chat completions API (https://api.deepseek.com).

Embedding stays BGE-M3/Qdrant (deliberately unchanged elsewhere in this
package) — DeepSeek has no public embeddings endpoint, so it is used only
for the generation step: turning retrieved chunks into a cited, grounded
answer in Turkish.
"""
from __future__ import annotations

import os

from openai import OpenAI

from mevzuat_rag.errors import GenerationError
from mevzuat_rag.models import RetrievalResult

SYSTEM_PROMPT = (
    "Sen bir Türk mevzuatı asistanısın. Sana verilen mevzuat parçalarına "
    "SIKI SIKIYA bağlı kal. Yalnızca verilen parçalarda geçen bilgiyle "
    "cevap ver, parçalarda olmayan hiçbir bilgiyi uydurma veya varsayma. "
    "Her iddianı, hangi parçaya dayandığını [1], [2] gibi referanslarla "
    "işaretleyerek belirt. Verilen parçalar soruyu cevaplamaya yetmiyorsa, "
    "açıkça 'Verilen mevzuat parçalarında bu sorunun cevabı yok.' de — "
    "tahmin yürütme."
)


def _client(api_key: str | None = None, base_url: str | None = None) -> OpenAI:
    return OpenAI(
        api_key=api_key or os.environ.get("DEEPSEEK_API_KEY"),
        base_url=base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    )


def _build_context(chunks: list[RetrievalResult]) -> str:
    parts = []
    for i, hit in enumerate(chunks, start=1):
        parts.append(f"[{i}] ({hit.chunk.citation})\n{hit.chunk.text}")
    return "\n\n".join(parts)


def generate_answer(
    query: str,
    chunks: list[RetrievalResult],
    model: str = "deepseek-chat",
    temperature: float = 0.0,
    max_tokens: int = 800,
    client: OpenAI | None = None,
) -> dict:
    """Returns {"answer": str, "citations": [chunk.citation, ...]}.

    temperature=0.0 by default — this is a legal-citation task where
    consistency/faithfulness matters far more than creative variation.
    """
    if not chunks:
        return {"answer": "Verilen mevzuat parçalarında bu sorunun cevabı yok.", "citations": []}

    client = client or _client()
    context = _build_context(chunks)
    user_prompt = f"Soru: {query}\n\nMevzuat parçaları:\n{context}\n\nYukarıdaki parçalara dayanarak soruyu cevapla."

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as exc:
        raise GenerationError(f"DeepSeek generation failed: {exc}") from exc

    answer_text = response.choices[0].message.content
    return {"answer": answer_text, "citations": [hit.chunk.citation for hit in chunks]}
