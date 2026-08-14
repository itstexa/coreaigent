FROM python:3.12-slim
WORKDIR /app
COPY mocks/server.py /app/server.py
COPY contracts /contracts
COPY scenarios /scenarios
ENV MOCK_SERVICE=ocr
EXPOSE 8080
CMD ["python", "/app/server.py"]

