#!/bin/bash
# ============================================================
# install.sh - GHunt REST API Server Setup Script
# ============================================================
# Run this on your DirectAdmin/Linux server to install GHunt
# and its REST API dependencies.
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
#
# Requirements: Python 3.10+, pip, git
# ============================================================

set -e

# --- Config ---
VENV_DIR="$HOME/ghunt_venv"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================="
echo "  GHunt REST API - Server Installation"
echo "============================================="
echo "Project: $PROJECT_DIR"
echo "Virtualenv: $VENV_DIR"
echo ""

# 1. Check Python version
PYTHON_BIN=$(which python3.11 || which python3.10 || which python3)
PYTHON_VERSION=$($PYTHON_BIN --version 2>&1)
echo "[*] Using Python: $PYTHON_VERSION at $PYTHON_BIN"

if $PYTHON_BIN -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"; then
    echo "[+] Python 3.10+ OK"
else
    echo "[-] Python 3.10 or higher is required. Exiting."
    exit 1
fi

# 2. Create virtualenv
echo ""
echo "[*] Creating virtualenv at $VENV_DIR ..."
$PYTHON_BIN -m venv "$VENV_DIR"
echo "[+] Virtualenv created."

VENV_PIP="$VENV_DIR/bin/pip"
VENV_PYTHON="$VENV_DIR/bin/python3"

# 3. Upgrade pip
echo ""
echo "[*] Upgrading pip..."
$VENV_PIP install --upgrade pip --quiet

# 4. Install GHunt dependencies
echo ""
echo "[*] Installing GHunt dependencies..."
cd "$PROJECT_DIR"
$VENV_PIP install -e . --quiet
echo "[+] GHunt installed."

# 5. Install API extra dependencies
echo ""
echo "[*] Installing REST API dependencies (FastAPI, Uvicorn, etc.)..."
$VENV_PIP install -r requirements_api.txt --quiet
echo "[+] API dependencies installed."

# 6. Set API key (prompt user)
echo ""
echo "============================================="
echo "  API Key Configuration"
echo "============================================="
echo "The API is protected by an API key."
echo "Set your API key via environment variable:"
echo ""
echo "  export GHUNT_API_KEY=\"your-secret-key-here\""
echo ""
echo "Or edit api/config.py and change API_SECRET_KEY."
echo ""

# 7. Update .htaccess USERNAME
echo "============================================="
echo "  .htaccess Configuration"
echo "============================================="
USERNAME=$(whoami)
echo "[*] Detected server username: $USERNAME"
echo "[*] Updating .htaccess with your username..."
if [ -f "$PROJECT_DIR/.htaccess" ]; then
    sed -i "s|/home/USERNAME|/home/$USERNAME|g" "$PROJECT_DIR/.htaccess"
    sed -i "s|PassengerPython /home/$USERNAME/ghunt_venv/bin/python3|PassengerPython $VENV_PYTHON|g" "$PROJECT_DIR/.htaccess"
    echo "[+] .htaccess updated."
else
    echo "[!] .htaccess not found, skipping."
fi

# 8. GHunt Login
echo ""
echo "============================================="
echo "  GHunt Authentication"
echo "============================================="
echo "[*] You need to authenticate GHunt before using the API."
echo ""
echo "Option A: Run the interactive login now:"
echo "  $VENV_DIR/bin/ghunt login"
echo ""
echo "Option B: Use the REST API endpoint after starting the server:"
echo "  POST /api/v1/session/setup"
echo "  Body: {\"credentials\": \"<base64 from GHunt Companion>\"}"
echo ""
read -p "Do you want to run 'ghunt login' now? (y/N) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    "$VENV_DIR/bin/ghunt" login
fi

# 9. Done
echo ""
echo "============================================="
echo "  Installation Complete!"
echo "============================================="
echo ""
echo "To run locally (development):"
echo "  $VENV_PYTHON -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "For DirectAdmin:"
echo "  1. Copy these files to your domain's public_html/"
echo "  2. Ensure .htaccess PassengerPython points to: $VENV_PYTHON"
echo "  3. Set GHUNT_API_KEY env var in DirectAdmin or edit api/config.py"
echo "  4. Restart PHP/Passenger via DirectAdmin panel"
echo ""
echo "API Docs will be available at: http://yourdomain.com/docs"
echo ""
