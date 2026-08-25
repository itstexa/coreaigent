"""Leased F-04 worker: local BGE-M3 retrieval then structured Jamba generation."""

from __future__ import annotations

import json
import os
import time
import urllib.request
import uuid
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from correspondence import NoSourceLegalClaimError, build_retrieval_context, extract_json_object, sanitize_text, semantic_repair_payload, validate_generated_draft
from app import ensure_schema

DATABASE_URL = os.environ["DATABASE_URL"]
LLM_URL = os.environ.get("JAMBA_URL", "http://llm:8080/generate")
BGE_MODEL_REVISION = os.environ.get("BGE_MODEL_REVISION", "5617a9f61b028005a4858fdac845db406aefb181")
LEASE_SECONDS = int(os.environ.get("WORKER_LEASE_SECONDS", "180"))
POLL_SECONDS = float(os.environ.get("WORKER_POLL_SECONDS", "0.2"))
_EMBEDDING_MODEL = None


def _load_json(name):
    return json.loads(Path(__file__).with_name(name).read_text(encoding="utf-8"))


def embedding_model():
    """Load the local BGE-M3 artifact once for retrieval and schema repair."""
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is not None:
        return _EMBEDDING_MODEL
    from sentence_transformers import SentenceTransformer

    # HF_HOME is the cache root; repositories themselves live in its `hub`
    # directory.  Passing the root makes SentenceTransformer search a second,
    # nonexistent cache layout when network access is intentionally disabled.
    cache_dir = str(Path(os.environ.get("HF_HOME", "/var/cache/huggingface")) / "hub")
    _EMBEDDING_MODEL = SentenceTransformer("BAAI/bge-m3", revision=BGE_MODEL_REVISION, cache_folder=cache_dir, local_files_only=True)
    return _EMBEDDING_MODEL


def retrieve(query):
    """Run the approved local-only BGE-M3 dense retrieval; no network fallback."""
    corpus = _load_json("corpus.json")
    model = embedding_model()
    chunks = [{**chunk, "source_id": source["source_id"], "title": source["title"], "source_type": source["source_type"], "official_source_url": source.get("official_source_url"), "corpus_version": corpus["corpus_version"]} for source in corpus["sources"] for chunk in source["chunks"]]
    vectors = model.encode([query] + [chunk["content"] for chunk in chunks], normalize_embeddings=True)
    query_vector = vectors[0]
    for chunk, vector in zip(chunks, vectors[1:]):
        chunk["score"] = float(query_vector @ vector)
    return build_retrieval_context(chunks)


def semantic_similarity(left, right):
    vectors = embedding_model().encode([left, right], normalize_embeddings=True)
    return float(vectors[0] @ vectors[1])


def claim():
    with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
        cur.execute("SELECT j.job_id,j.generation_id FROM correspondence_generation_jobs j WHERE j.state='pending' OR (j.state='claimed' AND j.claimed_until < now()) ORDER BY j.created_at FOR UPDATE SKIP LOCKED LIMIT 1")
        job = cur.fetchone()
        if not job:
            return None
        cur.execute("UPDATE correspondence_generation_jobs SET state='claimed',attempt_count=attempt_count+1,claimed_until=now()+(%s*interval '1 second'),updated_at=now() WHERE job_id=%s", (LEASE_SECONDS, job[0]))
        cur.execute("UPDATE correspondence_generations SET generation_status='processing' WHERE generation_id=%s AND generation_status='queued'", (job[1],))
        return job


def _semantic_fields(fields, policy):
    return {
        field_id: entry["value"]
        for field_id, entry in fields.items()
        if policy["fieldHandling"].get(field_id) == "task_required" and isinstance(entry, dict) and isinstance(entry.get("value"), str)
    }


def _prompt(*, row, semantic_fields, sanitized_document, chunks, repair_error=None):
    """Build the bounded, PII-minimized F-04 model instruction."""
    source_text = "\n".join(item["content"] for item in chunks)
    payload = {
        "request_type": row[2], "department": row[3], "unit": row[4],
        "validated_semantic_fields": semantic_fields,
        "case_content": sanitized_document[:6000],
        "retrieved_sources": [{"chunk_id": item["chunk_id"], "content": item["content"]} for item in chunks],
        "allowed_correspondence_types": ["response_letter", "information_letter", "referral_letter", "cover_letter", "other"],
    }
    source_rule = "Kullanılabilir kaynak yoktur. used_source_refs=[] döndür; taslak yalnız idari inceleme veya iletim ifadeleri içersin." if not chunks else "used_source_refs yalnızca retrieved_sources içindeki chunk_id değerleri olabilir."
    retry_rule = " Önceki yanıt kabul edilmedi: " + repair_error + "." if repair_error else ""
    return (
        "Türkçe resmî yazışma taslağı üret. Sadece tek bir JSON nesnesi döndür; markdown, açıklama veya başka anahtar ekleme. "
        "JSON nesnesini mutlaka kapat ve nesneden sonra yazmayı durdur. draft_text 2-4 kısa cümle ve en fazla 1200 karakter olsun. "
        "Zorunlu şema: document_summary(string, en fazla 600 karakter), recommended_correspondence_type(" 
        "response_letter|information_letter|referral_letter|cover_letter|other), draft_text(string, en fazla 6000 karakter), "
        "used_source_refs(string dizisi). other seçilirse correspondence_type_detail(string, en fazla 200 karakter) eklenebilir. "
        "Örnek biçim: {\"document_summary\":\"Kısa özet.\",\"recommended_correspondence_type\":\"information_letter\",\"draft_text\":\"Başvurunuz incelenecektir.\",\"used_source_refs\":[]}. "
        + source_rule + retry_rule + "\nGirdi:\n" + json.dumps(payload, ensure_ascii=False)
    )


def _invoke(prompt):
    request = urllib.request.Request(LLM_URL, data=json.dumps({"prompt": prompt}, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=185) as response:
        return json.load(response)


def _mark_pending(job_id):
    with psycopg.connect(DATABASE_URL) as db:
        db.execute("UPDATE correspondence_generation_jobs SET state='pending',claimed_until=NULL,updated_at=now() WHERE job_id=%s AND state='claimed'", (job_id,))


def _mark_failed(job, error_code, attempts):
    with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
        cur.execute("UPDATE correspondence_generations SET generation_status='failed',error_code=%s,model_attempt_count=%s,completed_at=now() WHERE generation_id=%s AND generation_status='processing'", (error_code, attempts, job[1]))
        cur.execute("UPDATE correspondence_generation_jobs SET state='completed',claimed_until=NULL,updated_at=now() WHERE job_id=%s", (job[0],))


def _mark_completed(job, source_status, output, chunks, model, attempts):
    citations = [{key: item[key] for key in ("source_id", "corpus_version", "title", "source_type", "locator", "chunk_id", "official_source_url", "excerpt", "score") if key in item} for item in chunks if item["chunk_id"] in output["used_source_refs"]]
    result_status = "draft_ready" if source_status == "relevant_source_found" else "review_required"
    with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
        cur.execute("UPDATE correspondence_generations SET generation_status='completed',source_status=%s,result_status=%s,correspondence_type=%s,correspondence_type_detail=%s,document_summary=%s,draft_text=%s,regulation_suggestions=%s,model_id=%s,model_revision=%s,model_attempt_count=%s,completed_at=now() WHERE generation_id=%s AND generation_status='processing'", (source_status, result_status, output["recommended_correspondence_type"], output.get("correspondence_type_detail"), output["document_summary"], output["draft_text"], Jsonb(citations), model.get("model"), model.get("modelRevision"), attempts, job[1]))
        cur.execute("SELECT case_id,source_case_revision FROM correspondence_generations WHERE generation_id=%s", (job[1],))
        case_id, revision = cur.fetchone()
        cur.execute("INSERT INTO routing_jobs (job_id,case_id,source_case_revision,source_generation_id,state) VALUES (%s,%s,%s,%s,'pending') ON CONFLICT (case_id,source_case_revision) DO NOTHING", (uuid.uuid4(), case_id, revision, job[1]))
        cur.execute("UPDATE correspondence_generation_jobs SET state='completed',claimed_until=NULL,updated_at=now() WHERE job_id=%s", (job[0],))


def run_once():
    job = claim()
    if not job:
        return False
    try:
        with psycopg.connect(DATABASE_URL) as db:
            row = db.execute("SELECT g.case_id,g.source_case_revision,g.request_type_id,g.department_label,g.unit_label,r.normalized_text,g.validated_fields FROM correspondence_generations g JOIN intake_records r USING(document_id) WHERE g.generation_id=%s", (job[1],)).fetchone()
        policy = _load_json("f04_pii_policy.json")
        fields = row[6] or {}
        known = {key: value["value"] for key, value in fields.items() if policy["fieldHandling"].get(key) == "redact" and isinstance(value, dict) and isinstance(value.get("value"), str)}
        sanitized = sanitize_text(row[5], known_values=known, field_handling=policy["fieldHandling"])
        source_status, chunks = retrieve(f"{row[2]} {row[3]} {row[4]} {_semantic_fields(fields, policy)}")
    except Exception:
        _mark_pending(job[0])
        return True

    refs = [chunk["chunk_id"] for chunk in chunks]
    repair_error = None
    for attempts in (1, 2):
        try:
            model = _invoke(_prompt(row=row, semantic_fields=_semantic_fields(fields, policy), sanitized_document=sanitized, chunks=chunks, repair_error=repair_error))
            try:
                output = validate_generated_draft(json.loads(model["response"]), refs, source_status)
            except NoSourceLegalClaimError:
                raise
            except (ValueError, json.JSONDecodeError):
                output = semantic_repair_payload(
                    extract_json_object(model["response"]),
                    retrieved_refs=refs,
                    source_status=source_status,
                    similarity=semantic_similarity,
                )
            _mark_completed(job, source_status, output, chunks, model, attempts)
            return True
        except Exception as exc:
            is_guard = exc.__class__.__name__ == "NoSourceLegalClaimError"
            error_code = "UNVERIFIED_LEGAL_CLAIM" if is_guard else "STRUCTURED_OUTPUT_INVALID"
            repair_error = str(exc) or error_code
    _mark_failed(job, error_code, 2)
    return True


if __name__ == "__main__":
    ensure_schema()
    while True:
        if not run_once():
            time.sleep(POLL_SECONDS)
