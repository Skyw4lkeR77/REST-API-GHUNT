from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from api.config import API_SECRET_KEY

# API Key scheme - reads from header X-API-Key
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    FastAPI dependency that validates the X-API-Key header.
    Returns the key if valid, raises 403 if missing or invalid.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing API key. Provide it via the X-API-Key header.",
        )
    if api_key != API_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )
    return api_key
