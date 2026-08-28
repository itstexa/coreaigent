"""Hakem Ajan (Critic Agent) demo — kasıtlı olarak uydurma bir cevabı, gerçek
indekslenmiş korpustan çekilen gerçek kaynak parçalarına karşı verify_answer()
ile denetler ve sonucu CLI'ye basar.

    python -m scripts.demo_hakem_agent

Gerçek bir DEEPSEEK_API_KEY yoksa (401), bunu açıkça raporlar ve mock'lu
davranışı gösterir — sessizce başarılıymış gibi davranmaz.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.pipeline.stages.post_hoc_verify import verify_answer

QUERY = "Dilekçeye idari makamlar kaç gün içinde cevap vermek zorundadır?"
# Kasıtlı halüsinasyon: 3071 sayılı Kanun'da böyle bir süre YOK (Kanun'da
# yalnızca TBMM Dilekçe Komisyonu için 60 günlük süre var, madde 8) — burada
# uydurma bir "15 gün" rakamı ve var olmayan bir madde numarası üretiliyor.
HALLUCINATED_ANSWER = (
    "3071 sayılı Dilekçe Hakkının Kullanılmasına Dair Kanun'un 12. maddesine "
    "göre, idari makamlar kendilerine yapılan dilekçelere en geç 15 gün "
    "içinde cevap vermek zorundadır [1]."
)


def _fake_critic_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    return response


def main() -> None:
    print(f"SORU: {QUERY}")
    print(f"ÜRETILEN (kasıtlı uydurma) CEVAP: {HALLUCINATED_ANSWER}\n")

    engine = RAGEngine()
    hits = engine.retrieve(QUERY, top_k=3, actor="demo:demo_hakem_agent")
    chunks = [{"citation": h.chunk.citation, "text": h.chunk.text} for h in hits]
    print(f"Gerçek indeksten çekilen {len(chunks)} kaynak parça:")
    for c in chunks:
        print(f"  - [{c['citation']}] {c['text'][:80]}...")
    print()

    try:
        verdict = verify_answer(HALLUCINATED_ANSWER, chunks)
        print("[GERÇEK DeepSeek API çağrısı başarılı]")
    except Exception as exc:
        print(f"[GERÇEK DeepSeek API çağrısı BAŞARISIZ: {exc}]")
        print("[.env'deki DEEPSEEK_API_KEY geçersiz/401 — Hakem Ajan mantığı mock'lu client ile gösteriliyor]\n")
        import json

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _fake_critic_response(
            json.dumps({
                "is_valid": False,
                "reason": "Kaynakta (3071 sayılı Kanun) 'idari makamların 15 gün içinde cevap vermesi' veya 'madde 12' diye bir hüküm yok — cevap uydurma.",
            })
        )
        verdict = verify_answer(HALLUCINATED_ANSWER, chunks, client=mock_client)

    print(f"HAKEM AJAN KARARI: is_valid={verdict['is_valid']}")
    print(f"GEREKÇE: {verdict['reason']}\n")

    if not verdict["is_valid"]:
        from mevzuat_rag.pipeline.stages.post_hoc_verify import HAKEM_BLOCKED_TEXT
        print("--- KULLANICIYA GİDECEK NİHAİ CEVAP (Hakem Ajan tarafından engellendi) ---")
        print(HAKEM_BLOCKED_TEXT)
    else:
        print("--- KULLANICIYA GİDECEK NİHAİ CEVAP (Hakem Ajan onayladı) ---")
        print(HALLUCINATED_ANSWER)


if __name__ == "__main__":
    main()
