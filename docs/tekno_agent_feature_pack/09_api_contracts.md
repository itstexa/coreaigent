# Ortak Backend Kontratları - Stabilizasyon Spec'i

Bu dosya implementation code değildir. Architect'in repo standardına göre OpenAPI/JSON Schema'ya çevireceği minimum domain kontratlarını tanımlar.

## 1. Document Intake

Request anlamı:

```json
{
  "document_id": "optional-client-id",
  "source_type": "text|ocr",
  "text": "...",
  "source_metadata": {},
  "correlation_id": "optional"
}
```

Response anlamı:

```json
{
  "document_id": "doc-...",
  "case_id": "case-...",
  "ingest_status": "accepted|queued",
  "warnings": []
}
```

## 2. Classification Result

```json
{
  "schemaVersion": "3.0",
  "requestId": "...",
  "documentId": "...",
  "workflowId": "...",
  "department": {"id": "...", "label": "..."},
  "unit": {"id": "...", "label": "..."},
  "requestType": {"id": "...", "label": "..."},
  "confidence": 0.0,
  "taxonomyVersion": "...",
  "classifierVersion": "...",
  "classificationReason": "...",
  "status": "classified|needs_review"
}
```

`confidence > 0.80` ise `classified` döner. Eşik ve altındaki geçerli en iyi
zincir `needs_review` olarak provisional gösterilir; hiç eşleşme yoksa üç
hiyerarşi alanı `null` olur. `topCandidates` ve `unclassified` bu kontratta
yoktur.

## 3. Extraction / Missing Information

```json
{
  "schemaVersion": "3.0",
  "requestId": "...",
  "documentId": "...",
  "caseId": "...",
  "workflowId": "...",
  "requestTypeId": "...",
  "schemaVersionUsed": "demo-belediyesi-fields-v1",
  "extractedFields": [
    {"id": "field-id", "label": "Türkçe alan", "value": "...", "confidence": 0.0}
  ],
  "missingRequiredFields": [
    {"id": "...", "label": "..."}
  ],
  "invalidFields": [],
  "completionStatus": "complete|missing_information|invalid_information",
  "userActionRequired": true
}
```

## 4. User Supplemental Information

```json
{
  "fields": {"field-id": "new value"}
}
```

Bu body sadece `PATCH /cases/{case_id}/supplemental-information` için
kullanılır. İstek `Authorization: Bearer <token>`, `Idempotency-Key: <uuid>`
ve `If-Match: "<current_revision>"` gerektirir. Backend veriyi mevcut case'e
atomik merge eder, F-03 validation'ı yeniden çalıştırır ve `ETag` ile current
validation-result v3 döndürür. Public sonuç evidence/span/provenance veya raw
source text içermez.

## 5. Correspondence Result

```json
{
  "case_id": "case-...",
  "generation_id": "generation-...",
  "case_revision": 4,
  "generation_status": "completed",
  "source_status": "relevant_source_found",
  "result_status": "draft_ready",
  "corpus_version": "demo-municipality-regulations-v1",
  "document_summary": "...",
  "recommended_correspondence_type": "response_letter",
  "correspondence_type_detail": null,
  "draft_text": "...",
  "regulation_suggestions": [
    {"source_id":"REG-002","corpus_version":"demo-municipality-regulations-v1","title":"5393 sayılı Belediye Kanunu","source_type":"law","locator":"Madde ...","chunk_id":"REG-002-chunk-014"}
  ]
}
```

Queued veya processing okuması yalnız `case_id`, `case_revision` ve
`generation_status` döner. Failed okuması `generation_id`,
`generation_status: failed` ve `error_code` döndürür; partial draft dönmez.
Bu endpoint case-level authorization gerektirir; history listesi değil current
generation pointer'ını okur.

## 6. Routing + Notification Status

```json
{
  "case_id": "case-...",
  "routing": {
    "target_department_id": "...",
    "target_unit_id": "...",
    "status": "routed|pending_review|failed"
  },
  "notifications": {
    "user": {"status": "generated|pending|failed", "text": "..."},
    "unit": {"status": "generated|pending|failed", "text": "..."}
  }
}
```

## 7. Case Status

```json
{
  "case_id": "case-...",
  "state": "waiting_for_user|ready_for_processing|completed|failed|...",
  "current_step": "...",
  "last_error": null,
  "updated_at": "..."
}
```

## Contract kuralları

- Stable id ile görünen label ayrılmalıdır.
- `case_id` uçtan uca correlation anahtarıdır.
- Hata response'ları `{code, message, details?, correlation_id}` benzeri tutarlı bir envelope kullanmalıdır.
- Internal model promptu, stack trace ve hassas config client response'una sızmamalıdır.
- Contract değişiklikleri version control altında ve contract testleriyle korunmalıdır.

## Repository eşlemesi

- Ortak generation kontratı `POST /v1/generate` olarak sabittir.
- Jamba'nın minimal model endpoint'i `POST /generate` bunun yanında bulunur.
  Public cross-service adapter `/v1/generate`dir; F-03 extraction ile F-04/F-05
  durable worker'ları kendi structured-output doğrulamasını yaptığı kontrollü
  internal çağrıda `/generate` kullanır.
- Gerçek Jamba response'unda routing kararı üretilemez; adapter güvenli
  başlangıç değeri olarak `department=manual_review` ve `confidence=0.0`
  döndürür. Nihai department/unit kararı classification ve workflow state'inden
  gelir.
- `GET /health` liveness, `GET /ready` model readiness'tir; health başarılı
  diye generation hazır kabul edilmez.
- Mock Compose endpoint'leri şemaları doğrulamak içindir; gerçek servislerin
  yalnızca mock'a özgü scenario lookup davranışını kopyalaması yasaktır.
