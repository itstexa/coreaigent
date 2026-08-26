import logging
import time
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from validate import validate_document as run_validation
from model_loader import get_model_and_tokenizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Validation Service")

model = None
tokenizer = None


class ClassificationResult(BaseModel):
    schemaVersion: str
    requestId: str
    documentId: str
    workflowId: str
    documentType: str
    classification: str
    extractedFields: Dict[str, Optional[str]]
    summary: Optional[str] = None


class ValidationResult(BaseModel):
    schemaVersion: str = "1.0"
    requestId: str
    documentId: str
    workflowId: str
    missingFields: List[str] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)


@app.on_event("startup")
async def startup_event():
    global model, tokenizer
    try:
        model, tokenizer = get_model_and_tokenizer()
        logger.info("Model and tokenizer loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load model: {str(e)}")
        raise


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    if model is not None and tokenizer is not None:
        return {"status": "ready"}
    raise HTTPException(status_code=503, detail="Model not loaded")


@app.post("/v1/validate")
async def validate_endpoint(request: ClassificationResult):
    log_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "service": "validation",
        "requestId": request.requestId,
        "documentId": request.documentId,
        "workflowId": request.workflowId,
    }

    try:
        source_text = request.extractedFields.get("source_text", "")
        result = run_validation(request.documentType, source_text, model, tokenizer)

        validation_result = ValidationResult(
            requestId=request.requestId,
            documentId=request.documentId,
            workflowId=request.workflowId,
            missingFields=result["missingFields"],
            conflicts=result["conflicts"],
        )

        logger.info(f"Validation completed", extra=log_data)
        return validation_result

    except Exception as e:
        log_data["error"] = "validation_error"
        logger.error(f"Validation failed: {str(e)}", extra=log_data)
        raise HTTPException(status_code=500, detail="Validation failed")
