import re
from typing import Optional

from utils.logging_config import setup_logging

logger = setup_logging(__name__)

SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


def validate_session_id(session_id: str) -> Optional[str]:
    """Validate session ID to prevent path traversal attacks.
    
    Args:
        session_id: The session ID to validate.
        
    Returns:
        The validated session ID if valid, None otherwise.
    """
    if not session_id:
        return None
    
    if not SESSION_ID_PATTERN.match(session_id):
        logger.warning(
            "Invalid session_id format",
            extra={"session_id": session_id[:50]},
        )
        return None
    
    return session_id


def sanitize_llm_input(text: str) -> str:
    """Sanitize user input to prevent prompt injection attacks."""
    if not text:
        return ""
    # Limit length to 2000 characters
    text = text[:2000]
    # Replace newlines with spaces to avoid line breaks in prompt
    text = text.replace('\n', ' ').replace('\r', ' ')
    # Remove any control characters (ASCII 0-31 except space)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    # Collapse multiple spaces
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()