FROM python:3.13-slim

WORKDIR /app

COPY backend/src ./src
COPY backend/pyproject.toml ./

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
