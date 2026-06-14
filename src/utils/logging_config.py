import logging
import os

from settings import settings


def setup_logging(name: str | None = None) -> logging.Logger:
    """Configure and return a logger for the given module name."""
    log_level = settings.LOG_LEVEL.upper()
    log_file = os.path.abspath(settings.LOG_FILE)
    log_to_file = settings.LOG_TO_FILE
    is_hosted = bool(os.getenv("VERCEL") or os.getenv("RENDER"))
    if log_to_file and not is_hosted:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

    root = logging.getLogger()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")

    root.setLevel(log_level)

    # Add handlers only if they don't already exist. Frameworks like uvicorn/streamlit
    # pre-configure root handlers, so we must not rely on `not root.handlers`.
    has_stream = any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    if not has_stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    if log_to_file and not is_hosted:
        has_file = any(
            isinstance(h, logging.FileHandler)
            and os.path.abspath(getattr(h, "baseFilename", "")) == log_file
            for h in root.handlers
        )
        if not has_file:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
    return logging.getLogger(name)
