FROM python:3.12-slim
WORKDIR /app
COPY tests/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY contracts /contracts
COPY scenarios /scenarios
COPY tests /app
ENTRYPOINT ["python", "/app/run_scenarios.py"]

