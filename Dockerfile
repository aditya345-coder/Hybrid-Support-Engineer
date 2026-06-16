FROM python:3.13-slim

WORKDIR /app

COPY backend/pyproject.toml backend/requirements.txt ./
RUN pip install --no-cache-dir -e ".[dev]"

COPY backend/src ./src

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
