FROM python:3.13-slim

WORKDIR /app

COPY backend/requirements.txt ./

# Install dependencies only (not the project package itself)
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code — used directly via PYTHONPATH
COPY backend/src ./src

# Make all modules under src/ importable as top-level names
# This matches the local development setup (src/ on sys.path)
ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["sh", "-c", "NEO4J_URI=${NEO4J_URI:-bolt://localhost:7687} NEO4J_USERNAME=${NEO4J_USERNAME:-neo4j} NEO4J_PASSWORD=${NEO4J_PASSWORD:-test} QDRANT_URL=${QDRANT_URL:-http://localhost:6333} REDIS_URL=${REDIS_URL:-redis://localhost:6379} uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} 2>&1"]
