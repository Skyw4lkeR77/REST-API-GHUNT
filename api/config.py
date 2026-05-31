import os
from typing import List

# ============================================================
# API Configuration
# ============================================================

# API Key for authentication. Change this in production!
# Can be overridden with environment variable GHUNT_API_KEY
API_SECRET_KEY: str = os.environ.get("GHUNT_API_KEY", "kypau201106")

# API versioning
API_VERSION: str = "1.0.0"
API_PREFIX: str = "/api/v1"

# CORS - list of allowed origins. Use ["*"] for all origins (not recommended in production)
ALLOWED_ORIGINS: List[str] = os.environ.get(
    "GHUNT_ALLOWED_ORIGINS", "*"
).split(",")

# Timeout for GHunt HTTP requests (in seconds)
REQUEST_TIMEOUT: int = int(os.environ.get("GHUNT_REQUEST_TIMEOUT", "30"))

# App metadata
APP_TITLE: str = "GHunt REST API"
APP_DESCRIPTION: str = (
    "REST API wrapper for GHunt - an offensive Google OSINT framework.\n\n"
    "## Authentication\n"
    "All endpoints (except `/health`) require the **`X-API-Key`** header.\n\n"
    "## Session\n"
    "GHunt must be authenticated before use. Use `POST /api/v1/session/setup` "
    "to upload credentials, or run `ghunt login` on the server."
)
APP_CONTACT: dict = {
    "name": "GHunt",
    "url": "https://github.com/mxrch/GHunt",
}
APP_LICENSE: dict = {
    "name": "AGPL-3.0",
    "url": "https://choosealicense.com/licenses/agpl-3.0/",
}
