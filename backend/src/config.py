from __future__ import annotations

from pathlib import Path

# Central project paths (portable across machines).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DOCS_DIR = DATA_DIR / "raw_docs"
LOG_DIR = PROJECT_ROOT / "logs"
