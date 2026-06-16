FROM python:3.13-slim

WORKDIR /app

COPY backend/pyproject.toml backend/requirements.txt ./
RUN pip install --no-cache-dir -e ".[dev]"

COPY backend/src ./src

EXPOSE 8000

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
