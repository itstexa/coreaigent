# sentence-transformers needs a Torch runtime for BGE-M3 embedding.  The CUDA
# lane's llm image already carries one, so that closure can reuse it by passing
# BASE_IMAGE=coreaigent/llm:jamba-local.  The default base stays self-contained,
# because the GGUF lane's llm image deliberately ships no Torch at all and this
# service never touches a GPU: the CPU-only wheel is all the embedding needs.
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
