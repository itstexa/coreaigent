import logging
import time
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from classify import classify_document
from model_loader import get_model_and_tokenizer

logger = logging.getLogger("classification")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Classification Service")

model = None
tokenizer = None


class OCRResult(BaseModel):
    schemaVersion: str
    requestId: str
    documentId: str
    workflowId: str
    text: str
    language: str = "tr"
    confidence: float = Field(ge=0.0, le=1.0)
    pages: Optional[int] = None
    warnings: List[str] = []


class ClassificationResult(BaseModel):
    schemaVersion: str
    requestId: str
    documentId: str
    workflowId: str
    documentType: str
    classification: str
    extractedFields: dict
    summary: Optional[str] = None


def log_request(request: OCRResult, error: Optional[str] = None):
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "service": "classification",
        "requestId": request.requestId,
        "documentId": request.documentId,
        "workflowId": request.workflowId,
    }
    if error:
        log_entry["error"] = error
    logger.info(log_entry)


@app.on_event("startup")
async def load_model():
    global model, tokenizer
    try:
        model, tokenizer = get_model_and_tokenizer()
        logger.info("Model loaded successfully")
    except Exception as e:
        logger.error(f"Model loading failed: {str(e)}")
        raise


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    if model is not None and tokenizer is not None:
        return {"status": "ready"}
    raise HTTPException(status_code=503, detail="Model not loaded")


@app.post("/v1/classify", response_model=ClassificationResult)
async def classify(request: OCRResult):
    try:
        if model is None or tokenizer is None:
            raise HTTPException(status_code=503, detail="Model not loaded")

        classification_output = classify_document(request.text, model, tokenizer)

        result = ClassificationResult(
            schemaVersion="1.0",
            requestId=request.requestId,
            documentId=request.documentId,
            workflowId=request.workflowId,
            documentType=classification_output["documentType"],
            classification=classification_output["classification"],
            extractedFields=classification_output["extractedFields"],
            summary=classification_output["summary"],
        )
        log_request(request)
        return result
    except HTTPException:
        log_request(request, error="model_not_loaded")
        raise
    except Exception as e:
        log_request(request, error=f"classification_failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Classification failed")
