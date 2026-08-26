# Build context bu Dockerfile'ın kendi dizini DEĞİL, repo kökü olmalı
# (çünkü workflow, ocr/classification/validation/llm servislerinin modüllerini
# doğrudan import ediyor): docker build -f services/workflow/Dockerfile .
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-tur \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/workflow/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/workflow/*.py ./
COPY services/ocr/pdf_extract.py services/ocr/ocr_scan.py ./
COPY services/classification/classify.py ./
COPY services/validation/validate.py services/validation/rule_checks.py services/validation/llm_checks.py services/validation/required_fields.py ./
COPY services/llm/router.py services/llm/draft.py services/llm/rag_connector.py ./

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
