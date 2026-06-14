# Hybrid Support Agent

An agentic AI system designed to act as a support engineer for any GitHub repository. It uses a **Hybrid GraphRAG** approach, combining semantic documentation search (Qdrant) with historical issue/bug relationship mapping (Neo4j) to provide grounded, cited answers.

---

## 🏗️ Architecture Overview

The system follows a multi-layered agentic architecture built with **LangGraph**:

1.  **The Ingestion Pipeline (ETL):**
    *   **Vector DB (Qdrant):** Stores embeddings of the repository docs with feature tags and a `neo4j_id` bridge.
    *   **Graph DB (Neo4j):** Stores `Issue` and `Feature` nodes linked by `AFFECTS` relationships.
2.  **The Agentic Core:**
    *   **Analyzer:** Identifies the relevant feature/component in the user query.
    *   **Hybrid Retriever:** Queries Qdrant and, when possible, Neo4j using the doc feature bridge or detected feature.
    *   **Critic Node:** Verifies grounding and retries retrieval up to 3 times if hallucination is detected.
3.  **Interaction Layer:**
    *   **FastAPI Backend:** Orchestrates the LangGraph state machine.
    *   **React Frontend:** Chat interface on Vercel that formats citations and links GitHub issues.
    *   **Auth0:** GitHub social login with JWT validation on the backend.

---

## 🚀 Setup Instructions

### 1. Prerequisites
*   Python 3.13+
*   [Neo4j](https://neo4j.com/cloud/aura24/) Aura Account (required)
*   [Qdrant](https://qdrant.tech/) Account (optional; in-memory fallback exists)
*   [Groq](https://console.groq.com/) API Key (default model via LiteLLM)
*   OpenAI API Key (optional, only for evaluation via RAGAS)

### 2. Clone and Install
```bash
git clone https://github.com/your-username/The-Knowledge-Graph-Support-Engineer.git
cd The-Knowledge-Graph-Support-Engineer

# Install dependencies
pip install -e .
```

### 3. Environment Configuration
Create a `.env` file in the root directory (see `.env.example`) and populate it with your keys:
```env
# LLM
LLM_MODEL=groq/llama-3.1-8b-instant
GROQ_API_KEY=your_groq_key

# Logging
LOG_LEVEL=INFO
# Local only: write logs to file (stdout always enabled)
LOG_TO_FILE=true
LOG_FILE=logs/app.log

# Qdrant
QDRANT_URL=your_qdrant_url
QDRANT_API_KEY=your_qdrant_api_key

# Neo4j
NEO4J_URI=neo4j+s://your_instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password

# GitHub (for ingestion)
GITHUB_TOKEN=your_github_pat
# Set to any GitHub repo (owner/name). This example uses FastAPI.
TARGET_REPO=tiangolo/fastapi

# Evaluation (optional)
OPENAI_API_KEY=your_openai_key
```

---

## 🛠️ How to Run

### Phase 1: Ingest Data (Do this once)
First, populate your databases with the documentation and GitHub issues:
```bash
# Ingest Documentation into Qdrant
python src/ingestion/docs_loader.py

# Ingest GitHub Issues into Neo4j (last 20 closed issues)
python src/ingestion/github_loader.py
```

### Phase 2: Start the System
You need to run both the backend API and the frontend UI:

1.  **Start the Backend API:**
    ```bash
    python src/main.py
    ```
2.  **Start the React Frontend (dev mode):**
    ```bash
    cd frontend
    cmd /c npm install    # first time only
    cmd /c npm run dev    # Vite dev server on :5173
    ```

Notes:
- Neo4j configuration is required; the app will error if it is missing.

### Phase 3: (Optional) Run Evaluation
```bash
python src/evaluation/evaluate.py
```

---

## 📺 Demo
*A video demo or screenshot gallery will be placed here soon.*

---

## 🛡️ Key Features
*   **Grounded Answers With Citations:** Responses require `[Source: ...]` tags and the UI formats links to GitHub issues.
*   **Hybrid Retrieval:** Qdrant doc chunks plus Neo4j issues, bridged by `neo4j_id` or detected feature.
*   **Verification Loop:** The LangGraph critic retries retrieval up to 3 times when hallucination is detected.
*   **Evaluation Harness:** RAGAS-based evaluation using `src/evaluation/golden_dataset.json`.
