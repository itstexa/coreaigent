import json
import logging
import os
import time
import uuid
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from model_loader import get_model_and_tokenizer
from pipeline import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("workflow")

app = FastAPI(title="Workflow Orchestrator")

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))

model = None
tokenizer = None

# workflowId -> {"status": "processing"|"completed", "result": dict|None}
JOBS: Dict[str, dict] = {}


class DocumentInput(BaseModel):
    schemaVersion: str = "1.0"
    requestId: str
    documentId: str
    scenarioId: str
    contentType: str
    content: Optional[str] = None
    fileName: Optional[str] = None
    source: str = "test"


class WorkflowStep(BaseModel):
    service: str
    status: str
    timestamp: str


class WorkflowResult(BaseModel):
    schemaVersion: str = "1.0"
    requestId: str
    documentId: str
    workflowId: str
    status: str
    documentType: str
    department: str
    draft: str
    missingFields: List[str] = []
    conflicts: List[str] = []
    summary: Optional[str] = None
    confidence: Optional[float] = None
    steps: List[WorkflowStep]
    error: Optional[dict] = None


def _log(correlation_id: str, event: str, error: Optional[str] = None):
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "service": "workflow",
        "correlationId": correlation_id,
        "event": event,
    }
    if error:
        entry["error"] = error
    logger.info(json.dumps(entry, ensure_ascii=False))


@app.on_event("startup")
async def startup_event():
    global model, tokenizer
    model, tokenizer = get_model_and_tokenizer()
    _log("startup", "model_loaded")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    if model is not None and tokenizer is not None:
        return {"status": "ready"}
    raise HTTPException(status_code=503, detail="Model not loaded")


def _execute(document_input: dict, workflow_id: str) -> dict:
    _log(workflow_id, "pipeline_start")
    try:
        result = run_pipeline(document_input, workflow_id, model, tokenizer)
    except Exception as exc:
        _log(workflow_id, "pipeline_crashed", error=str(exc))
        result = {
            "schemaVersion": "1.0",
            "requestId": document_input["requestId"],
            "documentId": document_input["documentId"],
            "workflowId": workflow_id,
            "status": "manual_review",
            "documentType": "unsupported",
            "department": "manual_review",
            "draft": "",
            "steps": [{"service": "workflow", "status": "failed", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}],
            "error": {"step": "workflow", "message": str(exc)},
        }
    _log(workflow_id, "pipeline_end")
    return result


@app.post("/v1/workflows/document", response_model=WorkflowResult)
async def workflow_document(request: DocumentInput):
    workflow_id = request.requestId
    result = _execute(request.model_dump(), workflow_id)
    return result


@app.post("/upload")
async def upload(request: DocumentInput):
    workflow_id = str(uuid.uuid4())
    JOBS[workflow_id] = {"status": "processing", "result": None}
    _log(workflow_id, "upload_received")

    result = _execute(request.model_dump(), workflow_id)
    JOBS[workflow_id] = {"status": "completed", "result": result}

    return {"workflowId": workflow_id, "status": "completed"}


@app.get("/status/{workflow_id}")
async def status(workflow_id: str):
    job = JOBS.get(workflow_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Bilinmeyen workflowId")
    return {"workflowId": workflow_id, "status": job["status"]}


@app.get("/result/{workflow_id}", response_model=WorkflowResult)
async def result(workflow_id: str):
    job = JOBS.get(workflow_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Bilinmeyen workflowId")
    if job["status"] != "completed" or job["result"] is None:
        raise HTTPException(status_code=425, detail="Henüz hazır değil")
    return job["result"]
