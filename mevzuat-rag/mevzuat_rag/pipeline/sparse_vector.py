"""Metni Qdrant native sparse vector'e çevirir — BM25'in artık RAM'de
``rank_bm25.BM25Okapi`` ile değil, Qdrant'ın kendi sparse index'inde
(``Modifier.IDF``) yaşamasını sağlayan katman.

Denetim bulgusu: eski BM25Index tüm korpusu ``scroll_all_chunks()`` ile
belleğe çekip yeniden kuruyordu — kendi docstring'i "a few thousand chunks
at most" diyordu, 1M-dosya hedefiyle doğrudan çelişiyordu (bkz.
rag_config_panel.py madde 4). Bu modül, o sınırı ortadan kaldırır: her
chunk'ın sparse vektörü upsert anında hesaplanıp Qdrant'a yazılır, index
disk-backed ve kalıcıdır, hiçbir "tüm korpusu RAM'e yükle" adımı yoktur.

Token->indeks eşlemesi (hashing trick): sabit bir vocabulary dosyası
tutmuyoruz — her token'ın crc32 hash'i sparse vektör indeksi olarak
kullanılıyor. Bu, artan/streaming ingestion'ı (bkz. ingestion/pdf_corpus.py)
sorunsuz destekler (yeni bir token için önceden "kayıt" gerekmez) ama
teorik bir çakışma (collision) riski taşır — 2^31 alanda, hukuki bir
korpusun gerçekçi kelime dağarcığı (~onlarca bin benzersiz kök) için bu risk
ihmal edilebilir düzeyde kalır (aynı teknik scikit-learn'ün
``HashingVectorizer``'ında da kullanılır).

IDF ağırlığı burada HESAPLANMIYOR: ham terim sayıları (raw term counts)
yazılıyor, IDF'i Qdrant'ın kendisi sunucu tarafında, koleksiyonun GÜNCEL
istatistiklerine göre (``Modifier.IDF``) uyguluyor — bu yüzden korpus
büyüdükçe IDF sürekli güncel kalır, ayrı bir "IDF'i yeniden hesapla" işine
gerek kalmaz.
"""
from __future__ import annotations

import zlib
from collections import Counter

from qdrant_client.models import SparseVector

from mevzuat_rag.pipeline.tokenize_tr import tokenize

_HASH_SPACE = 0x7FFFFFFF  # Qdrant sparse indeksleri unsigned; pozitif 31-bit alan yeterli


def _token_to_index(token: str) -> int:
    return zlib.crc32(token.encode("utf-8")) & _HASH_SPACE


def text_to_sparse_vector(text: str) -> SparseVector:
    """Metni ham terim-sayısı sparse vektörüne çevirir (IDF uygulanmaz —
    bkz. modül docstring'i). Boş/tokenize edilemeyen metin için boş
    ``SparseVector`` döner (Qdrant boş indices/values listesini kabul eder)."""
    tokens = tokenize(text)
    counts = Counter(_token_to_index(t) for t in tokens)
    indices = list(counts.keys())
    values = [float(v) for v in counts.values()]
    return SparseVector(indices=indices, values=values)
