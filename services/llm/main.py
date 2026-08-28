import json
import logging
import time
from typing import List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import verify_api_key
from model_loader import get_model_and_tokenizer
from router import route_document
from draft import generate_draft, summarize
import rag_connector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm")

app = FastAPI(title="LLM Service", version="1.0")

model = None
tokenizer = None


class LLMRequest(BaseModel):
    schemaVersion: str = "1.0"
    requestId: str
    documentId: str
    workflowId: str
    task: Literal["draft_reply", "route_document", "summarize"]
    prompt: str
    context: List[str] = Field(default_factory=list)


class LLMOutput(BaseModel):
    draft: str
    department: str
    confidence: float


class LLMResponse(BaseModel):
    schemaVersion: str = "1.0"
    requestId: str
    documentId: str
    workflowId: str
    output: LLMOutput
    model: Optional[str] = "jamba2-3b-turkish"


def log_event(request_id: str, document_id: str, workflow_id: str, task: str, error: Optional[str] = None):
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "service": "llm",
        "requestId": request_id,
        "documentId": document_id,
        "workflowId": workflow_id,
        "task": task,
    }
    if error:
        log_entry["error"] = error
    logger.info(json.dumps(log_entry, ensure_ascii=False))


@app.on_event("startup")
async def startup_event():
    global model, tokenizer
    try:
        model, tokenizer = get_model_and_tokenizer()
        logger.info(json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "service": "llm",
            "event": "model_loaded"
        }))
    except Exception as e:
        logger.error(json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "service": "llm",
            "error": f"model_load_failed: {str(e)}"
        }))
        raise


@app.post("/v1/generate", response_model=LLMResponse)
async def generate(request: LLMRequest, actor: str = Depends(verify_api_key)):
    if model is None or tokenizer is None:
        log_event(request.requestId, request.documentId, request.workflowId, request.task, "model_not_loaded")
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        routing = route_document(request.prompt, model, tokenizer)
        department, confidence = routing["department"], routing["confidence"]

        draft = ""
        if request.task == "draft_reply":
            context = request.context
            if not context:
                try:
                    rag_result = rag_connector.get_rag_context(request.prompt, actor=actor)
                    context = rag_result.get("context_snippets", [])
                except Exception as e:
                    log_event(request.requestId, request.documentId, request.workflowId, request.task, f"rag_failed: {str(e)}")
                    context = []
            draft = generate_draft(request.prompt, context, model, tokenizer)
        elif request.task == "summarize":
            draft = summarize(request.prompt, model, tokenizer)

        log_event(request.requestId, request.documentId, request.workflowId, request.task)
        return LLMResponse(
            schemaVersion="1.0",
            requestId=request.requestId,
            documentId=request.documentId,
            workflowId=request.workflowId,
            output=LLMOutput(
                draft=draft,
                department=department,
                confidence=confidence
            ),
            model="jamba2-3b-turkish"
        )
    except Exception as e:
        log_event(request.requestId, request.documentId, request.workflowId, request.task, f"generation_failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    if model is not None and tokenizer is not None:
        return {"status": "ready"}
    return JSONResponse(status_code=503, content={"status": "not_ready"})
