# Architecture Session — BX-12–BX-14 managed RAG corpus

> Consumes approved [BX-12–BX-14 requirements](../design/DESIGN_bd84424_rag_corpus.md). No new logical service is introduced.

## Data Models

### Entity: ExtractTextRequest

Traces to: BX-12, BX-13

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `file` | multipart binary part | bytes | Required; PDF or DOCX; `1..10,485,760` bytes. |
| `filename` | UTF-8 string | Unicode code points | Required; `1..255`; suffix must match MIME. |
| `content_type` | enum | — | Required; `application/pdf` or DOCX MIME. |
| `purpose` | enum | — | Required; `rag_source` or `case_attachment`; audit only. |

**Invariants:**

- The OCR service never creates a case, attachment, RAG source, or corpus chunk.
- A successful extraction returns normalized text only; the caller owns binary persistence and any downstream state.

**Boundary Behavior:**

- A non-PDF/DOCX file, MIME/suffix mismatch, empty file, or 10 MiB + 1 byte returns a validation error before OCR.
- A PDF with no extractable/OCR text, unreadable DOCX, or text under the existing 40-character intake minimum returns a controlled extraction failure; no caller state may publish.
- `purpose` is required and unknown values are rejected; it never changes OCR text.

**Concurrency / Race-Scenario Analysis:**

- Extraction requests are independent and contain no mutable OCR state. PaddleOCR and DOCX parsers load once per OCR process behind a bounded worker semaphore; overload returns a retryable busy error rather than consuming unbounded CPU/RAM.

### Entity: RagSource

Traces to: BX-12

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `source_id` | UUID | — | Primary key; generated once. |
| `revision` | positive integer | revisions | Starts at `1`; increments exactly once for each successful replacement. |
| `title` | UTF-8 string | Unicode code points | Required; `1..255`. |
| `filename` | UTF-8 string | Unicode code points | Required; `1..255`. |
| `content_type` | enum | — | PDF or DOCX MIME only. |
| `size_bytes` | integer | bytes | Required; `1..10,485,760`. |
| `storage_key` | relative POSIX path | — | Required; generated server-side below `RAG_STORAGE_ROOT`; never browser supplied. |
| `normalized_text` | PostgreSQL `text` | Unicode code points | Required after successful OCR; never empty. |
| `content_sha256` | lowercase hex string | SHA-256 digest | Required; 64 characters; identifies exact stored bytes. |
| `indexed_at` | `timestamptz` | UTC instant | Required; set only after all chunks/vectors commit. |
| `created_by`, `updated_by` | string | principal identity | Required; exactly `ADMIN` in the demo lane. |
| `created_at`, `updated_at` | `timestamptz` | UTC instant | Required; database generated. |

**Invariants:**

- A source is visible to retrieval only when its current revision has a complete, same-revision chunk set.
- Source bytes, normalized text, and chunks are permanently removed by RAG-source deletion. Existing immutable correspondence rows retain only their already-published citation snapshots; deleted bytes/text cannot be reconstructed from corpus storage.
- Case attachments never create `RagSource` rows implicitly.

**Boundary Behavior:**

- Add/replace is synchronous: OCR extraction, CPU embedding, byte write, source write, and chunk write must succeed before HTTP success.
- A failed write removes its temporary file and rolls back source/chunk changes. A malformed file is not stored.
- `GET` returns source metadata and normalized text to ADMIN; it never returns `storage_key`.

**Concurrency / Race-Scenario Analysis:**

- Replace/delete require quoted `If-Match` revision. A stale revision returns `412 RAG_SOURCE_REVISION_CONFLICT`; concurrent add is independent. Delete locks the source row, deletes chunks plus row in one transaction, then removes the stored file; a filesystem-removal failure is retried from a durable cleanup marker and never restores a searchable row.

### Entity: RagSourceChunk

Traces to: BX-12, BX-14

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `chunk_id` | UUID | — | Primary key; generated server-side. |
| `source_id` | UUID | — | Required foreign key to `RagSource`; cascade hard delete. |
| `source_revision` | positive integer | revisions | Must equal current source revision when searchable. |
| `ordinal` | non-negative integer | position | Unique with `(source_id, source_revision)`; starts at `0`. |
| `content` | PostgreSQL `text` | Unicode code points | Required; `1..3,000` after NFC normalization. |
| `embedding` | PostgreSQL `real[1024]` | normalized vector | Required; every element finite; L2 norm `1±0.001`. |
| `embedding_model`, `embedding_revision` | strings | model provenance | Required; exact current BGE-M3 pin. |

**Invariants:**

- Retrieval scores only active current-revision chunks and never loads `corpus.json` after managed corpus is enabled.
- Chunk content is a deterministic ordered partition of `normalized_text`; no chunk exceeds 3,000 characters and none is silently omitted.
- A source replacement deletes its prior chunks transactionally before its new revision becomes searchable.

**Boundary Behavior:**

- Empty normalized text produces no source/chunks and returns extraction failure.
- More than five qualifying chunks may be scored, but at most five pass to F-04; existing F-04 `0.60` relevance threshold and citation guards stay unchanged.
- An invalid vector dimension, NaN, or model-pin mismatch aborts publication rather than serving mixed embedding spaces.

**Concurrency / Race-Scenario Analysis:**

- CPU embedding happens before the short PostgreSQL write transaction. The transaction verifies the expected source revision, removes prior chunks on replacement, and inserts one complete new set; retrieval observes either old or new set, never a mix.

### Entity: CaseAttachmentLifecycle

Traces to: BX-13

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `attachment_id` | UUID | — | Existing primary key. |
| `storage_key` | relative POSIX path | — | Existing opaque key; server generated below `CASE_ATTACHMENT_STORAGE_ROOT`. |
| `deleted_at` | nullable `timestamptz` | UTC instant | Null while active; set exactly once on soft delete. |
| `deleted_by` | nullable string | principal identity | Null while active; exactly `ADMIN` when deleted. |

**Invariants:**

- Only ADMIN may soft-delete a case attachment. A normal case reader sees no delete control and receives `403` when calling the route.
- Soft-deleted attachments are excluded from current attachment lists, required-attachment checks, and download/read projections; their bytes and metadata remain retained.
- Case attachment state has no RAG admission effect.

**Boundary Behavior:**

- Upload reuses the same PDF/DOCX 10 MiB extraction limit. Existing metadata-only attachment registration remains contract-compatible; binary upload is an additive route.
- Delete is idempotent for the same ADMIN: a second delete returns the stored soft-delete projection. Unknown attachment/case returns `404`.

**Concurrency / Race-Scenario Analysis:**

- Delete locks the attachment row and changes active to deleted once. Upload and delete on the same attachment cannot race because an attachment ID is created only after its byte write succeeds.

## Technology / Design Decisions

### Decision: RAG ownership and vector storage

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| `workflow` + existing PostgreSQL `real[]` vectors + Python CPU cosine | Reuses durable DB, Compose topology, BGE-M3 artifact, and no extra service/GPU. | Exact scan is for bounded municipal corpus, not million-document search. | ✅ |
| Import standalone Qdrant `mevzuat-rag` package | Mature ingest/index features. | Adds a second topology, dependencies, remote-LLM defaults, and duplicate RAG ownership. | ❌ |
| Keep static `corpus.json` | No migration. | Cannot add/edit/delete sources. | ❌ |

**Why the first option:** It is smallest contract-first path, costs 0 GB GPU VRAM, and preserves F-04 ownership.

**Why not the second option:** The reviewed branch is reference material; wholesale import breaks local offline and service-boundary rules.

**Why not the third option:** It fails BX-12 lifecycle requirements.

### Decision: Binary persistence

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Named local Compose volume, server-generated relative keys, atomic temp-file rename | No new dependency; durable across container restart; supports hard/soft lifecycle. | Single-host scope. | ✅ |
| PostgreSQL bytea | Single transactional store. | Inflates DB/backups and duplicates file-storage responsibility. | ❌ |
| Object-storage service | Horizontal scale and external retention controls. | New service, credentials, and setup beyond approved simple local scope. | ❌ |

**Why the first option:** Local CoreAIgent already permits file/object storage adapters; a named volume is the minimum real adapter.

**Why not PostgreSQL bytea:** It turns case/RAG binary storage into database bloat without a required benefit.

**Why not object storage:** It adds unrequested infrastructure.

### Decision: PDF/DOCX text extraction

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| OCR-owned PaddleOCR PDF/raster extraction plus `python-docx` text extraction | Satisfies requested OCR boundary; handles scanned PDF and DOCX without a new service. | Adds CPU dependencies and bounded OCR work. | ✅ |
| Browser text extraction | Avoids server dependencies. | Trust boundary violation; inconsistent results; binary never reaches OCR. | ❌ |
| Upload bytes directly to `workflow` and parse there | Fewer HTTP calls. | Violates OCR service ownership and cross-service boundary rule. | ❌ |

**Why the first option:** `ocr` becomes the one conversion boundary; DOCX is text extraction within that boundary, not image OCR.

**Why not browser extraction:** The server needs authoritative normalized text and must not trust browser parsing.

**Why not workflow parsing:** It duplicates document conversion logic outside OCR.

### Decision: Publication and retrieval isolation

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Synchronous extract/embed/index then atomic current-revision swap | Matches add-button behavior; no partial searchable source. | Upload latency includes CPU work. | ✅ |
| Durable async indexing | Better upload responsiveness. | Contradicts requested immediate add behavior and adds queue/status UI. | ❌ |
| Expose source before indexing completes | Fastest acknowledgement. | Retrieval can observe missing/mixed corpus state. | ❌ |

**Why the first option:** User selected direct add and simple behavior.

**Why not async indexing:** It adds lifecycle states not requested.

**Why not early exposure:** It violates source/search consistency.

## Contract and Runtime Plan

- Add OCR `POST /v1/extract-text`: multipart file extraction request and JSON `text-extraction-result`; it does not alter `POST /v1/ocr` JSON intake semantics.
- Add workflow ADMIN routes: `GET`/`POST /rag-sources`, `GET`/`PUT`/`DELETE /rag-sources/{source_id}`. `POST`/`PUT` are multipart; `PUT`/`DELETE` require `If-Match`; all mutating responses return the new quoted `ETag`.
- Add workflow `POST /cases/{case_id}/attachments/upload` for real PDF/DOCX upload and `DELETE /cases/{case_id}/attachments/{attachment_id}` for ADMIN soft delete. Preserve existing metadata registration endpoint.
- Extend the manifest validator so `DELETE`, OCR extraction, RAG-source routes, and multipart media metadata remain contract-validated. Add request/result schemas for every new route; update mock behavior without presenting it as OCR/RAG.
- Mount `ocr-upload-tmp`, `workflow-rag-data`, and `workflow-attachment-data` named volumes only in real overlays. CPU OCR/retrieval is a real workflow closure change, never a mock claim.
- Replace F-04 `corpus.json` flattening with active `rag_source_chunks` lookup after the first managed source is published. Before that point, retain the versioned demo corpus as bootstrap fallback; no run may merge bootstrap and managed chunks.
- `correspondence_generations` continues to store published citation metadata. Hard deletion removes corpus source bytes/text/chunks, not immutable past generation records.

## Verification Plan

- Falsify MIME/suffix mismatch, 0 byte, 10 MiB, 10 MiB + 1, unreadable PDF/DOCX, under-40-character extraction, OCR overload, and no persisted source after failure.
- Falsify stale source edit/delete revisions, simultaneous replace/delete, temporary-file cleanup, hard source deletion, and no deleted chunk in retrieval.
- Falsify ADMIN-only source mutation and attachment delete, soft-delete list exclusion, binary upload storage-key non-disclosure, case-to-RAG non-admission, and existing metadata endpoint compatibility.
- Falsify BGE vector dimensions/norm/model-pin, current-revision chunk atomicity, top-five cap, 0.60 threshold, 5-second timeout, and zero-GPU configuration.
- Contract/mock changes run the required Docker mock suite; real OCR/workflow tests run the updated documented closure. Jamba download/container is never stopped by these checks.

## Architecture Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| AQ-115 | Is the approved five-second retrieval target measured after OCR/BGE warm-up on the minimum supported CPU, and what exact CPU is that? | solution-architect | Resolved | After OCR/BGE warm-up, measure on a modern four-core x86 CPU. (human operator, 2026-08-28) |
| AQ-116 | Which exact CPU-compatible PaddleOCR model artifact (repository, revision or digest, and cache location) is approved for scanned-PDF extraction? | senior-developer | Resolved | PaddlePaddle/PP-OCRv5_mobile_det@0d63e78e2b680928f6b1747d76a08db6e645efb7 plus PaddlePaddle/latin_PP-OCRv5_mobile_rec@ab2cd5cc5fa6309be2e5acdfe66eca2c2c127d57, preloaded below `/var/cache/paddleocr/hub`; CPU only. (human operator delegated selection, 2026-08-28) |
