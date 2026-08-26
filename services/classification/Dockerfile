FROM python:3.12-slim

# CUDA runtime host'tan --gpus all ile sağlanacaktır (air-gapped ortam, internet erişimi yok)
WORKDIR /app

# Sistem bağımlılıkları (transformers için gerekli olabilecekler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python bağımlılıkları
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodu
COPY model_loader.py .
COPY classify.py .
COPY main.py .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
