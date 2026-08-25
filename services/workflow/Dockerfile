# Reuse the local Jamba runtime: it already contains the CUDA-compatible
# PyTorch version used by the model service.  Installing sentence-transformers
# on python:slim would otherwise download a second multi-gigabyte Torch stack.
FROM coreaigent/llm:jamba-local
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
