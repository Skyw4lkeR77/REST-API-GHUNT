"""
passenger_wsgi.py - Entry point for Phusion Passenger (DirectAdmin)

This file is loaded by Phusion Passenger to serve the GHunt REST API.
Place this file in your domain's document root (e.g. public_html/).

Requirements:
- Python 3.10+ installed on the server
- Virtual environment with all dependencies installed (see install.sh)
- PASSENGER_PYTHON must point to the venv's python executable (set in .htaccess)
- GHunt credentials must be configured (run: ghunt login, or use /api/v1/session/setup)
"""

import sys
import os

# Add the project root to the Python path so 'api' and 'ghunt' packages are importable
sys.path.insert(0, os.path.dirname(__file__))

# Import the FastAPI app as 'application' - Passenger requires this exact variable name
from api.main import app

# Wrap FastAPI (ASGI) with a synchronous WSGI adapter for Passenger compatibility
# Passenger supports WSGI; we bridge FastAPI (ASGI) using asgiref
try:
    from asgiref.wsgi import WsgiToAsgi
    # Actually, we need the reverse: ASGI->WSGI. Use a2wsgi for that.
    raise ImportError("Using a2wsgi instead")
except ImportError:
    pass

try:
    from a2wsgi import ASGIMiddleware
    application = ASGIMiddleware(app)
except ImportError:
    # Fallback: use uvicorn's WSGI wrapper if available
    # If neither is available, Passenger with ASGI support can use 'app' directly
    # (some DirectAdmin setups support ASGI via gunicorn + uvicorn workers)
    application = app
