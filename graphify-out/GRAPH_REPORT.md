# Graph Report - .  (2026-08-27)

## Corpus Check
- 114 files · ~56,765 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 842 nodes · 2065 edges · 29 communities detected
- Extraction: 49% EXTRACTED · 51% INFERRED · 0% AMBIGUOUS · INFERRED: 1059 edges (avg confidence: 0.65)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]

## God Nodes (most connected - your core abstractions)
1. `RAGEngine` - 96 edges
2. `RAGConfig` - 71 edges
3. `LegislationChunk` - 58 edges
4. `StructureAwareChunker` - 56 edges
5. `PipelineContext` - 52 edges
6. `QdrantStore` - 51 edges
7. `ChunkMetadata` - 45 edges
8. `RetrievalResult` - 42 edges
9. `run()` - 33 edges
10. `parse_legislation_text()` - 33 edges

## Surprising Connections (you probably didn't know these)
- `run_pipeline()` --calls--> `extract_pdf_text()`  [INFERRED]
  services/workflow/pipeline.py → mevzuat-rag/mevzuat_rag/ingestion/pdf_corpus.py
- `get_rag_context()` --calls--> `run()`  [INFERRED]
  services/llm/rag_connector.py → mevzuat-rag/mevzuat_rag/eval/run_hard_negative_eval.py
- `ocr_endpoint()` --calls--> `extract_pdf_text()`  [INFERRED]
  services/ocr/main.py → mevzuat-rag/mevzuat_rag/ingestion/pdf_corpus.py
- `call()` --calls--> `request()`  [INFERRED]
  tests/run_scenarios.py → mocks/server.py
- `error_contract()` --calls--> `request()`  [INFERRED]
  tests/run_scenarios.py → mocks/server.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (82): Candidate, from_result(), CitationExpansionStage, [9] Atıf Genişletme (GraphRAG-lite) — [4] Parent Document Retrieval'den sonra, h, CompressionStage, _cosine(), _dedup(), _extractive_select() (+74 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (79): main(), CLI: ask a question, get a DeepSeek-generated answer grounded in retrieved mevzu, log_query(), [Güvenlik] Audit log — kim/ne zaman/ne sordu/hangi maddeler döndü kaydı.  Kamu e, Append-only — asla üzerine yazmaz, asla silmez., _citation(), _source_hash(), StructureAwareChunker (+71 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (55): best_result(), _build_parser(), build_synthetic_corpus(), calibrate(), extract_madde_texts(), is_oom_error(), main(), parse_batch_sizes() (+47 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (41): _build_parser(), main(), [5] Güvenlik — PII redaksiyonu sonrası veri saklama/silme politikası.  Uygulamas, model(), store(), _build_parser(), _human_bytes(), main() (+33 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (43): BaseModel, _build_prompt(), classify_document(), _match_turkce_tur(), _dedupe_repetition(), generate_draft(), Greedy decode bazen aynı cümleyi döngüsel tekrar eder; ilk tekrardan     sonrası, summarize() (+35 more)

### Community 5 - "Community 5"
Cohesion: 0.07
Nodes (40): Candidate — the unit that flows through the retrieval pipeline stages.  Wraps a, Turns a parsed LegislationDocument into citation-carrying chunks.  Invariant: a, _build_context(), Grounded answer generation over retrieved legislation chunks, via DeepSeek's Ope, _infer_mevzuat_turu(), _looks_like_table_line(), Parses Turkish legislation text into a Madde/Fıkra/Bent tree.  Turkish mevzuat t, kanun_adi başlığındaki anahtar kelimeye göre mevzuat türünü heuristik     olarak (+32 more)

### Community 6 - "Community 6"
Cohesion: 0.06
Nodes (40): AgentReachWebConnector, Agent-Reach-modeled generic ingestion backend.  github.com/Panniantong/Agent-Rea, IngestionConnector, Common interface every ingestion backend implements.  Chunking/embedding/indexin, RawDocument, SourceRef, load_offline_docs(), _parse_fixture() (+32 more)

### Community 7 - "Community 7"
Cohesion: 0.12
Nodes (29): _fake_critic_response(), main(), Hakem Ajan (Critic Agent) demo — kasıtlı olarak uydurma bir cevabı, gerçek indek, _parse_critic_verdict(), PostHocVerifyStage, [8] Hakem Ajan (Critic Agent) — [7] Generate'in ürettiği cevabı, kullanıcıya gös, Cevapta geçip sources listesinde karşılığı olmayan atıf indekslerini     döndürü, Hakem Ajan: üretilen cevabı verilen bağlamla karşılaştırıp     ``{"is_valid": bo (+21 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (21): NormalizeTextGeneralTests, NormalizeTextProfileTests, Unit tests for mevzuat_rag.text_norm.  All cases are pure functions; no model, n, _ascii_fold(), _dehyphenate(), _normalize_quotes(), normalize_text(), _normalize_unicode() (+13 more)

### Community 9 - "Community 9"
Cohesion: 0.12
Nodes (28): _bool_env(), CitationExpansionConfig, CompressionConfig, CRAGConfig, _deep_merge(), GenerationConfig, HybridConfig, HyDEConfig (+20 more)

### Community 10 - "Community 10"
Cohesion: 0.12
Nodes (24): append_history(), Retrieval eval sonuçları için kalıcı geçmiş kaydı.  docs/IMPROVEMENT_IDEAS.md'de, ``result`` (``run_retrieval_eval.run()``'ın döndürdüğü sözlük) içindeki     ``su, ``logs/eval_history.jsonl``'daki kayıtları dosyadaki sırayla (en     eskiden en, read_history(), _build_parser(), _fmt_cell(), format_table() (+16 more)

### Community 11 - "Community 11"
Cohesion: 0.12
Nodes (13): BM25Index, In-memory BM25 sparse index sharing the same chunk_id space as the dense Qdrant, _corpus_fingerprint(), _now_stamp(), _percentile(), run(), watch(), _write_json() (+5 more)

### Community 12 - "Community 12"
Cohesion: 0.15
Nodes (17): BaseHTTPRequestHandler, assert_mock(), call(), document(), error_contract(), main(), run(), valid() (+9 more)

### Community 13 - "Community 13"
Cohesion: 0.16
Nodes (16): [7] PII Redaksiyon — kimlik/iletişim bilgilerini LLM'e/vektör deposuna ulaşmadan, Resmi TCKN algoritması (bkz. Nüfus ve Vatandaşlık İşleri Genel Müdürlüğü     for, Sırasıyla IBAN, e-posta, telefon, TCKN — bu sıra önemli: IBAN/e-posta     kendi, redact_pii(), RedactionResult, _tckn_checksum_valid(), [7] PII Redaksiyon testleri.  TCKN test sabitleri (12345678950, 11111111110, 987, test_email_redacted() (+8 more)

### Community 14 - "Community 14"
Cohesion: 0.2
Nodes (14): extract_same_kanun_refs(), [9] Atıf tespiti — chunk metninde geçen madde-madde çapraz atıfları regex ile bu, Metinde geçen madde numaralarını döndürür — kendi madde numarasını     (kendine, [9] citation_ref.py testleri — hem sentetik hem gerçek corpus cümlesiyle., test_abbreviated_and_full_form_together(), test_abbreviated_forms_m_dot_number(), test_abbreviated_self_reference_excluded(), test_empty_text() (+6 more)

### Community 15 - "Community 15"
Cohesion: 0.21
Nodes (13): mrr(), precision_at_k(), Retrieval quality metrics — pure functions, no framework dependency., K adet getirilen doküman içindeki doğru doküman sayısı / K., recall_at_k(), _count_madde(), _madde_key(), _render_pdf() (+5 more)

### Community 16 - "Community 16"
Cohesion: 0.33
Nodes (6): _min_max_normalize(), [2] Rank fusion for Hybrid Retrieve — RRF (default) or weighted score fusion, bo, alpha=1.0 => pure dense/vector, alpha=0.0 => pure BM25. Both inputs     are min-, RRF: score(id) = sum over lists of 1 / (k + rank), rank 1-indexed., reciprocal_rank_fusion(), weighted_fusion()

### Community 17 - "Community 17"
Cohesion: 0.4
Nodes (0): 

### Community 18 - "Community 18"
Cohesion: 1.0
Nodes (0): 

### Community 19 - "Community 19"
Cohesion: 1.0
Nodes (0): 

### Community 20 - "Community 20"
Cohesion: 1.0
Nodes (0): 

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (0): 

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (1): Backward-compatible alias — existing code calls this directly.

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (0): 

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (0): 

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (0): 

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (0): 

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **53 isolated node(s):** `Greedy decode bazen aynı cümleyi döngüsel tekrar eder; ilk tekrardan     sonrası`, `Deterministic, contract-shaped HTTP mocks; intentionally stdlib-only.`, `The contracts use only this small JSON Schema subset; full checks run in tests.`, `eval_history.py + eval_trend_report.py testleri.  docs/IMPROVEMENT_IDEAS.md'deki`, `Scriptin gerçekten `python scripts/eval_trend_report.py` olarak     çalıştırılab` (+48 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 18`** (2 nodes): `validate_contracts.py`, `main()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 19`** (2 nodes): `extract_pdf_text()`, `pdf_extract.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 20`** (1 nodes): `required_fields.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 21`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (1 nodes): `Backward-compatible alias — existing code calls this directly.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `RAGEngine` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 5`, `Community 7`, `Community 11`, `Community 15`?**
  _High betweenness centrality (0.278) - this node is a cross-community bridge._
- **Why does `run()` connect `Community 7` to `Community 0`, `Community 1`, `Community 3`, `Community 4`, `Community 10`?**
  _High betweenness centrality (0.188) - this node is a cross-community bridge._
- **Why does `RAGConfig` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 5`, `Community 9`?**
  _High betweenness centrality (0.131) - this node is a cross-community bridge._
- **Are the 88 inferred relationships involving `RAGEngine` (e.g. with `Yürürlük durumu (mülga/değişik) takibi testleri.  sample_data/legislation/ içind` and `Bir fıkra max_tokens'ı aşınca chunker'ın AYRI (flush()'tan farklı)     ChunkMeta`) actually correct?**
  _`RAGEngine` has 88 INFERRED edges - model-reasoned connections that need verification._
- **Are the 70 inferred relationships involving `RAGConfig` (e.g. with `Yürürlük durumu (mülga/değişik) takibi testleri.  sample_data/legislation/ içind` and `Bir fıkra max_tokens'ı aşınca chunker'ın AYRI (flush()'tan farklı)     ChunkMeta`) actually correct?**
  _`RAGConfig` has 70 INFERRED edges - model-reasoned connections that need verification._
- **Are the 57 inferred relationships involving `LegislationChunk` (e.g. with `Yürürlük durumu (mülga/değişik) takibi testleri.  sample_data/legislation/ içind` and `Bir fıkra max_tokens'ı aşınca chunker'ın AYRI (flush()'tan farklı)     ChunkMeta`) actually correct?**
  _`LegislationChunk` has 57 INFERRED edges - model-reasoned connections that need verification._
- **Are the 53 inferred relationships involving `StructureAwareChunker` (e.g. with `Yürürlük durumu (mülga/değişik) takibi testleri.  sample_data/legislation/ içind` and `Bir fıkra max_tokens'ı aşınca chunker'ın AYRI (flush()'tan farklı)     ChunkMeta`) actually correct?**
  _`StructureAwareChunker` has 53 INFERRED edges - model-reasoned connections that need verification._