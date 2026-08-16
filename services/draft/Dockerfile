FROM python:3.12-slim

WORKDIR /app

COPY services/draft /app/services/draft
COPY services/__init__.py /app/services/__init__.py

ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["python", "-m", "services.draft.server"]
