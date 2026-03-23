import base64
import json
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.helpers.auth import verify_api_key
from ghunt.helpers.utils import get_httpx_client
from ghunt.objects.base import GHuntCreds
from ghunt.errors import GHuntInvalidSession
from ghunt.helpers import auth as ghunt_auth

router = APIRouter(prefix="/session", tags=["Session"])


class SetupRequest(BaseModel):
    """
    Credentials from GHunt Companion extension (base64 encoded JSON).
    The base64 string should decode to: {"oauth_token": "oauth2_4/..."}
    OR {"master_token": "aas_et/..."}
    """
    credentials: Optional[str] = None
    master_token: Optional[str] = None
    oauth_token: Optional[str] = None


class SetupResponse(BaseModel):
    success: bool
    message: str


class CheckResponse(BaseModel):
    valid: bool
    message: str
    creds_path: Optional[str] = None


@router.get(
    "/check",
    response_model=CheckResponse,
    summary="Check GHunt session validity",
    description=(
        "Checks whether the current GHunt session (credentials) is valid. "
        "This does NOT make any external requests—it only verifies the locally stored session."
    ),
)
async def check_session(api_key: str = Depends(verify_api_key)):
    as_client = get_httpx_client()
    try:
        creds = await ghunt_auth.load_and_auth(as_client)
        await as_client.aclose()
        return CheckResponse(
            valid=True,
            message="Session is valid and authenticated.",
            creds_path=str(creds.creds_path),
        )
    except GHuntInvalidSession as e:
        await as_client.aclose()
        return CheckResponse(valid=False, message=str(e))
    except Exception as e:
        await as_client.aclose()
        return CheckResponse(valid=False, message=f"Unexpected error: {str(e)}")


@router.post(
    "/setup",
    response_model=SetupResponse,
    summary="Setup GHunt credentials",
    description=(
        "Upload GHunt credentials to authenticate the session. "
        "Provide one of:\n"
        "- `credentials`: base64-encoded JSON from GHunt Companion (`{\"oauth_token\": \"...\"}`).\n"
        "- `oauth_token`: OAuth2 token string starting with `oauth2_4/`.\n"
        "- `master_token`: Master token string starting with `aas_et/`.\n\n"
        "This will generate and save cookies/OSIDs locally on the server."
    ),
)
async def setup_session(request: SetupRequest, api_key: str = Depends(verify_api_key)):
    oauth_token = ""
    master_token = ""

    # Parse credentials from different input formats
    if request.credentials:
        try:
            data = json.loads(base64.b64decode(request.credentials).decode())
            oauth_token = data.get("oauth_token", "")
            master_token = data.get("master_token", "")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid base64 credentials: {str(e)}",
            )
    elif request.oauth_token:
        oauth_token = request.oauth_token.strip('" ')
    elif request.master_token:
        master_token = request.master_token.strip('" ')
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide one of: credentials (base64), oauth_token, or master_token.",
        )

    as_client = get_httpx_client()
    ghunt_creds = GHuntCreds()

    try:
        ghunt_creds.android.authorization_tokens = {}

        if oauth_token:
            master_token, services, owner_email, owner_name = await ghunt_auth.android_master_auth(
                as_client, oauth_token
            )

        if not master_token:
            await as_client.aclose()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to obtain master token. Check your OAuth token.",
            )

        ghunt_creds.android.master_token = master_token
        ghunt_creds.cookies = {"a": "a"}
        ghunt_creds.osids = {"a": "a"}

        await ghunt_auth.gen_cookies_and_osids(as_client, ghunt_creds)
        ghunt_creds.save_creds(silent=True)
        await as_client.aclose()

        return SetupResponse(
            success=True,
            message=f"Session created and saved successfully. Credentials stored at {ghunt_creds.creds_path}",
        )

    except HTTPException:
        await as_client.aclose()
        raise
    except Exception as e:
        await as_client.aclose()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to setup session: {str(e)}",
        )
